"""Anime Detail API Routes"""
from fastapi import APIRouter, HTTPException, Query
import pandas as pd
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import DATASET_PATH
from data.anime_schema import Anime, parse_list_field
from embeddings.chroma_store import get_vector_store

router = APIRouter(prefix="/api/anime", tags=["Anime"])

# Load dataset into memory for fast lookups
_df = None


def get_dataframe():
    global _df
    if _df is None:
        _df = pd.read_csv(DATASET_PATH)
        _df = _df.rename(columns={
            "id": "mal_id",
            "mean": "score",
            "num_scoring_users": "scored_by",
            "num_favorites": "favorites",
            "main_picture_medium": "image_url",
            "alternative_titles_en": "title_english",
            "alternative_titles_ja": "title_japanese",
        })
    return _df


@router.get("/{mal_id}")
async def get_anime(mal_id: int):
    """Get detailed information for a specific anime"""
    df = get_dataframe()
    
    row = df[df["mal_id"] == mal_id]
    if row.empty:
        raise HTTPException(status_code=404, detail=f"Anime with ID {mal_id} not found")
    
    row = row.iloc[0]
    
    return {
        "mal_id": int(row["mal_id"]),
        "title": row["title"],
        "title_english": row.get("title_english") if pd.notna(row.get("title_english")) else None,
        "title_japanese": row.get("title_japanese") if pd.notna(row.get("title_japanese")) else None,
        "media_type": row.get("media_type", "unknown"),
        "episodes": int(row["num_episodes"]) if pd.notna(row.get("num_episodes")) else None,
        "status": row.get("status", "unknown"),
        "score": float(row["score"]) if pd.notna(row.get("score")) else None,
        "scored_by": int(row["scored_by"]) if pd.notna(row.get("scored_by")) else None,
        "rank": int(row["rank"]) if pd.notna(row.get("rank")) else None,
        "popularity": int(row["popularity"]) if pd.notna(row.get("popularity")) else None,
        "favorites": int(row["favorites"]) if pd.notna(row.get("favorites")) else None,
        "synopsis": row.get("synopsis") if pd.notna(row.get("synopsis")) else None,
        "genres": parse_list_field(row.get("genres", "[]")),
        "studios": parse_list_field(row.get("studios", "[]")),
        "source": row.get("source") if pd.notna(row.get("source")) else None,
        "rating": row.get("rating") if pd.notna(row.get("rating")) else None,
        "image_url": row.get("image_url") if pd.notna(row.get("image_url")) else None,
        "start_date": str(row.get("start_date")) if pd.notna(row.get("start_date")) else None,
        "end_date": str(row.get("end_date")) if pd.notna(row.get("end_date")) else None,
    }


@router.get("/{mal_id}/similar")
async def get_similar_anime(
    mal_id: int,
    limit: int = Query(10, ge=1, le=50)
):
    """Get anime similar to the specified anime"""
    store = get_vector_store()
    
    results = store.search_similar(mal_id=mal_id, n_results=limit)
    
    if not results:
        raise HTTPException(status_code=404, detail=f"Anime with ID {mal_id} not found in vector store")
    
    return {
        "source_id": mal_id,
        "similar": [
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


@router.get("")
async def list_anime(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    sort_by: str = Query("score", regex="^(score|popularity|rank|favorites|members|scored_by)$"),
    order: str = Query("desc", regex="^(asc|desc)$"),
    genre: str = Query(None),
    media_type: str = Query(None),
    min_score: float = Query(None, ge=0, le=10),
):
    """List anime with pagination, sorting, and filters"""
    df = get_dataframe()
    
    # Apply filters
    if genre:
        df = df[df["genres"].str.contains(genre, case=False, na=False)]
    if media_type:
        df = df[df["media_type"] == media_type]
    if min_score:
        df = df[df["score"] >= min_score]
    
    # Sort
    ascending = order == "asc"
    df = df.sort_values(by=sort_by, ascending=ascending, na_position="last")
    
    # Paginate
    total = len(df)
    start = (page - 1) * limit
    end = start + limit
    df_page = df.iloc[start:end]
    
    return {
        "page": page,
        "limit": limit,
        "total": total,
        "pages": (total + limit - 1) // limit,
        "results": [
            {
                "mal_id": int(row["mal_id"]),
                "title": row["title"],
                "score": float(row["score"]) if pd.notna(row["score"]) else None,
                "genres": parse_list_field(row.get("genres", "[]")),
                "media_type": row.get("media_type"),
                "image_url": row.get("image_url") if pd.notna(row.get("image_url")) else None,
            }
            for _, row in df_page.iterrows()
        ]
    }
