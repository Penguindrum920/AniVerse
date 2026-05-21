"""Personalized Recommendations API Routes"""
from collections import Counter
import math
import re
import sys
from pathlib import Path
from typing import List, Optional

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

sys.path.insert(0, str(Path(__file__).parent.parent))
from data.anime_schema import parse_list_field
from data.data_loader import load_anime_dataset
from data.database import AnimeStatus, User, UserAnime, get_db
from routes.auth import get_current_user, require_user

router = APIRouter(prefix="/api/recommendations", tags=["Recommendations"])


class RecommendationItem(BaseModel):
    mal_id: int
    title: str
    score: float
    genres: str
    image_url: str
    similarity: float
    reason: str


class RecommendationsResponse(BaseModel):
    based_on: List[dict]
    recommendations: List[RecommendationItem]


_anime_df: Optional[pd.DataFrame] = None
_anime_by_id: dict[int, pd.Series] = {}


def get_anime_df() -> pd.DataFrame:
    """Load the local anime CSV once and index it by MAL ID."""
    global _anime_df, _anime_by_id

    if _anime_df is None:
        df = load_anime_dataset()
        _anime_df = df
        _anime_by_id = {
            int(row["mal_id"]): row
            for _, row in df.iterrows()
            if pd.notna(row.get("mal_id"))
        }

    return _anime_df


def get_anime_row(mal_id: int) -> Optional[pd.Series]:
    """Look up an anime row by MAL ID from the local CSV."""
    get_anime_df()
    return _anime_by_id.get(int(mal_id))


def safe_float(value, default: float = 0.0) -> float:
    """Convert CSV values to float without leaking NaN."""
    try:
        if pd.isna(value):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def safe_int(value, default: int = 0) -> int:
    """Convert CSV values to int without leaking NaN."""
    try:
        if pd.isna(value):
            return default
        return int(float(value))
    except (TypeError, ValueError):
        return default


def row_genres(row: pd.Series) -> list[str]:
    return parse_list_field(row.get("genres", "[]"))


def row_studios(row: pd.Series) -> list[str]:
    return parse_list_field(row.get("studios", "[]"))


def row_title(row: pd.Series) -> str:
    return str(row.get("title", "Unknown"))


def row_media_type(row: pd.Series) -> str:
    return str(row.get("media_type", "") or "").lower()


def row_score(row: pd.Series) -> float:
    return safe_float(row.get("score"), 0.0)


def row_popularity_score(row: pd.Series) -> float:
    """Normalize popularity so higher is better."""
    popularity = safe_float(row.get("popularity"), 0.0)
    if popularity > 0:
        if popularity <= 1000:
            return max(0.5, 1 - popularity / 2000)
        return max(0.12, 0.5 - (popularity - 1000) / 40000)

    list_users = safe_float(row.get("num_list_users"), 0.0)
    if list_users > 0:
        return min(1.0, math.log10(list_users + 1) / 7)

    return 0.25


def is_adult_or_low_value(row: pd.Series) -> bool:
    """Skip records that tend to be poor discovery recommendations."""
    nsfw = str(row.get("nsfw", "") or "").lower()
    media_type = row_media_type(row)
    return nsfw == "black" or media_type in {"cm", "pv"}


def preference_weight(entry: UserAnime) -> float:
    """Turn a list entry into a positive or negative preference weight."""
    rating = entry.rating
    favorite_bonus = 0.9 if entry.is_favorite else 0.0

    if rating is not None:
        if rating >= 9:
            return 3.2 + favorite_bonus
        if rating >= 8:
            return 2.5 + favorite_bonus
        if rating >= 7:
            return 1.6 + favorite_bonus
        if rating >= 6:
            return 0.7 + favorite_bonus
        return -1.4

    if entry.status == AnimeStatus.completed:
        return 1.0 + favorite_bonus
    if entry.status == AnimeStatus.watching:
        return 0.8 + favorite_bonus
    if entry.status == AnimeStatus.planned:
        return 0.35 + favorite_bonus
    if entry.status == AnimeStatus.on_hold:
        return 0.15
    if entry.status == AnimeStatus.dropped:
        return -1.2

    return favorite_bonus


def build_profile(entries: list[UserAnime]) -> dict:
    """Build a weighted preference profile from the user's anime list."""
    profile = {
        "based_on": [],
        "positive_rows": [],
        "genre_weights": Counter(),
        "studio_weights": Counter(),
        "source_weights": Counter(),
        "media_weights": Counter(),
        "negative_genres": Counter(),
    }

    for entry in entries:
        row = get_anime_row(entry.anime_id)
        if row is None:
            continue

        weight = preference_weight(entry)
        genres = row_genres(row)

        if weight < 0:
            for genre in genres:
                profile["negative_genres"][genre] += abs(weight)
            continue

        if weight == 0:
            continue

        profile["positive_rows"].append((row, entry, weight))
        profile["based_on"].append({
            "anime_id": entry.anime_id,
            "title": row_title(row),
            "rating": entry.rating,
            "status": entry.status.value,
            "is_favorite": bool(entry.is_favorite),
        })

        for genre in genres:
            profile["genre_weights"][genre] += weight
        for studio in row_studios(row):
            profile["studio_weights"][studio] += weight * 0.65

        source = str(row.get("source", "") or "").lower()
        if source:
            profile["source_weights"][source] += weight * 0.45

        media_type = row_media_type(row)
        if media_type:
            profile["media_weights"][media_type] += weight * 0.35

    return profile


def weighted_match(items: list[str], weights: Counter) -> float:
    if not items or not weights:
        return 0.0
    total_weight = sum(max(0, value) for value in weights.values()) or 1.0
    matched_weight = sum(max(0, weights.get(item, 0)) for item in items)
    return min(1.0, matched_weight / total_weight)


def title_family_key(title: str) -> str:
    """Coarse franchise key used only for result diversity."""
    key = title.lower()
    key = re.sub(r"\([^)]*\)", " ", key)
    key = re.sub(r"\b(season|part|movie|ova|ona|special|the final|final season)\b", " ", key)
    key = re.sub(r"\b\d+(st|nd|rd|th)?\b", " ", key)
    key = re.sub(r"[^a-z0-9]+", " ", key)
    return " ".join(key.split()[:4])


def best_source_match(row: pd.Series, positive_rows: list[tuple[pd.Series, UserAnime, float]]) -> tuple[str, list[str]]:
    """Find the liked title that best explains a candidate."""
    candidate_genres = set(row_genres(row))
    best_title = ""
    best_overlap: list[str] = []
    best_score = -1.0

    for source_row, _entry, weight in positive_rows:
        overlap = sorted(candidate_genres.intersection(row_genres(source_row)))
        score = len(overlap) + (weight / 10)
        if score > best_score:
            best_score = score
            best_title = row_title(source_row)
            best_overlap = overlap

    return best_title, best_overlap


def recommendation_reason(row: pd.Series, profile: dict, confidence: float) -> str:
    """Generate a short deterministic reason for a recommendation."""
    source_title, overlap = best_source_match(row, profile["positive_rows"])
    pieces = []

    if overlap:
        pieces.append(f"matches your taste for {', '.join(overlap[:3])}")
    if source_title:
        pieces.append(f"based on {source_title}")

    score = row_score(row)
    if score >= 8.5:
        pieces.append(f"it is highly rated at {score:.2f}")
    elif score >= 7.8 and confidence >= 0.55:
        pieces.append(f"it has a strong {score:.2f} score")

    studios = set(row_studios(row))
    liked_studios = set(profile["studio_weights"].keys())
    studio_overlap = sorted(studios.intersection(liked_studios))
    if studio_overlap:
        pieces.append(f"from {studio_overlap[0]}")

    if not pieces:
        pieces.append("it is a strong all-around pick to expand your profile")

    return "Recommended because " + "; ".join(pieces[:3]) + "."


def candidate_confidence(row: pd.Series, profile: dict, vector_boost: float = 0.0) -> float:
    """Score a candidate using user taste, quality, popularity, and exclusions."""
    genres = row_genres(row)
    studios = row_studios(row)
    source = str(row.get("source", "") or "").lower()
    media_type = row_media_type(row)

    genre_score = weighted_match(genres, profile["genre_weights"])
    studio_score = weighted_match(studios, profile["studio_weights"])
    source_score = weighted_match([source], profile["source_weights"])
    media_score = weighted_match([media_type], profile["media_weights"])
    quality_score = row_score(row) / 10
    popularity_score = row_popularity_score(row)
    negative_genre_score = weighted_match(genres, profile["negative_genres"])

    if profile["positive_rows"]:
        confidence = (
            0.46 * genre_score
            + 0.10 * studio_score
            + 0.08 * source_score
            + 0.05 * media_score
            + 0.21 * quality_score
            + 0.07 * popularity_score
            + 0.03 * min(1.0, vector_boost)
        )
    else:
        confidence = 0.62 * quality_score + 0.38 * popularity_score

    confidence -= 0.24 * negative_genre_score

    if str(row.get("nsfw", "") or "").lower() == "gray":
        confidence -= 0.04
    if media_type in {"music"}:
        confidence -= 0.08
    if media_type == "special" and not profile["media_weights"].get("special"):
        confidence -= 0.04

    return max(0.0, min(0.99, confidence))


def row_to_recommendation(row: pd.Series, confidence: float, reason: str) -> RecommendationItem:
    genres = row_genres(row)
    return RecommendationItem(
        mal_id=safe_int(row.get("mal_id")),
        title=row_title(row),
        score=round(row_score(row), 2),
        genres=", ".join(genres),
        image_url=str(row.get("image_url", "") or ""),
        similarity=round(confidence, 3),
        reason=reason,
    )


def select_diverse_recommendations(scored: list[dict], limit: int) -> list[dict]:
    """Keep high-scoring results while reducing sequel and genre pileups."""
    selected = []
    family_counts = Counter()
    primary_genre_counts = Counter()
    max_per_family = 2
    max_primary_genre = max(3, limit // 3)

    for item in scored:
        row = item["row"]
        family = title_family_key(row_title(row))
        primary_genre = row_genres(row)[0] if row_genres(row) else "unknown"

        if family_counts[family] >= max_per_family:
            continue
        if primary_genre_counts[primary_genre] >= max_primary_genre and len(selected) < limit - 2:
            continue

        selected.append(item)
        family_counts[family] += 1
        primary_genre_counts[primary_genre] += 1

        if len(selected) >= limit:
            return selected

    if len(selected) < limit:
        selected_ids = {safe_int(item["row"].get("mal_id")) for item in selected}
        for item in scored:
            mal_id = safe_int(item["row"].get("mal_id"))
            if mal_id in selected_ids:
                continue
            selected.append(item)
            selected_ids.add(mal_id)
            if len(selected) >= limit:
                break

    return selected


def get_retrieval_boosts(seed_entries: list[UserAnime], user_anime_ids: set[int]) -> dict[int, float]:
    """Use the trained local retrieval model as a similarity boost."""
    boosts: dict[int, float] = {}

    try:
        from embeddings.local_retrieval_model import get_anime_retrieval_model
        model = get_anime_retrieval_model()
    except Exception as e:
        print(f"Local retrieval boost unavailable: {e}")
        return boosts

    for entry in seed_entries[:6]:
        for result in model.search_similar(entry.anime_id, n_results=30):
            mal_id = result["mal_id"]
            if mal_id in user_anime_ids:
                continue
            boosts[mal_id] = max(boosts.get(mal_id, 0.0), result.get("similarity", 0.0))

    return boosts


def build_local_recommendations(entries: list[UserAnime], limit: int) -> RecommendationsResponse:
    """Recommend from the full local CSV with profile-aware scoring."""
    df = get_anime_df()
    profile = build_profile(entries)
    user_anime_ids = {entry.anime_id for entry in entries}
    positive_seed_entries = [
        entry
        for _row, entry, _weight in profile["positive_rows"]
        if entry.rating is None or entry.rating >= 7 or entry.is_favorite
    ]
    retrieval_boosts = get_retrieval_boosts(positive_seed_entries, user_anime_ids)

    scored = []
    for _, row in df.iterrows():
        mal_id = safe_int(row.get("mal_id"))
        if not mal_id or mal_id in user_anime_ids or is_adult_or_low_value(row):
            continue

        confidence = candidate_confidence(row, profile, retrieval_boosts.get(mal_id, 0.0))
        if confidence <= 0:
            continue

        scored.append({
            "row": row,
            "confidence": confidence,
            "reason": recommendation_reason(row, profile, confidence),
        })

    scored.sort(key=lambda item: item["confidence"], reverse=True)
    selected = select_diverse_recommendations(scored, limit)

    return RecommendationsResponse(
        based_on=profile["based_on"],
        recommendations=[
            row_to_recommendation(item["row"], item["confidence"], item["reason"])
            for item in selected
        ],
    )


def quick_local_recommendations(anime_id: int, limit: int, excluded_ids: set[int]) -> list[dict]:
    """Find similar local anime from the CSV when Chroma is unavailable."""
    source_row = get_anime_row(anime_id)
    if source_row is None:
        raise HTTPException(status_code=404, detail=f"Anime with ID {anime_id} not found in local dataset")

    source_genres = set(row_genres(source_row))
    source_studios = set(row_studios(source_row))
    source_media = row_media_type(source_row)
    source_source = str(source_row.get("source", "") or "").lower()

    scored = []
    for _, row in get_anime_df().iterrows():
        mal_id = safe_int(row.get("mal_id"))
        if not mal_id or mal_id == anime_id or mal_id in excluded_ids or is_adult_or_low_value(row):
            continue

        genres = set(row_genres(row))
        studios = set(row_studios(row))
        genre_similarity = len(source_genres.intersection(genres)) / max(1, len(source_genres.union(genres)))
        studio_similarity = 1.0 if source_studios.intersection(studios) else 0.0
        media_similarity = 1.0 if row_media_type(row) == source_media else 0.0
        source_similarity = 1.0 if str(row.get("source", "") or "").lower() == source_source else 0.0
        quality_score = row_score(row) / 10
        popularity_score = row_popularity_score(row)

        confidence = (
            0.50 * genre_similarity
            + 0.12 * studio_similarity
            + 0.08 * media_similarity
            + 0.07 * source_similarity
            + 0.16 * quality_score
            + 0.07 * popularity_score
        )
        scored.append({"row": row, "confidence": max(0.0, min(0.99, confidence))})

    scored.sort(key=lambda item: item["confidence"], reverse=True)
    selected = select_diverse_recommendations(scored, limit)
    return [
        {
            "mal_id": safe_int(item["row"].get("mal_id")),
            "title": row_title(item["row"]),
            "score": row_score(item["row"]),
            "genres": ", ".join(row_genres(item["row"])),
            "image_url": str(item["row"].get("image_url", "") or ""),
            "similarity": round(item["confidence"], 3),
            "reason": f"Similar to {row_title(source_row)}",
        }
        for item in selected
    ]


@router.get("", response_model=RecommendationsResponse)
async def get_personalized_recommendations(
    limit: int = 10,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """
    Get personalized recommendations from the full local anime CSV.

    The scorer uses ratings, favorites, statuses, genres, studios, media type,
    source material, dislikes, global score, and popularity. Chroma is used only
    as an optional boost when it is available.
    """
    limit = max(1, min(limit, 50))
    entries = db.query(UserAnime).filter(UserAnime.user_id == user.id).all()

    if not entries:
        raise HTTPException(
            status_code=400,
            detail="Add some anime to your list first to get personalized recommendations.",
        )

    recommendations = build_local_recommendations(entries, limit)
    if not recommendations.recommendations:
        raise HTTPException(
            status_code=404,
            detail="No recommendations found from the local dataset for your current profile.",
        )

    return recommendations


@router.get("/quick")
async def get_quick_recommendations(
    anime_id: int,
    limit: int = 5,
    user: Optional[User] = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Get quick recommendations based on a single anime.

    Uses local CSV similarity so it works even when Chroma is unavailable.
    """
    limit = max(1, min(limit, 30))
    excluded_ids = set()
    if user:
        excluded_ids = {
            item.anime_id
            for item in db.query(UserAnime).filter(UserAnime.user_id == user.id).all()
        }

    try:
        from embeddings.local_retrieval_model import get_anime_retrieval_model
        model = get_anime_retrieval_model()
        source_row = get_anime_row(anime_id)
        source_title = row_title(source_row) if source_row is not None else f"anime #{anime_id}"
        model_results = [
            item
            for item in model.search_similar(anime_id, n_results=limit + len(excluded_ids) + 5)
            if item["mal_id"] not in excluded_ids
        ][:limit]
        if model_results:
            return {
                "source_id": anime_id,
                "recommendations": [
                    {
                        "mal_id": item["mal_id"],
                        "title": item["metadata"]["title"],
                        "score": item["metadata"].get("score", 0),
                        "genres": item["metadata"].get("genres", ""),
                        "image_url": item["metadata"].get("image_url", ""),
                        "similarity": round(item.get("similarity", 0), 3),
                        "reason": f"Similar to {source_title}",
                    }
                    for item in model_results
                ],
            }
    except Exception as e:
        print(f"Quick retrieval model unavailable, using heuristic fallback: {e}")

    return {
        "source_id": anime_id,
        "recommendations": quick_local_recommendations(anime_id, limit, excluded_ids),
    }
