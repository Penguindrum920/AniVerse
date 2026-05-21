"""Live anime provider integration with local cache and lazy vector indexing."""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta
from typing import Optional

import httpx
from sqlalchemy.orm import Session

from config import (
    ANILIST_GRAPHQL_URL,
    JIKAN_BASE_URL,
    LIVE_CACHE_TTL_HOURS,
    LIVE_ID_OFFSET,
    LIVE_PROVIDER_ENABLED,
    LIVE_SEARCH_TIMEOUT,
)
from data.database import CachedAnime, SessionLocal, init_db

_db_ready = False


ANILIST_SEARCH_QUERY = """
query ($search: String, $page: Int, $perPage: Int, $genre: String, $sort: [MediaSort]) {
  Page(page: $page, perPage: $perPage) {
    media(type: ANIME, search: $search, genre: $genre, sort: $sort) {
      id
      idMal
      title { romaji english native userPreferred }
      format
      status
      description(asHtml: false)
      startDate { year month day }
      endDate { year month day }
      season
      seasonYear
      episodes
      averageScore
      meanScore
      popularity
      favourites
      genres
      synonyms
      source(version: 3)
      countryOfOrigin
      coverImage { extraLarge large medium }
      bannerImage
      siteUrl
      updatedAt
      nextAiringEpisode { episode airingAt }
      studios(isMain: true) {
        nodes { name }
      }
      rankings {
        rank
        type
        allTime
      }
    }
  }
}
"""


ANILIST_DETAIL_QUERY = """
query ($id: Int, $idMal: Int) {
  Media(id: $id, idMal: $idMal, type: ANIME) {
    id
    idMal
    title { romaji english native userPreferred }
    format
    status
    description(asHtml: false)
    startDate { year month day }
    endDate { year month day }
    season
    seasonYear
    episodes
    averageScore
    meanScore
    popularity
    favourites
    genres
    synonyms
    source(version: 3)
    countryOfOrigin
    coverImage { extraLarge large medium }
    bannerImage
    siteUrl
    updatedAt
    nextAiringEpisode { episode airingAt }
    studios(isMain: true) {
      nodes { name }
    }
    rankings {
      rank
      type
      allTime
    }
  }
}
"""


def is_live_enabled() -> bool:
    return LIVE_PROVIDER_ENABLED


def ensure_cache_db() -> None:
    global _db_ready
    if not _db_ready:
        init_db()
        _db_ready = True


def to_public_id(anilist_id: Optional[int], mal_id: Optional[int]) -> int:
    """Keep MAL IDs when available; synthesize stable IDs for AniList-only entries."""
    if mal_id:
        return int(mal_id)
    if not anilist_id:
        raise ValueError("Live anime requires either an AniList ID or MAL ID")
    return LIVE_ID_OFFSET + int(anilist_id)


def public_id_to_anilist_id(public_id: int) -> Optional[int]:
    if int(public_id) >= LIVE_ID_OFFSET:
        return int(public_id) - LIVE_ID_OFFSET
    return None


def clean_description(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    value = re.sub(r"<br\s*/?>", "\n", value, flags=re.IGNORECASE)
    value = re.sub(r"<[^>]+>", "", value)
    value = re.sub(r"\n{3,}", "\n\n", value)
    return value.strip() or None


def fuzzy_date_to_string(value: Optional[dict]) -> Optional[str]:
    if not value or not value.get("year"):
        return None
    year = int(value["year"])
    month = int(value.get("month") or 1)
    day = int(value.get("day") or 1)
    return f"{year:04d}-{month:02d}-{day:02d}"


def normalize_media_type(value: Optional[str]) -> str:
    mapping = {
        "TV": "tv",
        "TV_SHORT": "tv_short",
        "MOVIE": "movie",
        "SPECIAL": "special",
        "OVA": "ova",
        "ONA": "ona",
        "MUSIC": "music",
    }
    return mapping.get((value or "").upper(), (value or "unknown").lower())


def normalize_status(value: Optional[str]) -> str:
    mapping = {
        "FINISHED": "finished_airing",
        "RELEASING": "currently_airing",
        "NOT_YET_RELEASED": "not_yet_aired",
        "CANCELLED": "cancelled",
        "HIATUS": "on_hiatus",
    }
    return mapping.get((value or "").upper(), (value or "unknown").lower())


def normalize_score(value: Optional[int | float]) -> Optional[float]:
    if value is None:
        return None
    try:
        score = float(value)
    except (TypeError, ValueError):
        return None
    return round(score / 10, 2) if score > 10 else round(score, 2)


def get_rank(rankings: Optional[list[dict]]) -> Optional[int]:
    if not rankings:
        return None
    for ranking in rankings:
        if ranking.get("allTime") and str(ranking.get("type", "")).upper() == "RATED":
            return ranking.get("rank")
    return rankings[0].get("rank")


def normalize_anilist_media(media: Optional[dict]) -> Optional[dict]:
    if not media:
        return None

    title = media.get("title") or {}
    cover = media.get("coverImage") or {}
    studios = [
        node.get("name")
        for node in ((media.get("studios") or {}).get("nodes") or [])
        if node.get("name")
    ]

    anilist_id = media.get("id")
    mal_id = media.get("idMal")
    public_id = to_public_id(anilist_id, mal_id)

    return {
        "mal_id": public_id,
        "anilist_id": anilist_id,
        "external_mal_id": mal_id,
        "provider": "anilist",
        "title": title.get("userPreferred") or title.get("english") or title.get("romaji") or "Unknown",
        "title_english": title.get("english"),
        "title_japanese": title.get("native"),
        "media_type": normalize_media_type(media.get("format")),
        "episodes": media.get("episodes"),
        "status": normalize_status(media.get("status")),
        "score": normalize_score(media.get("averageScore") or media.get("meanScore")),
        "scored_by": None,
        "rank": get_rank(media.get("rankings")),
        "popularity": media.get("popularity"),
        "favorites": media.get("favourites"),
        "synopsis": clean_description(media.get("description")),
        "genres": media.get("genres") or [],
        "synonyms": media.get("synonyms") or [],
        "studios": studios,
        "source": media.get("source"),
        "rating": None,
        "image_url": cover.get("extraLarge") or cover.get("large") or cover.get("medium"),
        "start_date": fuzzy_date_to_string(media.get("startDate")),
        "end_date": fuzzy_date_to_string(media.get("endDate")),
        "site_url": media.get("siteUrl"),
        "next_airing_episode": media.get("nextAiringEpisode"),
        "raw": media,
    }


def normalize_jikan_anime(data: Optional[dict]) -> Optional[dict]:
    if not data:
        return None

    images = data.get("images") or {}
    jpg = images.get("jpg") or {}
    aired = data.get("aired") or {}

    return {
        "mal_id": int(data["mal_id"]),
        "anilist_id": None,
        "external_mal_id": int(data["mal_id"]),
        "provider": "jikan",
        "title": data.get("title") or data.get("title_english") or "Unknown",
        "title_english": data.get("title_english"),
        "title_japanese": data.get("title_japanese"),
        "media_type": normalize_media_type(data.get("type")),
        "episodes": data.get("episodes"),
        "status": data.get("status") or "unknown",
        "score": normalize_score(data.get("score")),
        "scored_by": data.get("scored_by"),
        "rank": data.get("rank"),
        "popularity": data.get("popularity"),
        "favorites": data.get("favorites"),
        "synopsis": data.get("synopsis"),
        "genres": [item.get("name") for item in data.get("genres", []) if item.get("name")],
        "synonyms": [item.get("title") for item in data.get("titles", []) if item.get("title")],
        "studios": [item.get("name") for item in data.get("studios", []) if item.get("name")],
        "source": data.get("source"),
        "rating": data.get("rating"),
        "image_url": jpg.get("large_image_url") or jpg.get("image_url"),
        "start_date": aired.get("from"),
        "end_date": aired.get("to"),
        "site_url": data.get("url"),
        "next_airing_episode": None,
        "raw": data,
    }


def anime_to_detail_response(anime: dict) -> dict:
    return {
        "mal_id": anime["mal_id"],
        "title": anime.get("title"),
        "title_english": anime.get("title_english"),
        "title_japanese": anime.get("title_japanese"),
        "media_type": anime.get("media_type", "unknown"),
        "episodes": anime.get("episodes"),
        "status": anime.get("status", "unknown"),
        "score": anime.get("score"),
        "scored_by": anime.get("scored_by"),
        "rank": anime.get("rank"),
        "popularity": anime.get("popularity"),
        "favorites": anime.get("favorites"),
        "synopsis": anime.get("synopsis"),
        "genres": anime.get("genres") or [],
        "studios": anime.get("studios") or [],
        "source": anime.get("source"),
        "rating": anime.get("rating"),
        "image_url": anime.get("image_url"),
        "start_date": anime.get("start_date"),
        "end_date": anime.get("end_date"),
        "anilist_id": anime.get("anilist_id"),
        "external_mal_id": anime.get("external_mal_id"),
        "provider": anime.get("provider"),
        "site_url": anime.get("site_url"),
        "next_airing_episode": anime.get("next_airing_episode"),
    }


def anime_to_search_result(anime: dict, similarity: float = 1.0) -> dict:
    return {
        "mal_id": anime["mal_id"],
        "metadata": {
            "title": anime.get("title") or "Unknown",
            "score": anime.get("score") or 0,
            "genres": ", ".join(anime.get("genres") or []),
            "media_type": anime.get("media_type") or "unknown",
            "image_url": anime.get("image_url") or "",
            "popularity": anime.get("popularity") or 0,
        },
        "document": create_live_embedding_text(anime),
        "similarity": similarity,
        "provider": anime.get("provider"),
    }


def create_live_embedding_text(anime: dict) -> str:
    parts = [anime.get("title") or "Unknown"]
    if anime.get("title_english") and anime.get("title_english") != anime.get("title"):
        parts.append(anime["title_english"])
    if anime.get("genres"):
        parts.append(f"Genres: {', '.join(anime['genres'])}")
    if anime.get("synonyms"):
        parts.append(f"Also known as: {', '.join(anime['synonyms'][:5])}")
    if anime.get("studios"):
        parts.append(f"Studios: {', '.join(anime['studios'][:3])}")
    if anime.get("synopsis"):
        parts.append(anime["synopsis"][:1000])
    return " | ".join(parts)


def cached_row_to_anime(row: CachedAnime) -> dict:
    return {
        "mal_id": row.id,
        "anilist_id": row.anilist_id,
        "external_mal_id": row.mal_id,
        "provider": row.provider,
        "title": row.title,
        "title_english": row.title_english,
        "title_japanese": row.title_japanese,
        "media_type": row.media_type,
        "episodes": row.episodes,
        "status": row.status,
        "score": row.score,
        "scored_by": row.scored_by,
        "rank": row.rank,
        "popularity": row.popularity,
        "favorites": row.favorites,
        "synopsis": row.synopsis,
        "genres": json.loads(row.genres or "[]"),
        "studios": json.loads(row.studios or "[]"),
        "source": row.source,
        "rating": row.rating,
        "image_url": row.image_url,
        "start_date": row.start_date,
        "end_date": row.end_date,
        "site_url": row.site_url,
        "next_airing_episode": None,
        "raw": json.loads(row.raw_json or "{}"),
    }


def get_cached_anime(anime_id: int, db: Optional[Session] = None, fresh_only: bool = False) -> Optional[dict]:
    ensure_cache_db()
    owns_session = db is None
    if db is None:
        db = SessionLocal()
    try:
        row = db.query(CachedAnime).filter(CachedAnime.id == int(anime_id)).first()
        if not row:
            return None
        if fresh_only and row.cached_at:
            expires_at = row.cached_at + timedelta(hours=LIVE_CACHE_TTL_HOURS)
            if expires_at < datetime.utcnow():
                return None
        return cached_row_to_anime(row)
    finally:
        if owns_session:
            db.close()


def cache_anime(anime: dict, db: Optional[Session] = None) -> dict:
    ensure_cache_db()
    owns_session = db is None
    if db is None:
        db = SessionLocal()
    try:
        public_id = int(anime["mal_id"])
        row = db.query(CachedAnime).filter(CachedAnime.id == public_id).first()
        if row is None:
            row = CachedAnime(id=public_id)
            db.add(row)

        row.mal_id = anime.get("external_mal_id")
        row.anilist_id = anime.get("anilist_id")
        row.provider = anime.get("provider") or "anilist"
        row.title = anime.get("title") or "Unknown"
        row.title_english = anime.get("title_english")
        row.title_japanese = anime.get("title_japanese")
        row.media_type = anime.get("media_type")
        row.episodes = anime.get("episodes")
        row.status = anime.get("status")
        row.score = anime.get("score")
        row.scored_by = anime.get("scored_by")
        row.rank = anime.get("rank")
        row.popularity = anime.get("popularity")
        row.favorites = anime.get("favorites")
        row.synopsis = anime.get("synopsis")
        row.genres = json.dumps(anime.get("genres") or [])
        row.studios = json.dumps(anime.get("studios") or [])
        row.source = anime.get("source")
        row.rating = anime.get("rating")
        row.image_url = anime.get("image_url")
        row.start_date = anime.get("start_date")
        row.end_date = anime.get("end_date")
        row.site_url = anime.get("site_url")
        row.raw_json = json.dumps(anime.get("raw") or {})
        row.cached_at = datetime.utcnow()
        row.updated_at = datetime.utcnow()
        db.commit()
        return anime
    finally:
        if owns_session:
            db.close()


def index_live_anime(anime: dict, store=None) -> None:
    try:
        if store is None:
            from embeddings.chroma_store import get_vector_store

            store = get_vector_store()
        store.add_anime(
            mal_id=int(anime["mal_id"]),
            embedding_text=create_live_embedding_text(anime),
            metadata={
                "title": anime.get("title") or "Unknown",
                "score": anime.get("score") or 0,
                "genres": ", ".join(anime.get("genres") or []),
                "media_type": anime.get("media_type") or "unknown",
                "status": anime.get("status") or "unknown",
                "image_url": anime.get("image_url") or "",
                "popularity": anime.get("popularity") or 0,
            },
        )
    except Exception as exc:
        print(f"Live anime vector indexing skipped for {anime.get('mal_id')}: {exc}")


async def anilist_request(query: str, variables: dict) -> Optional[dict]:
    async with httpx.AsyncClient(timeout=LIVE_SEARCH_TIMEOUT) as client:
        response = await client.post(
            ANILIST_GRAPHQL_URL,
            json={"query": query, "variables": variables},
            headers={"Content-Type": "application/json", "Accept": "application/json"},
        )
        response.raise_for_status()
        payload = response.json()
        if payload.get("errors"):
            print(f"AniList returned errors: {payload['errors']}")
            return None
        return payload.get("data")


def map_sort(sort_by: str, order: str) -> list[str]:
    suffix = "_DESC" if order == "desc" else ""
    mapping = {
        "score": f"SCORE{suffix}",
        "rank": f"SCORE{suffix}",
        "popularity": f"POPULARITY{suffix}",
        "members": f"POPULARITY{suffix}",
        "scored_by": f"POPULARITY{suffix}",
        "favorites": f"FAVOURITES{suffix}",
        "updated": f"UPDATED_AT{suffix}",
        "trending": f"TRENDING{suffix}",
    }
    return [mapping.get(sort_by, f"POPULARITY{suffix}")]


def rank_live_search_results(query: str, results: list[dict]) -> list[dict]:
    words = [word for word in re.findall(r"[a-z0-9]+", query.lower()) if len(word) > 1]
    if not words:
        return results

    def score(anime: dict) -> float:
        titles = [
            anime.get("title") or "",
            anime.get("title_english") or "",
            anime.get("title_japanese") or "",
            *[str(item) for item in anime.get("synonyms", [])],
        ]
        title_blob = " ".join(titles).lower()
        query_lower = query.lower()

        title_score = 0.0
        if query_lower in title_blob:
            title_score += 100
        title_score += sum(12 for word in words if word in title_blob)
        if words and all(word in title_blob for word in words):
            title_score += 40

        quality_score = (anime.get("score") or 0) * 2
        popularity_score = min((anime.get("popularity") or 0) / 100000, 10)
        return title_score + quality_score + popularity_score

    return sorted(results, key=score, reverse=True)


async def search_anilist(
    query: str,
    limit: int,
    genre: Optional[str] = None,
    min_score: Optional[float] = None,
    media_type: Optional[str] = None,
) -> list[dict]:
    data = await anilist_request(
        ANILIST_SEARCH_QUERY,
        {
            "search": query,
            "page": 1,
            "perPage": min(max(limit, 1), 50),
            "genre": genre,
            "sort": ["SEARCH_MATCH"],
        },
    )
    media = ((data or {}).get("Page") or {}).get("media") or []
    results = [item for item in (normalize_anilist_media(item) for item in media) if item]
    return rank_live_search_results(query, filter_live_results(results, min_score=min_score, media_type=media_type))


async def list_anilist(
    page: int,
    limit: int,
    sort_by: str,
    order: str,
    genre: Optional[str] = None,
    min_score: Optional[float] = None,
    media_type: Optional[str] = None,
) -> list[dict]:
    data = await anilist_request(
        ANILIST_SEARCH_QUERY,
        {
            "search": None,
            "page": page,
            "perPage": min(max(limit, 1), 50),
            "genre": genre,
            "sort": map_sort(sort_by, order),
        },
    )
    media = ((data or {}).get("Page") or {}).get("media") or []
    results = [item for item in (normalize_anilist_media(item) for item in media) if item]
    return filter_live_results(results, min_score=min_score, media_type=media_type)


async def get_anilist_by_id(anime_id: int) -> Optional[dict]:
    anilist_id = public_id_to_anilist_id(anime_id)
    variables = {"id": anilist_id, "idMal": None if anilist_id else int(anime_id)}
    data = await anilist_request(ANILIST_DETAIL_QUERY, variables)
    return normalize_anilist_media((data or {}).get("Media"))


async def search_jikan(
    query: str,
    limit: int,
    genre: Optional[str] = None,
    min_score: Optional[float] = None,
    media_type: Optional[str] = None,
) -> list[dict]:
    params = {"q": query, "limit": min(max(limit, 1), 25), "sfw": "true"}
    async with httpx.AsyncClient(timeout=LIVE_SEARCH_TIMEOUT) as client:
        response = await client.get(f"{JIKAN_BASE_URL}/anime", params=params)
        response.raise_for_status()
        data = response.json().get("data") or []
    results = [item for item in (normalize_jikan_anime(item) for item in data) if item]
    if genre:
        genre_lower = genre.lower()
        results = [item for item in results if genre_lower in [g.lower() for g in item.get("genres", [])]]
    return rank_live_search_results(query, filter_live_results(results, min_score=min_score, media_type=media_type))


async def get_jikan_by_id(anime_id: int) -> Optional[dict]:
    if public_id_to_anilist_id(anime_id):
        return None
    async with httpx.AsyncClient(timeout=LIVE_SEARCH_TIMEOUT) as client:
        response = await client.get(f"{JIKAN_BASE_URL}/anime/{int(anime_id)}/full")
        response.raise_for_status()
        return normalize_jikan_anime(response.json().get("data"))


def filter_live_results(
    results: list[dict],
    min_score: Optional[float] = None,
    media_type: Optional[str] = None,
) -> list[dict]:
    if min_score is not None:
        results = [item for item in results if (item.get("score") or 0) >= min_score]
    if media_type:
        media_type_lower = media_type.lower()
        results = [item for item in results if (item.get("media_type") or "").lower() == media_type_lower]
    return results


async def search_live_anime(
    query: str,
    limit: int = 10,
    genre: Optional[str] = None,
    min_score: Optional[float] = None,
    media_type: Optional[str] = None,
) -> list[dict]:
    if not is_live_enabled():
        return []
    try:
        results = await search_anilist(query, limit, genre, min_score, media_type)
    except Exception as exc:
        print(f"AniList search failed, trying Jikan: {exc}")
        results = []

    if not results:
        try:
            results = await search_jikan(query, limit, genre, min_score, media_type)
        except Exception as exc:
            print(f"Jikan search failed: {exc}")
            results = []

    for anime in results:
        cache_anime(anime)
    return results


async def list_live_anime(
    page: int = 1,
    limit: int = 20,
    sort_by: str = "score",
    order: str = "desc",
    genre: Optional[str] = None,
    min_score: Optional[float] = None,
    media_type: Optional[str] = None,
) -> list[dict]:
    if not is_live_enabled():
        return []
    try:
        results = await list_anilist(page, limit, sort_by, order, genre, min_score, media_type)
    except Exception as exc:
        print(f"AniList list failed: {exc}")
        results = []

    for anime in results:
        cache_anime(anime)
    return results


async def get_live_anime(anime_id: int, prefer_cache: bool = True) -> Optional[dict]:
    if prefer_cache:
        cached = get_cached_anime(anime_id, fresh_only=True)
        if cached:
            return cached

    if not is_live_enabled():
        return get_cached_anime(anime_id)

    result = None
    try:
        result = await get_anilist_by_id(anime_id)
    except Exception as exc:
        print(f"AniList detail failed, trying Jikan: {exc}")

    if result is None:
        try:
            result = await get_jikan_by_id(anime_id)
        except Exception as exc:
            print(f"Jikan detail failed: {exc}")

    if result:
        cache_anime(result)
        return result

    return get_cached_anime(anime_id)
