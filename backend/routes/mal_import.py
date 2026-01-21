"""MAL Import Routes - OAuth and XML Import"""
from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from typing import Optional
import secrets
import httpx
import xml.etree.ElementTree as ET
from datetime import datetime
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from data.database import get_db, User, UserAnime, AnimeStatus
from routes.auth import require_user
from sqlalchemy.orm import Session

router = APIRouter(prefix="/api/import", tags=["MAL Import"])

# MAL OAuth Configuration
MAL_CLIENT_ID = "488a3cc0a2690df1a02bf4b13dbccf9d"
MAL_CLIENT_SECRET = "9143d5286658878b1f18d145eae3fa2757b5283b236ec05561fc333548557153"
MAL_AUTH_URL = "https://myanimelist.net/v1/oauth2/authorize"
MAL_TOKEN_URL = "https://myanimelist.net/v1/oauth2/token"
MAL_API_BASE = "https://api.myanimelist.net/v2"

# Store for PKCE code verifiers (in production, use Redis or DB)
oauth_states = {}

# MAL status mapping
MAL_STATUS_MAP = {
    "watching": AnimeStatus.watching,
    "completed": AnimeStatus.completed,
    "on_hold": AnimeStatus.on_hold,
    "dropped": AnimeStatus.dropped,
    "plan_to_watch": AnimeStatus.planned,
    "1": AnimeStatus.watching,  # XML format
    "2": AnimeStatus.completed,
    "3": AnimeStatus.on_hold,
    "4": AnimeStatus.dropped,
    "6": AnimeStatus.planned,
}


class ImportResult(BaseModel):
    success: bool
    imported: int
    skipped: int
    message: str


# ============================================
# OAuth Flow
# ============================================

@router.get("/mal/auth")
async def start_mal_oauth(request: Request, user: User = Depends(require_user)):
    """Start MAL OAuth flow - returns URL to redirect user"""
    # Generate PKCE code verifier (MAL uses plain method)
    code_verifier = secrets.token_urlsafe(64)[:128]
    state = secrets.token_urlsafe(32)
    
    # Store state -> (user_id, code_verifier)
    oauth_states[state] = {
        "user_id": user.id,
        "code_verifier": code_verifier
    }
    
    # Build authorization URL
    # Get the frontend origin for redirect
    frontend_origin = request.headers.get("origin", "http://localhost:5500")
    redirect_uri = f"{request.base_url}api/import/mal/callback"
    
    auth_url = (
        f"{MAL_AUTH_URL}?"
        f"response_type=code&"
        f"client_id={MAL_CLIENT_ID}&"
        f"state={state}&"
        f"redirect_uri={redirect_uri}&"
        f"code_challenge={code_verifier}&"
        f"code_challenge_method=plain"
    )
    
    return {"auth_url": auth_url, "state": state}


@router.get("/mal/callback")
async def mal_oauth_callback(
    code: Optional[str] = None,
    state: Optional[str] = None,
    error: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Handle MAL OAuth callback"""
    if error:
        return RedirectResponse(url=f"http://localhost:5500?import_error={error}")
    
    if not code or not state:
        return RedirectResponse(url="http://localhost:5500?import_error=missing_params")
    
    if state not in oauth_states:
        return RedirectResponse(url="http://localhost:5500?import_error=invalid_state")
    
    oauth_data = oauth_states.pop(state)
    user_id = oauth_data["user_id"]
    code_verifier = oauth_data["code_verifier"]
    
    # Exchange code for access token
    async with httpx.AsyncClient() as client:
        try:
            token_response = await client.post(
                MAL_TOKEN_URL,
                data={
                    "client_id": MAL_CLIENT_ID,
                    "client_secret": MAL_CLIENT_SECRET,
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": "http://127.0.0.1:8000/api/import/mal/callback",
                    "code_verifier": code_verifier
                }
            )
            
            if token_response.status_code != 200:
                return RedirectResponse(url=f"http://localhost:5500?import_error=token_failed")
            
            tokens = token_response.json()
            access_token = tokens["access_token"]
            
            # Fetch user's anime list
            anime_list = []
            next_url = f"{MAL_API_BASE}/users/@me/animelist?fields=list_status&limit=1000"
            
            while next_url:
                list_response = await client.get(
                    next_url,
                    headers={"Authorization": f"Bearer {access_token}"}
                )
                
                if list_response.status_code != 200:
                    break
                    
                data = list_response.json()
                anime_list.extend(data.get("data", []))
                next_url = data.get("paging", {}).get("next")
            
            # Import anime to user's list
            imported = 0
            skipped = 0
            user = db.query(User).filter(User.id == user_id).first()
            
            for item in anime_list:
                try:
                    anime_id = item["node"]["id"]
                    status_str = item["list_status"]["status"]
                    score = item["list_status"].get("score", 0)
                    
                    status = MAL_STATUS_MAP.get(status_str, AnimeStatus.planned)
                    rating = score if score > 0 else None
                    
                    # Check if exists
                    existing = db.query(UserAnime).filter(
                        UserAnime.user_id == user_id,
                        UserAnime.anime_id == anime_id
                    ).first()
                    
                    if existing:
                        existing.status = status
                        if rating:
                            existing.rating = rating
                        existing.updated_at = datetime.utcnow()
                        skipped += 1
                    else:
                        entry = UserAnime(
                            user_id=user_id,
                            anime_id=anime_id,
                            status=status,
                            rating=rating
                        )
                        db.add(entry)
                        imported += 1
                except Exception:
                    skipped += 1
                    continue
            
            db.commit()
            
            return RedirectResponse(
                url=f"http://localhost:5500?import_success=true&imported={imported}&updated={skipped}"
            )
            
        except Exception as e:
            return RedirectResponse(url=f"http://localhost:5500?import_error=api_failed")


# ============================================
# XML Import
# ============================================

@router.post("/mal/xml", response_model=ImportResult)
async def import_mal_xml(
    file: UploadFile = File(...),
    user: User = Depends(require_user),
    db: Session = Depends(get_db)
):
    """Import anime list from MAL XML export file"""
    if not file.filename.endswith('.xml'):
        raise HTTPException(status_code=400, detail="File must be XML format")
    
    try:
        content = await file.read()
        root = ET.fromstring(content)
    except ET.ParseError:
        raise HTTPException(status_code=400, detail="Invalid XML file")
    except Exception:
        raise HTTPException(status_code=400, detail="Could not read file")
    
    imported = 0
    skipped = 0
    
    # Find all anime entries
    for anime in root.findall(".//anime"):
        try:
            # Extract data from XML
            anime_id_elem = anime.find("series_animedb_id")
            status_elem = anime.find("my_status")
            score_elem = anime.find("my_score")
            
            if anime_id_elem is None:
                skipped += 1
                continue
            
            anime_id = int(anime_id_elem.text)
            status_str = status_elem.text if status_elem is not None else "6"
            score = int(score_elem.text) if score_elem is not None and score_elem.text else 0
            
            status = MAL_STATUS_MAP.get(status_str, AnimeStatus.planned)
            rating = float(score) if score > 0 else None
            
            # Check if exists
            existing = db.query(UserAnime).filter(
                UserAnime.user_id == user.id,
                UserAnime.anime_id == anime_id
            ).first()
            
            if existing:
                existing.status = status
                if rating:
                    existing.rating = rating
                existing.updated_at = datetime.utcnow()
                skipped += 1
            else:
                entry = UserAnime(
                    user_id=user.id,
                    anime_id=anime_id,
                    status=status,
                    rating=rating
                )
                db.add(entry)
                imported += 1
                
        except Exception:
            skipped += 1
            continue
    
    db.commit()
    
    return ImportResult(
        success=True,
        imported=imported,
        skipped=skipped,
        message=f"Successfully imported {imported} anime, updated {skipped} existing entries"
    )
