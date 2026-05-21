"""Search API Routes - With fallback text search"""
from fastapi import APIRouter, Query
from typing import Optional
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from data.anime_schema import AnimeSearchResult
from providers.live_anime import anime_to_search_result, get_live_anime, index_live_anime, search_live_anime

router = APIRouter(prefix="/api/search", tags=["Search"])

# Global flag for vector store availability
_vector_store = None
_vector_store_error = None
_retrieval_model = None
_retrieval_model_error = None


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


def get_retrieval_model_safe():
    """Get the local trained retrieval model, returning None if it fails."""
    global _retrieval_model, _retrieval_model_error

    if _retrieval_model_error:
        return None

    if _retrieval_model is None:
        try:
            from embeddings.local_retrieval_model import get_anime_retrieval_model
            _retrieval_model = get_anime_retrieval_model()
        except Exception as e:
            print(f"Local retrieval model unavailable, using text fallback: {e}")
            _retrieval_model_error = str(e)
            return None

    return _retrieval_model


def text_search_fallback(query: str, limit: int = 10, genre: str = None, 
                         min_score: float = None, media_type: str = None):
    """Simple text-based search fallback when ChromaDB is unavailable"""
    from data.data_loader import load_anime_dataset
    
    try:
        df = load_anime_dataset()
    except Exception as e:
        print(f"Text search fallback unavailable: {e}")
        return []
    
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


def merge_results(primary: list[dict], live: list[dict], limit: int) -> list[dict]:
    """Deduplicate search results while preserving provider coverage."""
    merged = []
    seen = set()

    for result in primary + live:
        mal_id = result.get("mal_id")
        if mal_id in seen:
            continue
        seen.add(mal_id)
        merged.append(result)
        if len(merged) >= limit:
            break

    return merged


@router.get("")
async def semantic_search(
    q: str = Query(..., min_length=1, description="Search query"),
    limit: int = Query(10, ge=1, le=50, description="Number of results"),
    genre: Optional[str] = Query(None, description="Filter by genre"),
    min_score: Optional[float] = Query(None, ge=0, le=10, description="Minimum score"),
    media_type: Optional[str] = Query(None, description="Filter by media type (tv, movie, ova, etc.)"),
):
    """Search anime with local semantic results plus live AniList/Jikan coverage."""
    
    store = None
    results = []

    model = get_retrieval_model_safe()
    if model:
        results = model.search(
            query=q,
            n_results=limit,
            genre=genre,
            min_score=min_score,
            media_type=media_type,
        )

    if not results:
        store = get_vector_store_safe()
        if store:
            # Use legacy vector search only when the trained local model is unavailable.
            try:
                where = {}
                if genre:
                    where["genres"] = {"$contains": genre}
                if media_type:
                    where["media_type"] = media_type

                results = store.search(
                    query=q,
                    n_results=limit,
                    where=where if where else None,
                )

                if min_score:
                    results = [r for r in results if r["metadata"].get("score", 0) >= min_score]
            except Exception as e:
                print(f"Vector search failed, using text fallback: {e}")
                results = []

    if not results:
        # Use text search fallback
        results = text_search_fallback(q, limit, genre, min_score, media_type)

    live_anime = await search_live_anime(
        query=q,
        limit=limit,
        genre=genre,
        min_score=min_score,
        media_type=media_type,
    )
    live_results = []
    for index, anime in enumerate(live_anime):
        if store:
            index_live_anime(anime, store=store)
        live_results.append(anime_to_search_result(anime, similarity=max(0.5, 0.98 - index * 0.02)))

    results = merge_results(results, live_results, limit)
    
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
    results = []

    model = get_retrieval_model_safe()
    if model:
        results = model.search_similar(mal_id=mal_id, n_results=limit)

    if not results:
        store = get_vector_store_safe()
        if store:
            try:
                results = store.search_similar(mal_id=mal_id, n_results=limit)

                if not results:
                    live_anime = await get_live_anime(mal_id)
                    if live_anime:
                        index_live_anime(live_anime, store=store)
                        results = store.search_similar(mal_id=mal_id, n_results=limit)

            except Exception as e:
                print(f"Similar search failed: {e}")

    if not results and model:
        try:
            live_anime = await get_live_anime(mal_id)
            if live_anime:
                results = model.search(query=live_anime.get("title", ""), n_results=limit)
        except Exception as e:
            print(f"Live similar fallback failed: {e}")

    if results:
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

    # Fallback: return empty results
    return {
        "source_id": mal_id,
        "count": 0,
        "results": [],
        "note": "Similarity search requires a trained local retrieval model or compatible vector database"
    }
