"""Chat API Routes - Agentic AI with List Actions"""
from fastapi import APIRouter, HTTPException, Depends, Header
from pydantic import BaseModel, Field
from typing import Optional
import re
import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))
from embeddings.chroma_store import get_vector_store
from embeddings.manga_chroma_store import get_manga_vector_store
from embeddings.search_utils import rerank_results, detect_genres_from_query
from llm.groq_client import get_llm_client
from config import GROQ_API_KEY
from data.database import get_db, User, UserAnime, UserManga, AnimeStatus
from routes.auth import get_current_user
from sqlalchemy.orm import Session

router = APIRouter(prefix="/api/chat", tags=["Chat"])


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=1000)
    history: list[dict] = Field(default_factory=list)
    use_context: bool = Field(default=True)


class ActionResult(BaseModel):
    action: str
    success: bool
    message: str
    anime_id: Optional[int] = None
    anime_title: Optional[str] = None


class ChatResponse(BaseModel):
    reply: str
    context_anime: list[dict] = []
    actions_taken: list[ActionResult] = []


# Action patterns for agentic behavior
ACTION_PATTERNS = {
    "add_completed": r"(?:add|mark|set|put)\s+(.+?)\s+(?:to|as|in)\s+(?:my\s+)?completed(?:\s+list)?(?:\s+with\s+(?:a\s+)?rating\s+(?:of\s+)?(\d+(?:\.\d+)?))?",
    "add_watching": r"(?:add|mark|set|put)\s+(.+?)\s+(?:to|as|in)\s+(?:my\s+)?(?:watching|currently watching)(?:\s+list)?",
    "add_planned": r"(?:add|mark|set|put)\s+(.+?)\s+(?:to|as|in)\s+(?:my\s+)?(?:plan(?:ned)?(?:\s+to\s+watch)?|watchlist|ptw)(?:\s+list)?",
    "add_dropped": r"(?:add|mark|set|put)\s+(.+?)\s+(?:to|as|in)\s+(?:my\s+)?dropped(?:\s+list)?",
    "add_on_hold": r"(?:add|mark|set|put)\s+(.+?)\s+(?:to|as|in)\s+(?:my\s+)?(?:on[\s_-]?hold|paused)(?:\s+list)?",
    "rate_anime": r"(?:rate|give|score)\s+(.+?)\s+(?:a\s+)?(\d+(?:\.\d+)?)\s*(?:out of 10|/10|stars?)?",
    "change_rating": r"(?:change|update|set)\s+(?:the\s+)?rating\s+(?:of\s+)?(.+?)\s+to\s+(\d+(?:\.\d+)?)",
    "remove_anime": r"(?:remove|delete|take off)\s+(.+?)\s+(?:from\s+(?:my\s+)?(?:list|watchlist|anime list))",
}

# Manga-specific action patterns
MANGA_ACTION_PATTERNS = {
    "add_manga_completed": r"(?:add|mark|set|put)\s+(.+?)\s+(?:manga\s+)?(?:to|as|in)\s+(?:my\s+)?(?:manga\s+)?completed(?:\s+list)?(?:\s+with\s+(?:a\s+)?rating\s+(?:of\s+)?(\d+(?:\.\d+)?))?",
    "add_manga_reading": r"(?:add|mark|set|put)\s+(.+?)\s+(?:manga\s+)?(?:to|as|in)\s+(?:my\s+)?(?:manga\s+)?(?:reading|currently reading)(?:\s+list)?",
    "add_manga_planned": r"(?:add|mark|set|put)\s+(.+?)\s+(?:manga\s+)?(?:to|as|in)\s+(?:my\s+)?(?:manga\s+)?(?:plan(?:ned)?(?:\s+to\s+read)?|ptr)(?:\s+list)?",
    "rate_manga": r"(?:rate|give|score)\s+(.+?)\s+(?:manga\s+)?(?:a\s+)?(\d+(?:\.\d+)?)\s*(?:out of 10|/10|stars?)?",
    "remove_manga": r"(?:remove|delete|take off)\s+(.+?)\s+(?:manga\s+)?(?:from\s+(?:my\s+)?(?:manga\s+)?(?:list|reading list))",
}


def find_anime_by_title(title: str) -> Optional[dict]:
    """Find anime in vector store by title search"""
    store = get_vector_store()
    results = store.search(query=title, n_results=5)
    
    if not results:
        return None
    
    # Find best match (title contains search or vice versa)
    title_lower = title.lower().strip()
    for r in results:
        anime_title = r["metadata"]["title"].lower()
        if title_lower in anime_title or anime_title in title_lower:
            return {
                "mal_id": r["mal_id"],
                "title": r["metadata"]["title"],
                "score": r["metadata"]["score"],
                "genres": r["metadata"]["genres"]
            }
    
    # Return first result if no exact match
    return {
        "mal_id": results[0]["mal_id"],
        "title": results[0]["metadata"]["title"],
        "score": results[0]["metadata"]["score"],
        "genres": results[0]["metadata"]["genres"]
    }


def find_manga_by_title(title: str) -> Optional[dict]:
    """Find manga in vector store by title search"""
    try:
        store = get_manga_vector_store()
        results = store.search(query=title, n_results=5)
        
        if not results:
            return None
        
        # Find best match (title contains search or vice versa)
        title_lower = title.lower().strip()
        for r in results:
            manga_title = r["metadata"]["title"].lower()
            if title_lower in manga_title or manga_title in title_lower:
                return {
                    "mal_id": r["mal_id"],
                    "title": r["metadata"]["title"],
                    "score": r["metadata"]["score"],
                    "genres": r["metadata"]["genres"]
                }
        
        # Return first result if no exact match
        return {
            "mal_id": results[0]["mal_id"],
            "title": results[0]["metadata"]["title"],
            "score": results[0]["metadata"]["score"],
            "genres": results[0]["metadata"]["genres"]
        }
    except Exception:
        return None


def execute_action(user: User, db: Session, action_type: str, match: re.Match) -> Optional[ActionResult]:
    """Execute a user action from chat"""
    if action_type == "add_completed":
        title = match.group(1).strip()
        rating = float(match.group(2)) if match.group(2) else None
        anime = find_anime_by_title(title)
        
        if not anime:
            return ActionResult(action="add_completed", success=False, message=f"Couldn't find anime: {title}")
        
        # Add to list
        existing = db.query(UserAnime).filter(
            UserAnime.user_id == user.id,
            UserAnime.anime_id == anime["mal_id"]
        ).first()
        
        if existing:
            existing.status = AnimeStatus.completed
            if rating:
                existing.rating = min(10, max(1, rating))
            existing.updated_at = datetime.utcnow()
        else:
            entry = UserAnime(
                user_id=user.id,
                anime_id=anime["mal_id"],
                status=AnimeStatus.completed,
                rating=min(10, max(1, rating)) if rating else None
            )
            db.add(entry)
        
        db.commit()
        rating_text = f" with rating {rating}/10" if rating else ""
        return ActionResult(
            action="add_completed",
            success=True,
            message=f"Added **{anime['title']}** to completed{rating_text}",
            anime_id=anime["mal_id"],
            anime_title=anime["title"]
        )
    
    elif action_type == "add_watching":
        title = match.group(1).strip()
        anime = find_anime_by_title(title)
        
        if not anime:
            return ActionResult(action="add_watching", success=False, message=f"Couldn't find anime: {title}")
        
        existing = db.query(UserAnime).filter(
            UserAnime.user_id == user.id,
            UserAnime.anime_id == anime["mal_id"]
        ).first()
        
        if existing:
            existing.status = AnimeStatus.watching
            existing.updated_at = datetime.utcnow()
        else:
            entry = UserAnime(user_id=user.id, anime_id=anime["mal_id"], status=AnimeStatus.watching)
            db.add(entry)
        
        db.commit()
        return ActionResult(
            action="add_watching",
            success=True,
            message=f"Added **{anime['title']}** to watching",
            anime_id=anime["mal_id"],
            anime_title=anime["title"]
        )
    
    elif action_type == "add_planned":
        title = match.group(1).strip()
        anime = find_anime_by_title(title)
        
        if not anime:
            return ActionResult(action="add_planned", success=False, message=f"Couldn't find anime: {title}")
        
        existing = db.query(UserAnime).filter(
            UserAnime.user_id == user.id,
            UserAnime.anime_id == anime["mal_id"]
        ).first()
        
        if existing:
            existing.status = AnimeStatus.planned
            existing.updated_at = datetime.utcnow()
        else:
            entry = UserAnime(user_id=user.id, anime_id=anime["mal_id"], status=AnimeStatus.planned)
            db.add(entry)
        
        db.commit()
        return ActionResult(
            action="add_planned",
            success=True,
            message=f"Added **{anime['title']}** to plan to watch",
            anime_id=anime["mal_id"],
            anime_title=anime["title"]
        )
    
    elif action_type == "rate_anime":
        title = match.group(1).strip()
        rating = float(match.group(2))
        anime = find_anime_by_title(title)
        
        if not anime:
            return ActionResult(action="rate_anime", success=False, message=f"Couldn't find anime: {title}")
        
        rating = min(10, max(1, rating))
        
        existing = db.query(UserAnime).filter(
            UserAnime.user_id == user.id,
            UserAnime.anime_id == anime["mal_id"]
        ).first()
        
        if existing:
            existing.rating = rating
            existing.updated_at = datetime.utcnow()
        else:
            entry = UserAnime(
                user_id=user.id,
                anime_id=anime["mal_id"],
                status=AnimeStatus.completed,
                rating=rating
            )
            db.add(entry)
        
        db.commit()
        return ActionResult(
            action="rate_anime",
            success=True,
            message=f"Rated **{anime['title']}** {rating}/10",
            anime_id=anime["mal_id"],
            anime_title=anime["title"]
        )
    
    elif action_type == "remove_anime":
        title = match.group(1).strip()
        anime = find_anime_by_title(title)
        
        if not anime:
            return ActionResult(action="remove_anime", success=False, message=f"Couldn't find anime: {title}")
        
        existing = db.query(UserAnime).filter(
            UserAnime.user_id == user.id,
            UserAnime.anime_id == anime["mal_id"]
        ).first()
        
        if existing:
            db.delete(existing)
            db.commit()
            return ActionResult(
                action="remove_anime",
                success=True,
                message=f"Removed **{anime['title']}** from your list",
                anime_id=anime["mal_id"],
                anime_title=anime["title"]
            )
        else:
            return ActionResult(action="remove_anime", success=False, message=f"{anime['title']} wasn't in your list")
    
    elif action_type == "add_on_hold":
        title = match.group(1).strip()
        anime = find_anime_by_title(title)
        
        if not anime:
            return ActionResult(action="add_on_hold", success=False, message=f"Couldn't find anime: {title}")
        
        existing = db.query(UserAnime).filter(
            UserAnime.user_id == user.id,
            UserAnime.anime_id == anime["mal_id"]
        ).first()
        
        if existing:
            existing.status = AnimeStatus.on_hold
            existing.updated_at = datetime.utcnow()
        else:
            entry = UserAnime(user_id=user.id, anime_id=anime["mal_id"], status=AnimeStatus.on_hold)
            db.add(entry)
        
        db.commit()
        return ActionResult(
            action="add_on_hold",
            success=True,
            message=f"Added **{anime['title']}** to on hold",
            anime_id=anime["mal_id"],
            anime_title=anime["title"]
        )
    
    elif action_type == "change_rating":
        title = match.group(1).strip()
        rating = float(match.group(2))
        anime = find_anime_by_title(title)
        
        if not anime:
            return ActionResult(action="change_rating", success=False, message=f"Couldn't find anime: {title}")
        
        rating = min(10, max(1, rating))
        
        existing = db.query(UserAnime).filter(
            UserAnime.user_id == user.id,
            UserAnime.anime_id == anime["mal_id"]
        ).first()
        
        if existing:
            existing.rating = rating
            existing.updated_at = datetime.utcnow()
            db.commit()
            return ActionResult(
                action="change_rating",
                success=True,
                message=f"Changed rating of **{anime['title']}** to {rating}/10",
                anime_id=anime["mal_id"],
                anime_title=anime["title"]
            )
        else:
            return ActionResult(action="change_rating", success=False, message=f"{anime['title']} is not in your list yet")
    
    return None


def execute_manga_action(user: User, db: Session, action_type: str, match: re.Match) -> Optional[ActionResult]:
    """Execute a manga action from chat"""
    if action_type == "add_manga_completed":
        title = match.group(1).strip()
        rating = float(match.group(2)) if match.group(2) else None
        manga = find_manga_by_title(title)
        
        if not manga:
            return ActionResult(action="add_manga_completed", success=False, message=f"Couldn't find manga: {title}")
        
        existing = db.query(UserManga).filter(
            UserManga.user_id == user.id,
            UserManga.manga_id == manga["mal_id"]
        ).first()
        
        if existing:
            existing.status = AnimeStatus.completed
            if rating:
                existing.rating = min(10, max(1, rating))
            existing.updated_at = datetime.utcnow()
        else:
            entry = UserManga(
                user_id=user.id,
                manga_id=manga["mal_id"],
                status=AnimeStatus.completed,
                rating=min(10, max(1, rating)) if rating else None
            )
            db.add(entry)
        
        db.commit()
        rating_text = f" with rating {rating}/10" if rating else ""
        return ActionResult(
            action="add_manga_completed",
            success=True,
            message=f"Added manga **{manga['title']}** to completed{rating_text}",
            anime_id=manga["mal_id"],
            anime_title=manga["title"]
        )
    
    elif action_type == "add_manga_reading":
        title = match.group(1).strip()
        manga = find_manga_by_title(title)
        
        if not manga:
            return ActionResult(action="add_manga_reading", success=False, message=f"Couldn't find manga: {title}")
        
        existing = db.query(UserManga).filter(
            UserManga.user_id == user.id,
            UserManga.manga_id == manga["mal_id"]
        ).first()
        
        if existing:
            existing.status = AnimeStatus.watching  # 'watching' = 'reading' for manga
            existing.updated_at = datetime.utcnow()
        else:
            entry = UserManga(user_id=user.id, manga_id=manga["mal_id"], status=AnimeStatus.watching)
            db.add(entry)
        
        db.commit()
        return ActionResult(
            action="add_manga_reading",
            success=True,
            message=f"Added manga **{manga['title']}** to reading",
            anime_id=manga["mal_id"],
            anime_title=manga["title"]
        )
    
    elif action_type == "rate_manga":
        title = match.group(1).strip()
        rating = float(match.group(2))
        manga = find_manga_by_title(title)
        
        if not manga:
            return ActionResult(action="rate_manga", success=False, message=f"Couldn't find manga: {title}")
        
        rating = min(10, max(1, rating))
        
        existing = db.query(UserManga).filter(
            UserManga.user_id == user.id,
            UserManga.manga_id == manga["mal_id"]
        ).first()
        
        if existing:
            existing.rating = rating
            existing.updated_at = datetime.utcnow()
        else:
            entry = UserManga(
                user_id=user.id,
                manga_id=manga["mal_id"],
                status=AnimeStatus.completed,
                rating=rating
            )
            db.add(entry)
        
        db.commit()
        return ActionResult(
            action="rate_manga",
            success=True,
            message=f"Rated manga **{manga['title']}** {rating}/10",
            anime_id=manga["mal_id"],
            anime_title=manga["title"]
        )
    
    elif action_type == "remove_manga":
        title = match.group(1).strip()
        manga = find_manga_by_title(title)
        
        if not manga:
            return ActionResult(action="remove_manga", success=False, message=f"Couldn't find manga: {title}")
        
        existing = db.query(UserManga).filter(
            UserManga.user_id == user.id,
            UserManga.manga_id == manga["mal_id"]
        ).first()
        
        if existing:
            db.delete(existing)
            db.commit()
            return ActionResult(
                action="remove_manga",
                success=True,
                message=f"Removed manga **{manga['title']}** from your list",
                anime_id=manga["mal_id"],
                anime_title=manga["title"]
            )
        else:
            return ActionResult(action="remove_manga", success=False, message=f"{manga['title']} wasn't in your list")
    
    return None


def detect_and_execute_actions(message: str, user: Optional[User], db: Session) -> list[ActionResult]:
    """Detect action commands in message and execute them"""
    if not user:
        return []
    
    actions = []
    message_lower = message.lower()
    
    # Check for manga actions first (more specific patterns)
    for action_type, pattern in MANGA_ACTION_PATTERNS.items():
        match = re.search(pattern, message_lower, re.IGNORECASE)
        if match:
            result = execute_manga_action(user, db, action_type, match)
            if result:
                actions.append(result)
                return actions  # Return early to avoid duplicate matching
    
    # Check for anime actions
    for action_type, pattern in ACTION_PATTERNS.items():
        match = re.search(pattern, message_lower, re.IGNORECASE)
        if match:
            result = execute_action(user, db, action_type, match)
            if result:
                actions.append(result)
    
    return actions


def get_user_profile_context(user: User, db: Session) -> str:
    """Build context string from user's anime history"""
    rated = db.query(UserAnime).filter(
        UserAnime.user_id == user.id,
        UserAnime.rating != None
    ).order_by(UserAnime.rating.desc()).limit(10).all()
    
    if not rated:
        return ""
    
    try:
        store = get_vector_store()
    except Exception as e:
        print(f"Vector store unavailable for profile context: {e}")
        # Return simple profile without anime details
        profile_text = f"\n\n=== {user.username}'s Anime Profile ===\n"
        profile_text += f"User has rated {len(rated)} anime.\n"
        return profile_text
    
    profile_text = f"\n\n=== {user.username}'s Anime Profile ===\n"
    
    loved, liked, disliked = [], [], []
    
    for entry in rated:
        try:
            result = store.collection.get(ids=[str(entry.anime_id)], include=["metadatas"])
            if result["metadatas"]:
                title = result["metadatas"][0].get("title", f"Anime #{entry.anime_id}")
                genres = result["metadatas"][0].get("genres", "")
                
                if entry.rating >= 8:
                    loved.append(f"{title} ({entry.rating}/10)")
                elif entry.rating >= 6:
                    liked.append(f"{title} ({entry.rating}/10)")
                else:
                    disliked.append(f"{title} ({entry.rating}/10)")
        except Exception:
            # Skip this entry if lookup fails
            pass
    
    if loved:
        profile_text += f"LOVED: {', '.join(loved[:5])}\n"
    if liked:
        profile_text += f"Liked: {', '.join(liked[:3])}\n"
    if disliked:
        profile_text += f"Disliked: {', '.join(disliked[:3])}\n"
    
    watching = db.query(UserAnime).filter(UserAnime.user_id == user.id, UserAnime.status == AnimeStatus.watching).count()
    completed = db.query(UserAnime).filter(UserAnime.user_id == user.id, UserAnime.status == AnimeStatus.completed).count()
    profile_text += f"Stats: {watching} watching, {completed} completed\n"
    
    return profile_text


@router.post("", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db)
):
    """
    Agentic chat with action execution.
    
    Supports commands like:
    - "Add Attack on Titan to my completed list with rating 9.5"
    - "Rate Death Note 10"
    - "Add Naruto to my watchlist"
    """
    if not GROQ_API_KEY:
        raise HTTPException(status_code=503, detail="Chat service unavailable. GROQ_API_KEY not configured.")
    
    user = await get_current_user(authorization, db)
    
    # Execute any actions in the message
    actions_taken = detect_and_execute_actions(request.message, user, db)
    
    # Build context
    user_profile_text = get_user_profile_context(user, db) if user else ""
    context_anime = []
    context_text = ""
    
    if request.use_context:
        store = get_vector_store()
        results = store.search(query=request.message, n_results=30)
        reranked = rerank_results(results, limit=15)
        
        if user:
            user_anime_ids = {item.anime_id for item in db.query(UserAnime).filter(UserAnime.user_id == user.id).all()}
            filtered = reranked[:5] + [r for r in reranked[5:] if r["mal_id"] not in user_anime_ids]
            reranked = filtered[:15]
        
        for r in reranked:
            anime_info = {
                "mal_id": r["mal_id"],
                "title": r["metadata"]["title"],
                "score": r["metadata"]["score"],
                "genres": r["metadata"]["genres"],
                "image_url": r["metadata"]["image_url"],
            }
            context_anime.append(anime_info)
            context_text += f"\n- {anime_info['title']} (Score: {anime_info['score']}/10, Genres: {anime_info['genres']})"
        
        detected_genres = detect_genres_from_query(request.message)
        if detected_genres:
            context_text = f"\nQuery suggests: {', '.join(detected_genres)}\n" + context_text
    
    # Build action context for LLM
    action_context = ""
    if actions_taken:
        action_context = "\n\n=== ACTIONS EXECUTED ===\n"
        for a in actions_taken:
            action_context += f"- {a.message}\n"
        action_context += "Acknowledge these actions in your response.\n"
    
    full_context = user_profile_text + action_context + "\n=== Relevant Anime ===\n" + context_text
    
    # Call LLM
    try:
        client = get_llm_client()
        reply = client.chat(
            user_message=request.message,
            context=full_context.strip(),
            history=request.history
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"LLM error: {str(e)}")
    
    return ChatResponse(
        reply=reply,
        context_anime=context_anime[:10],
        actions_taken=actions_taken
    )


@router.get("/health")
async def chat_health():
    return {"available": bool(GROQ_API_KEY), "model": "llama-3.1-8b-instant" if GROQ_API_KEY else None}
