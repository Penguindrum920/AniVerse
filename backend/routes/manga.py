"""Manga API Routes"""
from fastapi import APIRouter, Query, HTTPException
from typing import Optional
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from embeddings.manga_chroma_store import get_manga_vector_store
from data.manga_loader import load_manga_dataset, parse_manga_row

router = APIRouter(prefix="/api/manga", tags=["Manga"])

# Cache for manga data
_manga_df = None
_manga_store = None
_manga_store_error = None


def get_manga_df():
    """Get or load manga dataframe"""
    global _manga_df
    if _manga_df is None:
        _manga_df = load_manga_dataset()
    return _manga_df


def get_manga_vector_store_safe():
    """Return the manga vector store, or None when Chroma is unavailable."""
    global _manga_store, _manga_store_error

    if _manga_store_error:
        return None
    if _manga_store is None:
        try:
            _manga_store = get_manga_vector_store()
        except Exception as e:
            print(f"Manga vector store unavailable, using CSV fallback: {e}")
            _manga_store_error = str(e)
            return None
    return _manga_store


def manga_detail_response(manga):
    """Format a parsed manga row for detail views."""
    return {
        "mal_id": manga.mal_id,
        "title": manga.title,
        "media_type": manga.media_type or "manga",
        "score": manga.score,
        "rank": manga.rank,
        "members": manga.members,
        "volumes": manga.volumes,
        "genres": manga.genres,
        "authors": manga.authors,
        "image_url": manga.image_url or "",
        "published": manga.published or "",
        "synopsis": manga.synopsis,
    }


def manga_summary_response(manga, similarity: float = None):
    """Format a parsed manga row for list and search results."""
    result = {
        "mal_id": manga.mal_id,
        "title": manga.title,
        "media_type": manga.media_type or "manga",
        "score": manga.score or 0,
        "rank": manga.rank or 0,
        "members": manga.members or 0,
        "volumes": manga.volumes or 0,
        "genres": ", ".join(manga.genres) if manga.genres else "",
        "image_url": manga.image_url or "",
    }
    if similarity is not None:
        result["similarity"] = round(similarity, 3)
    return result


def find_manga_in_dataset(mal_id: int):
    """Find manga by MAL ID from the CSV dataset."""
    df = get_manga_df()
    for _, row in df.iterrows():
        manga = parse_manga_row(row)
        if manga.mal_id == mal_id:
            return manga
    return None


def search_manga_dataset(query: str, limit: int):
    """Simple title search fallback for manga."""
    df = get_manga_df().copy()
    query_words = query.lower().split()

    def match_score(row):
        title = str(row.get("Title", "")).lower()
        media_type = str(row.get("Type", "")).lower()
        score = 0
        for word in query_words:
            if word in title:
                score += 10
            if word in media_type:
                score += 2
        return score

    df["match_score"] = df.apply(match_score, axis=1)
    results_df = df[df["match_score"] > 0].sort_values(
        ["match_score", "Score"], ascending=[False, False]
    ).head(limit)

    results = []
    for _, row in results_df.iterrows():
        manga = parse_manga_row(row)
        results.append(manga_summary_response(manga, similarity=row["match_score"] / 100))
    return results


@router.get("/search")
async def search_manga(
    q: str = Query(..., min_length=1, description="Search query"),
    limit: int = Query(20, ge=1, le=100, description="Number of results")
):
    """Semantic search for manga"""
    store = get_manga_vector_store_safe()

    results = []
    if store:
        try:
            results = store.search(query=q, n_results=limit)
        except Exception as e:
            print(f"Manga vector search failed, using CSV fallback: {e}")

    if not results:
        fallback_results = search_manga_dataset(q, limit)
        return {
            "query": q,
            "count": len(fallback_results),
            "results": fallback_results
        }
    
    formatted = []
    for r in results:
        formatted.append({
            "mal_id": r["mal_id"],
            "title": r["metadata"]["title"],
            "media_type": r["metadata"].get("media_type", "manga"),
            "score": r["metadata"].get("score", 0),
            "genres": r["metadata"].get("genres", ""),
            "image_url": r["metadata"].get("image_url", ""),
            "volumes": r["metadata"].get("volumes", 0),
            "similarity": round(r["similarity"], 3)
        })
    
    return {
        "query": q,
        "count": len(formatted),
        "results": formatted
    }


@router.get("/{mal_id}")
async def get_manga(mal_id: int):
    """Get manga details by MAL ID"""
    store = get_manga_vector_store_safe()

    if store:
        try:
            # Try to get from vector store first
            result = store.collection.get(
                ids=[str(mal_id)],
                include=["metadatas"]
            )

            if result["ids"]:
                meta = result["metadatas"][0]
                return {
                    "mal_id": mal_id,
                    "title": meta.get("title", "Unknown"),
                    "media_type": meta.get("media_type", "manga"),
                    "score": meta.get("score", 0),
                    "rank": meta.get("rank", 0),
                    "members": meta.get("members", 0),
                    "volumes": meta.get("volumes", 0),
                    "genres": meta.get("genres", "").split(", ") if meta.get("genres") else [],
                    "authors": meta.get("authors", "").split(", ") if meta.get("authors") else [],
                    "image_url": meta.get("image_url", ""),
                    "published": meta.get("published", ""),
                }
        except Exception as e:
            print(f"Manga detail vector lookup failed, using CSV fallback: {e}")

    manga = find_manga_in_dataset(mal_id)
    if manga:
        return manga_detail_response(manga)
    
    raise HTTPException(status_code=404, detail="Manga not found")


@router.get("/{mal_id}/similar")
async def get_similar_manga(
    mal_id: int,
    limit: int = Query(10, ge=1, le=50)
):
    """Find manga similar to a given manga"""
    store = get_manga_vector_store_safe()
    if not store:
        return {
            "results": [],
            "note": "Similarity search requires a compatible manga vector store."
        }

    try:
        results = store.search_similar(mal_id=mal_id, n_results=limit)
    except Exception as e:
        print(f"Manga similarity search failed: {e}")
        results = []
    
    if not results:
        raise HTTPException(status_code=404, detail="Manga not found or no similar manga")
    
    formatted = []
    for r in results:
        formatted.append({
            "mal_id": r["mal_id"],
            "title": r["metadata"]["title"],
            "media_type": r["metadata"].get("media_type", "manga"),
            "score": r["metadata"].get("score", 0),
            "genres": r["metadata"].get("genres", ""),
            "image_url": r["metadata"].get("image_url", ""),
            "similarity": round(r["similarity"], 3)
        })
    
    return {"results": formatted}


@router.get("")
async def list_manga(
    limit: int = Query(30, ge=1, le=100),
    offset: int = Query(0, ge=0),
    sort_by: str = Query("score", pattern="^(score|rank|members)$"),
    order: str = Query("desc", pattern="^(asc|desc)$"),
    min_score: Optional[float] = Query(None, ge=0, le=10),
    media_type: Optional[str] = None
):
    """List manga with filters"""
    store = get_manga_vector_store_safe()

    manga_list = []
    if store:
        try:
            # Get all manga from store
            all_results = store.collection.get(
                include=["metadatas"],
                limit=1000
            )

            for i, mal_id in enumerate(all_results["ids"]):
                meta = all_results["metadatas"][i]

                # Apply filters
                if min_score and (meta.get("score", 0) or 0) < min_score:
                    continue
                if media_type and meta.get("media_type") != media_type:
                    continue

                manga_list.append({
                    "mal_id": int(mal_id),
                    "title": meta.get("title", "Unknown"),
                    "media_type": meta.get("media_type", "manga"),
                    "score": meta.get("score", 0),
                    "rank": meta.get("rank", 0),
                    "members": meta.get("members", 0),
                    "volumes": meta.get("volumes", 0),
                    "genres": meta.get("genres", ""),
                    "image_url": meta.get("image_url", ""),
                })
        except Exception as e:
            print(f"Manga vector list failed, using CSV fallback: {e}")
            manga_list = []

    if not manga_list:
        for _, row in get_manga_df().iterrows():
            manga = parse_manga_row(row)
            if min_score and (manga.score or 0) < min_score:
                continue
            if media_type and manga.media_type != media_type:
                continue
            manga_list.append(manga_summary_response(manga))
    
    # Sort
    reverse = order == "desc"
    if sort_by == "rank":
        reverse = not reverse  # Lower rank is better
    
    manga_list.sort(key=lambda x: x.get(sort_by, 0) or 0, reverse=reverse)
    
    # Paginate
    paginated = manga_list[offset:offset + limit]
    
    return {
        "total": len(manga_list),
        "offset": offset,
        "limit": limit,
        "results": paginated
    }
