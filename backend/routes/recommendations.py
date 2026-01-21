"""Personalized Recommendations API Routes"""
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import List, Optional
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from data.database import get_db, User, UserAnime, AnimeStatus
from routes.auth import require_user, get_current_user
from embeddings.chroma_store import get_vector_store
from embeddings.search_utils import rerank_results
from sqlalchemy.orm import Session

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


@router.get("", response_model=RecommendationsResponse)
async def get_personalized_recommendations(
    limit: int = 10,
    user: User = Depends(require_user),
    db: Session = Depends(get_db)
):
    """
    Get personalized recommendations based on user's highly-rated anime.
    
    Finds anime similar to what the user rated 8+ or marked as favorites.
    """
    # Get user's highly rated anime (8+) and favorites
    high_rated = db.query(UserAnime).filter(
        UserAnime.user_id == user.id,
        (UserAnime.rating >= 8) | (UserAnime.is_favorite == 1)
    ).order_by(UserAnime.rating.desc()).limit(5).all()
    
    if not high_rated:
        # Fallback: get any completed anime
        high_rated = db.query(UserAnime).filter(
            UserAnime.user_id == user.id,
            UserAnime.status == AnimeStatus.completed
        ).limit(3).all()
    
    if not high_rated:
        raise HTTPException(
            status_code=400,
            detail="Add some anime to your list and rate them to get personalized recommendations!"
        )
    
    # Get all anime IDs in user's list (to exclude from recommendations)
    user_anime_ids = {
        item.anime_id for item in 
        db.query(UserAnime).filter(UserAnime.user_id == user.id).all()
    }
    
    store = get_vector_store()
    all_recommendations = []
    based_on = []
    
    # Find similar anime for each highly rated anime
    for entry in high_rated:
        similar = store.search_similar(mal_id=entry.anime_id, n_results=10)
        
        # Get the source anime info
        source_result = store.collection.get(
            ids=[str(entry.anime_id)],
            include=["metadatas"]
        )
        source_title = "Unknown"
        if source_result["metadatas"]:
            source_title = source_result["metadatas"][0].get("title", "Unknown")
            based_on.append({
                "anime_id": entry.anime_id,
                "title": source_title,
                "rating": entry.rating,
                "is_favorite": bool(entry.is_favorite)
            })
        
        for s in similar:
            # Skip if already in user's list
            if s["mal_id"] in user_anime_ids:
                continue
            
            all_recommendations.append({
                **s,
                "source_title": source_title,
                "source_id": entry.anime_id
            })
    
    # Deduplicate and rerank
    seen = set()
    unique_recs = []
    for r in all_recommendations:
        if r["mal_id"] not in seen:
            seen.add(r["mal_id"])
            unique_recs.append(r)
    
    reranked = rerank_results(unique_recs, limit=limit)
    
    return RecommendationsResponse(
        based_on=based_on,
        recommendations=[
            RecommendationItem(
                mal_id=r["mal_id"],
                title=r["metadata"]["title"],
                score=r["metadata"]["score"] or 0,
                genres=r["metadata"]["genres"],
                image_url=r["metadata"]["image_url"] or "",
                similarity=round(r["similarity"], 3),
                reason=f"Because you liked {r.get('source_title', 'similar anime')}"
            )
            for r in reranked
        ]
    )


@router.get("/quick")
async def get_quick_recommendations(
    anime_id: int,
    limit: int = 5,
    user: Optional[User] = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get quick recommendations based on a single anime.
    Works for both authenticated and anonymous users.
    """
    store = get_vector_store()
    similar = store.search_similar(mal_id=anime_id, n_results=limit + 10)
    
    # If user is logged in, filter out anime in their list
    if user:
        user_anime_ids = {
            item.anime_id for item in 
            db.query(UserAnime).filter(UserAnime.user_id == user.id).all()
        }
        similar = [s for s in similar if s["mal_id"] not in user_anime_ids]
    
    return {
        "source_id": anime_id,
        "recommendations": [
            {
                "mal_id": s["mal_id"],
                "title": s["metadata"]["title"],
                "score": s["metadata"]["score"],
                "genres": s["metadata"]["genres"],
                "image_url": s["metadata"]["image_url"],
                "similarity": round(s["similarity"], 3)
            }
            for s in similar[:limit]
        ]
    }
