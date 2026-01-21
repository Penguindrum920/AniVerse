"""Search API Routes"""
from fastapi import APIRouter, Query
from typing import Optional
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from embeddings.chroma_store import get_vector_store
from data.anime_schema import AnimeSearchResult

router = APIRouter(prefix="/api/search", tags=["Search"])


@router.get("")
async def semantic_search(
    q: str = Query(..., min_length=1, description="Search query"),
    limit: int = Query(10, ge=1, le=50, description="Number of results"),
    genre: Optional[str] = Query(None, description="Filter by genre"),
    min_score: Optional[float] = Query(None, ge=0, le=10, description="Minimum score"),
    media_type: Optional[str] = Query(None, description="Filter by media type (tv, movie, ova, etc.)"),
):
    """
    Semantic search for anime.
    
    Uses vector similarity to find anime matching the query meaning,
    not just keyword matching.
    """
    store = get_vector_store()
    
    # Build filter
    where = {}
    if genre:
        where["genres"] = {"$contains": genre}
    if media_type:
        where["media_type"] = media_type
    
    # Search
    results = store.search(
        query=q,
        n_results=limit,
        where=where if where else None
    )
    
    # Filter by score if specified (post-filter since ChromaDB doesn't support numeric comparison well)
    if min_score:
        results = [r for r in results if r["metadata"].get("score", 0) >= min_score]
    
    return {
        "query": q,
        "count": len(results),
        "results": [
            {
                "mal_id": r["mal_id"],
                "title": r["metadata"]["title"],
                "score": r["metadata"]["score"],
                "genres": r["metadata"]["genres"],
                "media_type": r["metadata"]["media_type"],
                "image_url": r["metadata"]["image_url"],
                "similarity": round(r["similarity"], 4),
            }
            for r in results
        ]
    }


@router.get("/similar/{mal_id}")
async def find_similar(
    mal_id: int,
    limit: int = Query(10, ge=1, le=50, description="Number of results"),
):
    """Find anime similar to a given anime by MAL ID"""
    store = get_vector_store()
    
    results = store.search_similar(mal_id=mal_id, n_results=limit)
    
    if not results:
        return {"error": f"Anime with ID {mal_id} not found", "results": []}
    
    return {
        "source_id": mal_id,
        "count": len(results),
        "results": [
            {
                "mal_id": r["mal_id"],
                "title": r["metadata"]["title"],
                "score": r["metadata"]["score"],
                "genres": r["metadata"]["genres"],
                "similarity": round(r["similarity"], 4),
                "image_url": r["metadata"]["image_url"],
            }
            for r in results
        ]
    }
