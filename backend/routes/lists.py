"""User Anime Lists API Routes"""
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from data.database import get_db, User, UserAnime, UserManga, AnimeStatus
from routes.auth import require_user
from sqlalchemy.orm import Session

router = APIRouter(prefix="/api/lists", tags=["User Lists"])


# Request/Response Models
class AddToListRequest(BaseModel):
    anime_id: int
    status: str = Field(default="planned", pattern="^(watching|completed|planned|dropped|on_hold)$")
    rating: Optional[float] = Field(None, ge=1, le=10)
    is_favorite: bool = False


class AddMangaToListRequest(BaseModel):
    manga_id: int
    status: str = Field(default="planned", pattern="^(watching|completed|planned|dropped|on_hold)$")
    rating: Optional[float] = Field(None, ge=1, le=10)
    is_favorite: bool = False


class UpdateListRequest(BaseModel):
    status: Optional[str] = Field(None, pattern="^(watching|completed|planned|dropped|on_hold)$")
    rating: Optional[float] = Field(None, ge=1, le=10)
    is_favorite: Optional[bool] = None


class AnimeListItem(BaseModel):
    anime_id: int
    status: str
    rating: Optional[float]
    is_favorite: bool
    added_at: datetime
    updated_at: datetime


class ListResponse(BaseModel):
    status: str
    count: int
    items: List[AnimeListItem]


class MangaListItem(BaseModel):
    manga_id: int
    status: str
    rating: Optional[float]
    is_favorite: bool
    added_at: datetime
    updated_at: datetime


class MangaListResponse(BaseModel):
    status: str
    count: int
    items: List[MangaListItem]


class UserStatsResponse(BaseModel):
    total_anime: int
    watching: int
    completed: int
    planned: int
    dropped: int
    on_hold: int
    favorites: int
    average_rating: Optional[float]


# Routes
@router.post("/add")
async def add_to_list(
    request: AddToListRequest,
    user: User = Depends(require_user),
    db: Session = Depends(get_db)
):
    """Add an anime to user's list"""
    # Check if already in list
    existing = db.query(UserAnime).filter(
        UserAnime.user_id == user.id,
        UserAnime.anime_id == request.anime_id
    ).first()
    
    if existing:
        # Update existing entry
        existing.status = AnimeStatus(request.status)
        if request.rating is not None:
            existing.rating = request.rating
        existing.is_favorite = 1 if request.is_favorite else 0
        existing.updated_at = datetime.utcnow()
        db.commit()
        return {"message": "Anime list updated", "anime_id": request.anime_id}
    
    # Create new entry
    entry = UserAnime(
        user_id=user.id,
        anime_id=request.anime_id,
        status=AnimeStatus(request.status),
        rating=request.rating,
        is_favorite=1 if request.is_favorite else 0
    )
    db.add(entry)
    db.commit()
    
    return {"message": "Anime added to list", "anime_id": request.anime_id}


@router.get("/{status}", response_model=ListResponse)
async def get_list_by_status(
    status: str,
    user: User = Depends(require_user),
    db: Session = Depends(get_db)
):
    """Get user's anime list filtered by status"""
    if status == "favorites":
        items = db.query(UserAnime).filter(
            UserAnime.user_id == user.id,
            UserAnime.is_favorite == 1
        ).all()
    elif status == "all":
        items = db.query(UserAnime).filter(UserAnime.user_id == user.id).all()
    else:
        try:
            status_enum = AnimeStatus(status)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid status: {status}")
        
        items = db.query(UserAnime).filter(
            UserAnime.user_id == user.id,
            UserAnime.status == status_enum
        ).all()
    
    return ListResponse(
        status=status,
        count=len(items),
        items=[
            AnimeListItem(
                anime_id=item.anime_id,
                status=item.status.value,
                rating=item.rating,
                is_favorite=bool(item.is_favorite),
                added_at=item.added_at,
                updated_at=item.updated_at
            )
            for item in items
        ]
    )


@router.patch("/{anime_id}")
async def update_list_entry(
    anime_id: int,
    request: UpdateListRequest,
    user: User = Depends(require_user),
    db: Session = Depends(get_db)
):
    """Update an anime in user's list"""
    entry = db.query(UserAnime).filter(
        UserAnime.user_id == user.id,
        UserAnime.anime_id == anime_id
    ).first()
    
    if not entry:
        raise HTTPException(status_code=404, detail="Anime not in your list")
    
    if request.status is not None:
        entry.status = AnimeStatus(request.status)
    if request.rating is not None:
        entry.rating = request.rating
    if request.is_favorite is not None:
        entry.is_favorite = 1 if request.is_favorite else 0
    
    entry.updated_at = datetime.utcnow()
    db.commit()
    
    return {"message": "List entry updated", "anime_id": anime_id}


@router.delete("/{anime_id}")
async def remove_from_list(
    anime_id: int,
    user: User = Depends(require_user),
    db: Session = Depends(get_db)
):
    """Remove an anime from user's list"""
    entry = db.query(UserAnime).filter(
        UserAnime.user_id == user.id,
        UserAnime.anime_id == anime_id
    ).first()
    
    if not entry:
        raise HTTPException(status_code=404, detail="Anime not in your list")
    
    db.delete(entry)
    db.commit()
    
    return {"message": "Anime removed from list", "anime_id": anime_id}


@router.get("/stats/me", response_model=UserStatsResponse)
async def get_user_stats(
    user: User = Depends(require_user),
    db: Session = Depends(get_db)
):
    """Get user's anime list statistics"""
    all_items = db.query(UserAnime).filter(UserAnime.user_id == user.id).all()
    
    stats = {
        "total_anime": len(all_items),
        "watching": 0,
        "completed": 0,
        "planned": 0,
        "dropped": 0,
        "on_hold": 0,
        "favorites": 0,
    }
    
    ratings = []
    for item in all_items:
        stats[item.status.value] = stats.get(item.status.value, 0) + 1
        if item.is_favorite:
            stats["favorites"] += 1
        if item.rating:
            ratings.append(item.rating)
    
    avg_rating = sum(ratings) / len(ratings) if ratings else None
    
    return UserStatsResponse(
        **stats,
        average_rating=round(avg_rating, 2) if avg_rating else None
    )


# --- Manga List Routes ---

@router.post("/manga/add")
async def add_manga_to_list(
    request: AddMangaToListRequest,
    user: User = Depends(require_user),
    db: Session = Depends(get_db)
):
    """Add a manga to user's list"""
    # Check if already in list
    existing = db.query(UserManga).filter(
        UserManga.user_id == user.id,
        UserManga.manga_id == request.manga_id
    ).first()
    
    if existing:
        # Update existing entry
        existing.status = AnimeStatus(request.status)
        if request.rating is not None:
            existing.rating = request.rating
        existing.is_favorite = 1 if request.is_favorite else 0
        existing.updated_at = datetime.utcnow()
        db.commit()
        return {"message": "Manga list updated", "manga_id": request.manga_id}
    
    # Create new entry
    entry = UserManga(
        user_id=user.id,
        manga_id=request.manga_id,
        status=AnimeStatus(request.status),
        rating=request.rating,
        is_favorite=1 if request.is_favorite else 0
    )
    db.add(entry)
    db.commit()
    
    return {"message": "Manga added to list", "manga_id": request.manga_id}


@router.get("/manga/{status}", response_model=MangaListResponse)
async def get_manga_list_by_status(
    status: str,
    user: User = Depends(require_user),
    db: Session = Depends(get_db)
):
    """Get user's manga list filtered by status"""
    if status == "favorites":
        items = db.query(UserManga).filter(
            UserManga.user_id == user.id,
            UserManga.is_favorite == 1
        ).all()
    elif status == "all":
        items = db.query(UserManga).filter(UserManga.user_id == user.id).all()
    else:
        try:
            status_enum = AnimeStatus(status)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid status: {status}")
        
        items = db.query(UserManga).filter(
            UserManga.user_id == user.id,
            UserManga.status == status_enum
        ).all()
    
    return MangaListResponse(
        status=status,
        count=len(items),
        items=[
            MangaListItem(
                manga_id=item.manga_id,
                status=item.status.value,
                rating=item.rating,
                is_favorite=bool(item.is_favorite),
                added_at=item.added_at,
                updated_at=item.updated_at
            )
            for item in items
        ]
    )


@router.patch("/manga/{manga_id}")
async def update_manga_list_entry(
    manga_id: int,
    request: UpdateListRequest,
    user: User = Depends(require_user),
    db: Session = Depends(get_db)
):
    """Update a manga in user's list"""
    entry = db.query(UserManga).filter(
        UserManga.user_id == user.id,
        UserManga.manga_id == manga_id
    ).first()
    
    if not entry:
        raise HTTPException(status_code=404, detail="Manga not in your list")
    
    if request.status is not None:
        entry.status = AnimeStatus(request.status)
    if request.rating is not None:
        entry.rating = request.rating
    if request.is_favorite is not None:
        entry.is_favorite = 1 if request.is_favorite else 0
    
    entry.updated_at = datetime.utcnow()
    db.commit()
    
    return {"message": "Manga list entry updated", "manga_id": manga_id}


@router.delete("/manga/{manga_id}")
async def remove_manga_from_list(
    manga_id: int,
    user: User = Depends(require_user),
    db: Session = Depends(get_db)
):
    """Remove a manga from user's list"""
    entry = db.query(UserManga).filter(
        UserManga.user_id == user.id,
        UserManga.manga_id == manga_id
    ).first()
    
    if not entry:
        raise HTTPException(status_code=404, detail="Manga not in your list")
    
    db.delete(entry)
    db.commit()
    
    return {"message": "Manga removed from list", "manga_id": manga_id}

