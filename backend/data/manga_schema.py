"""Manga data schema"""
from pydantic import BaseModel
from typing import Optional
import ast


class Manga(BaseModel):
    """Manga entry with MAL-style fields"""
    mal_id: int
    title: str
    title_english: Optional[str] = None
    media_type: str = "manga"  # manga, manhwa, manhua, novel, light_novel
    volumes: Optional[int] = None
    chapters: Optional[int] = None
    status: Optional[str] = None  # publishing, finished
    score: Optional[float] = None
    scored_by: Optional[int] = None
    rank: Optional[int] = None
    popularity: Optional[int] = None
    members: Optional[int] = None
    favorites: Optional[int] = None
    synopsis: Optional[str] = None
    genres: list[str] = []
    authors: list[str] = []
    image_url: Optional[str] = None
    published: Optional[str] = None


def parse_list_field(value) -> list[str]:
    """Parse string list field from CSV"""
    if not value or (isinstance(value, float) and str(value) == 'nan'):
        return []
    
    if isinstance(value, list):
        return value
    
    if isinstance(value, str):
        value = value.strip()
        if value.startswith('['):
            try:
                parsed = ast.literal_eval(value)
                return [str(item) for item in parsed if item]
            except (ValueError, SyntaxError):
                pass
        
        # Try comma-separated
        if ',' in value:
            return [v.strip() for v in value.split(',') if v.strip()]
        
        return [value] if value else []
    
    return []
