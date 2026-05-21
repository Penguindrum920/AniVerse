"""Local trainable anime retrieval model.

This model is intentionally independent of ChromaDB. It trains a TF-IDF
retriever from the local anime CSV so search and similarity continue to work
when prebuilt vector indexes are unavailable or incompatible.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional
import re

import joblib
import pandas as pd
from scipy import sparse
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.pipeline import FeatureUnion
from sklearn.preprocessing import normalize

import sys

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import BACKEND_DIR, DATASET_PATH
from data.anime_schema import parse_list_field


MODEL_VERSION = "anime-tfidf-v3"
DEFAULT_MODEL_PATH = BACKEND_DIR / "models" / "anime_retrieval_model.joblib"
_model: Optional["AnimeRetrievalModel"] = None


def clean_text(value) -> str:
    """Normalize nullable CSV fields into compact text."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def weighted_section(label: str, values: list[str], repeat: int = 1) -> str:
    """Repeat important fields so they matter more in TF-IDF retrieval."""
    if not values:
        return ""
    text = f"{label}: " + ", ".join(clean_text(value) for value in values if clean_text(value))
    return " ".join([text] * repeat)


def anime_document(row: pd.Series) -> str:
    """Build a richer retrieval document from title, metadata, and synopsis."""
    genres = parse_list_field(row.get("genres", "[]"))
    studios = parse_list_field(row.get("studios", "[]"))
    synonyms = parse_list_field(row.get("alternative_titles_synonyms", "[]"))

    title_values = [
        row.get("title"),
        row.get("title_english"),
        row.get("title_japanese"),
        row.get("alternative_titles_en"),
        row.get("alternative_titles_ja"),
        *synonyms,
    ]

    parts = [
        weighted_section("Title", [clean_text(value) for value in title_values], repeat=4),
        weighted_section("Genres", genres, repeat=3),
        weighted_section("Studios", studios, repeat=2),
        weighted_section("Type", [row.get("media_type")], repeat=2),
        weighted_section("Source", [row.get("source")], repeat=2),
        weighted_section("Rating", [row.get("rating")], repeat=1),
        clean_text(row.get("synopsis")),
    ]

    return " ".join(part for part in parts if part)


def safe_float(value, default: float = 0.0) -> float:
    try:
        if pd.isna(value):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def safe_int(value, default: int = 0) -> int:
    try:
        if pd.isna(value):
            return default
        return int(float(value))
    except (TypeError, ValueError):
        return default


def row_metadata(row: pd.Series) -> dict:
    genres = parse_list_field(row.get("genres", "[]"))
    studios = parse_list_field(row.get("studios", "[]"))
    return {
        "title": clean_text(row.get("title")) or "Unknown",
        "score": safe_float(row.get("score")),
        "genres": ", ".join(genres),
        "studios": ", ".join(studios),
        "media_type": clean_text(row.get("media_type")),
        "status": clean_text(row.get("status")),
        "source": clean_text(row.get("source")),
        "rating": clean_text(row.get("rating")),
        "image_url": clean_text(row.get("image_url")),
        "popularity": safe_int(row.get("popularity")),
        "rank": safe_int(row.get("rank")),
        "scored_by": safe_int(row.get("scored_by")),
        "nsfw": clean_text(row.get("nsfw")),
    }


QUERY_EXPANSIONS = {
    "dark fantasy": ["Fantasy", "Horror", "Gore", "Supernatural", "Psychological", "Seinen"],
    "demon": ["Supernatural", "Fantasy", "Action"],
    "demons": ["Supernatural", "Fantasy", "Action"],
    "revenge": ["Drama", "Action", "Psychological"],
    "violent": ["Action", "Gore", "Horror"],
    "violence": ["Action", "Gore", "Horror"],
    "ninja": ["Action", "Martial Arts", "Shounen"],
    "samurai": ["Action", "Historical", "Martial Arts"],
    "space": ["Sci-Fi", "Space"],
    "robot": ["Mecha", "Sci-Fi"],
    "robots": ["Mecha", "Sci-Fi"],
    "mind game": ["Psychological", "Suspense"],
    "mind games": ["Psychological", "Suspense"],
    "time travel": ["Time Travel", "Sci-Fi", "Suspense"],
    "romantic": ["Romance"],
    "funny": ["Comedy"],
    "wholesome": ["Slice of Life", "CGDCT"],
}


def query_genre_hints(query: str) -> list[str]:
    query_lower = query.lower()
    hints = []

    for key, genres in QUERY_EXPANSIONS.items():
        if key in query_lower:
            hints.extend(genres)

    # Use the shared genre detector when available.
    try:
        from embeddings.search_utils import detect_genres_from_query
        hints.extend(detect_genres_from_query(query))
    except Exception:
        pass

    return list(dict.fromkeys(hints))


def expanded_query_text(query: str) -> str:
    hints = query_genre_hints(query)
    if not hints:
        return query
    return f"{query} " + weighted_section("Genres", hints, repeat=4)


def metadata_quality_score(metadata: dict) -> float:
    score = safe_float(metadata.get("score")) / 10
    popularity = safe_float(metadata.get("popularity"))
    if popularity > 0:
        popularity_score = max(0.12, 1 - min(popularity, 20000) / 22000)
    else:
        popularity_score = 0.25
    return 0.75 * score + 0.25 * popularity_score


def low_value_metadata(metadata: dict) -> bool:
    media_type = str(metadata.get("media_type", "")).lower()
    nsfw = str(metadata.get("nsfw", "")).lower()
    return nsfw == "black" or media_type in {"cm", "pv"}


@dataclass
class AnimeRetrievalModel:
    """Sparse TF-IDF retriever trained from the AniVerse anime dataset."""

    vectorizer: FeatureUnion
    matrix: sparse.csr_matrix
    records: list[dict]
    documents: list[str]
    id_to_index: dict[int, int]

    @classmethod
    def train(cls, df: pd.DataFrame) -> "AnimeRetrievalModel":
        records = []
        documents = []

        for _, row in df.iterrows():
            mal_id = safe_int(row.get("mal_id"))
            if not mal_id:
                continue

            document = anime_document(row)
            if not document:
                continue

            records.append({
                "mal_id": mal_id,
                "metadata": row_metadata(row),
            })
            documents.append(document)

        vectorizer = FeatureUnion([
            ("word", TfidfVectorizer(
                analyzer="word",
                ngram_range=(1, 2),
                min_df=2,
                max_df=0.88,
                sublinear_tf=True,
                strip_accents="unicode",
                stop_words="english",
                norm="l2",
            )),
            ("char", TfidfVectorizer(
                analyzer="char_wb",
                ngram_range=(3, 5),
                min_df=2,
                max_features=50000,
                sublinear_tf=True,
                strip_accents="unicode",
                norm="l2",
            )),
        ])

        matrix = normalize(vectorizer.fit_transform(documents), norm="l2").tocsr()
        id_to_index = {
            record["mal_id"]: index
            for index, record in enumerate(records)
        }

        return cls(
            vectorizer=vectorizer,
            matrix=matrix,
            records=records,
            documents=documents,
            id_to_index=id_to_index,
        )

    def _format_result(self, index: int, similarity: float) -> dict:
        record = self.records[index]
        return {
            "mal_id": record["mal_id"],
            "metadata": record["metadata"],
            "document": self.documents[index],
            "similarity": float(max(0.0, min(1.0, similarity))),
        }

    def _top_indices(self, query_vector, n_results: int, exclude_index: Optional[int] = None) -> list[tuple[int, float]]:
        scores = (self.matrix @ query_vector.T).toarray().ravel()
        if exclude_index is not None and 0 <= exclude_index < len(scores):
            scores[exclude_index] = -1

        positive_count = int((scores > 0).sum())
        if positive_count == 0:
            return []

        k = min(max(n_results * 4, n_results), positive_count, len(scores))
        candidate_indices = scores.argpartition(-k)[-k:]
        ranked = sorted(
            ((int(index), float(scores[index])) for index in candidate_indices if scores[index] > 0),
            key=lambda item: item[1],
            reverse=True,
        )
        return ranked

    def search(
        self,
        query: str,
        n_results: int = 10,
        genre: Optional[str] = None,
        min_score: Optional[float] = None,
        media_type: Optional[str] = None,
    ) -> list[dict]:
        hints = query_genre_hints(query)
        query_words = {
            word
            for word in re.findall(r"[a-z0-9]+", query.lower())
            if len(word) > 2
        }
        query_vector = normalize(self.vectorizer.transform([expanded_query_text(query)]), norm="l2")
        ranked = self._top_indices(query_vector, n_results=max(n_results * 12, 100))

        candidates = []
        for index, score in ranked:
            result = self._format_result(index, score)
            metadata = result["metadata"]

            if low_value_metadata(metadata):
                continue
            if genre and genre.lower() not in metadata.get("genres", "").lower():
                continue
            if min_score is not None and safe_float(metadata.get("score")) < min_score:
                continue
            if media_type and metadata.get("media_type", "").lower() != media_type.lower():
                continue

            genres = {item.strip() for item in metadata.get("genres", "").split(",") if item.strip()}
            hint_overlap = len(genres.intersection(hints)) / max(1, len(hints))
            title_words = set(re.findall(r"[a-z0-9]+", metadata.get("title", "").lower()))
            title_overlap = len(title_words.intersection(query_words)) / max(1, len(query_words))
            quality = metadata_quality_score(metadata)
            combined_score = (
                0.68 * result["similarity"]
                + 0.18 * quality
                + 0.09 * hint_overlap
                + 0.05 * title_overlap
            )
            result["similarity"] = max(0.0, min(1.0, combined_score))
            candidates.append(result)

        candidates.sort(key=lambda item: item["similarity"], reverse=True)
        results = candidates[:n_results]

        return results

    def search_similar(self, mal_id: int, n_results: int = 10) -> list[dict]:
        source_index = self.id_to_index.get(int(mal_id))
        if source_index is None:
            return []

        query_vector = normalize(self.matrix[source_index], norm="l2")
        ranked = self._top_indices(query_vector, n_results=n_results, exclude_index=source_index)
        return [self._format_result(index, score) for index, score in ranked[:n_results]]

    def get_count(self) -> int:
        return len(self.records)


def dataset_signature() -> dict:
    stat = DATASET_PATH.stat()
    return {
        "path": str(DATASET_PATH),
        "size": stat.st_size,
        "mtime": stat.st_mtime,
    }


def train_and_save_model(model_path: Path = DEFAULT_MODEL_PATH) -> AnimeRetrievalModel:
    from data.data_loader import load_anime_dataset

    df = load_anime_dataset()
    model = AnimeRetrievalModel.train(df)

    model_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump({
        "version": MODEL_VERSION,
        "dataset": dataset_signature(),
        "model": model,
    }, model_path, compress=3)

    return model


def load_or_train_model(force_rebuild: bool = False, model_path: Path = DEFAULT_MODEL_PATH) -> AnimeRetrievalModel:
    if not force_rebuild and model_path.exists():
        payload = joblib.load(model_path)
        if (
            payload.get("version") == MODEL_VERSION
            and payload.get("dataset") == dataset_signature()
            and payload.get("model") is not None
        ):
            return payload["model"]

    return train_and_save_model(model_path=model_path)


def get_anime_retrieval_model(force_rebuild: bool = False) -> AnimeRetrievalModel:
    global _model

    if force_rebuild or _model is None:
        _model = load_or_train_model(force_rebuild=force_rebuild)

    return _model


def get_model_artifact_info(model_path: Path = DEFAULT_MODEL_PATH) -> dict:
    if not model_path.exists():
        return {
            "available": False,
            "path": str(model_path),
            "version": MODEL_VERSION,
        }

    try:
        payload = joblib.load(model_path)
        model = payload.get("model")
        return {
            "available": True,
            "path": str(model_path),
            "version": payload.get("version"),
            "dataset": payload.get("dataset"),
            "count": model.get_count() if model else 0,
        }
    except Exception as e:
        return {
            "available": False,
            "path": str(model_path),
            "version": MODEL_VERSION,
            "error": str(e),
        }
