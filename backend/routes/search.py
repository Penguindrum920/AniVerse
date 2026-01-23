"""Search API Routes - With fallback text search"""
from fastapi import APIRouter, Query
from typing import Optional
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from data.anime_schema import AnimeSearchResult

router = APIRouter(prefix="/api/search", tags=["Search"])

# Global flag for vector store availability
_vector_store = None
_vector_store_error = None


def get_vector_store_safe():
    """Try to get vector store, return None if failed"""
    global _vector_store, _vector_store_error
    
    if _vector_store_error:
        return None
    
    if _vector_store is None:
        try:
            from embeddings.chroma_store import get_vector_store
            _vector_store = get_vector_store()
        except Exception as e:
            print(f"Vector store unavailable, using text search fallback: {e}")
            _vector_store_error = str(e)
            return None
    
    return _vector_store


def text_search_fallback(query: str, limit: int = 10, genre: str = None, 
                         min_score: float = None, media_type: str = None):
    """Simple text-based search fallback when ChromaDB is unavailable"""
    from data.data_loader import load_anime_dataset
    
    df = load_anime_dataset()
    
    # Convert query to lowercase for case-insensitive search
    query_lower = query.lower()
    query_words = query_lower.split()
    
    # Search in title and synopsis
    def match_score(row):
        score = 0
        title = str(row.get('title', '')).lower()
        synopsis = str(row.get('synopsis', '')).lower()
        genres = str(row.get('genres', '')).lower()
        
        # Title matches are worth more
        for word in query_words:
            if word in title:
                score += 10
            if word in synopsis:
                score += 1
            if word in genres:
                score += 5
        
        return score
    
    # Add match scores
    df['match_score'] = df.apply(match_score, axis=1)
    
    # Filter by score > 0 (has matches)
    results_df = df[df['match_score'] > 0].copy()
    
    # Apply filters
    if genre:
        results_df = results_df[results_df['genres'].str.contains(genre, case=False, na=False)]
    if min_score:
        results_df = results_df[results_df['score'] >= min_score]
    if media_type:
        results_df = results_df[results_df['media_type'].str.lower() == media_type.lower()]
    
    # Sort by match score, then by anime score
    results_df = results_df.sort_values(['match_score', 'score'], ascending=[False, False])
    
    # Limit results
    results_df = results_df.head(limit)
    
    # Format results
    results = []
    for _, row in results_df.iterrows():
        results.append({
            "mal_id": int(row['mal_id']),
            "metadata": {
                "title": row.get('title', ''),
                "score": row.get('score', 0) or 0,
                "genres": row.get('genres', ''),
                "media_type": row.get('media_type', ''),
                "image_url": row.get('image_url', ''),
            },
            "similarity": row['match_score'] / 100  # Normalize
        })
    
    return results


@router.get("")
async def semantic_search(
    q: str = Query(..., min_length=1, description="Search query"),
    limit: int = Query(10, ge=1, le=50, description="Number of results"),
    genre: Optional[str] = Query(None, description="Filter by genre"),
    min_score: Optional[float] = Query(None, ge=0, le=10, description="Minimum score"),
    media_type: Optional[str] = Query(None, description="Filter by media type (tv, movie, ova, etc.)"),
):
    """Search for anime - uses vector search if available, fallback to text search"""
    
    store = get_vector_store_safe()
    
    if store:
        # Use vector search
        try:
            where = {}
            if genre:
                where["genres"] = {"$contains": genre}
            if media_type:
                where["media_type"] = media_type
            
            results = store.search(
                query=q,
                n_results=limit,
                where=where if where else None
            )
            
            if min_score:
                results = [r for r in results if r["metadata"].get("score", 0) >= min_score]
        except Exception as e:
            print(f"Vector search failed, using fallback: {e}")
            results = text_search_fallback(q, limit, genre, min_score, media_type)
    else:
        # Use text search fallback
        results = text_search_fallback(q, limit, genre, min_score, media_type)
    
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
                "similarity": round(r.get("similarity", 0), 4),
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
    store = get_vector_store_safe()
    
    if store:
        try:
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
        except Exception as e:
            print(f"Similar search failed: {e}")
    
    # Fallback: return empty results
    return {
        "source_id": mal_id,
        "count": 0,
        "results": [],
        "note": "Similarity search requires vector database which is currently unavailable"
    }
