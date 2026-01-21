"""Anime Data Models"""
from pydantic import BaseModel, Field
from typing import Optional
import ast


class Anime(BaseModel):
    """Core anime data model"""
    mal_id: int = Field(..., description="MyAnimeList ID")
    title: str
    title_english: Optional[str] = None
    title_japanese: Optional[str] = None
    media_type: str = "tv"
    episodes: Optional[int] = None
    status: str = "unknown"
    score: Optional[float] = None
    scored_by: Optional[int] = None
    rank: Optional[int] = None
    popularity: Optional[int] = None
    favorites: Optional[int] = None
    synopsis: Optional[str] = None
    genres: list[str] = []
    studios: list[str] = []
    source: Optional[str] = None
    rating: Optional[str] = None
    image_url: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None


class AnimeSearchResult(BaseModel):
    """Search result with similarity score"""
    anime: Anime
    similarity: float = Field(..., ge=0, le=1)


class ChatMessage(BaseModel):
    """Chat message for AI recommendations"""
    role: str = Field(..., pattern="^(user|assistant)$")
    content: str


class RecommendationRequest(BaseModel):
    """Request for AI recommendations"""
    query: str
    history: list[ChatMessage] = []
    limit: int = Field(default=10, ge=1, le=50)


class ReviewSummary(BaseModel):
    """Summarized review data"""
    overall_sentiment: str  # positive, negative, mixed
    pros: list[str]
    cons: list[str]
    summary: str
    aspect_scores: dict[str, float] = {}  # story, animation, characters, etc.


def parse_list_field(value: str) -> list[str]:
    """Parse stringified list from CSV"""
    if not value or value == "[]" or isinstance(value, float):
        return []
    try:
        # Handle Python list string format: "['Action', 'Adventure']"
        return ast.literal_eval(value)
    except (ValueError, SyntaxError):
        # Handle comma-separated format
        return [g.strip() for g in str(value).split(",") if g.strip()]
