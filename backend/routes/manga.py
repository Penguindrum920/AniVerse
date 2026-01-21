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


def get_manga_df():
    """Get or load manga dataframe"""
    global _manga_df
    if _manga_df is None:
        _manga_df = load_manga_dataset()
    return _manga_df


@router.get("/search")
async def search_manga(
    q: str = Query(..., min_length=1, description="Search query"),
    limit: int = Query(20, ge=1, le=100, description="Number of results")
):
    """Semantic search for manga"""
    store = get_manga_vector_store()
    
    results = store.search(query=q, n_results=limit)
    
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
    store = get_manga_vector_store()
    
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
    
    raise HTTPException(status_code=404, detail="Manga not found")


@router.get("/{mal_id}/similar")
async def get_similar_manga(
    mal_id: int,
    limit: int = Query(10, ge=1, le=50)
):
    """Find manga similar to a given manga"""
    store = get_manga_vector_store()
    
    results = store.search_similar(mal_id=mal_id, n_results=limit)
    
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
    store = get_manga_vector_store()
    
    # Get all manga from store
    all_results = store.collection.get(
        include=["metadatas"],
        limit=1000
    )
    
    manga_list = []
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
