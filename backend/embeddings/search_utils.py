"""Search utilities for improved ranking and filtering"""
from typing import Optional


def calculate_combined_score(
    similarity: float,
    anime_score: float,
    popularity: int = None,
    weight_similarity: float = 0.6,
    weight_anime_score: float = 0.3,
    weight_popularity: float = 0.1
) -> float:
    """
    Calculate a combined ranking score.
    
    Args:
        similarity: Vector similarity (0-1)
        anime_score: MAL score (0-10)
        popularity: Popularity rank (lower is better)
        weight_*: Weights for each factor
    
    Returns:
        Combined score (0-1)
    """
    # Normalize anime score to 0-1
    normalized_score = (anime_score or 0) / 10
    
    # Normalize popularity (inverse, since lower rank = more popular)
    normalized_pop = 0.5  # Default if not available
    if popularity and popularity > 0:
        # Map rank 1-1000 to 1-0.5, rank > 1000 to 0.5-0.1
        if popularity <= 1000:
            normalized_pop = 1 - (popularity / 2000)
        else:
            normalized_pop = max(0.1, 0.5 - (popularity - 1000) / 20000)
    
    combined = (
        weight_similarity * similarity +
        weight_anime_score * normalized_score +
        weight_popularity * normalized_pop
    )
    
    return round(combined, 4)


def rerank_results(results: list[dict], limit: int = 15) -> list[dict]:
    """
    Rerank search results using combined scoring.
    
    Args:
        results: List of search results with metadata
        limit: Max results to return
    
    Returns:
        Reranked and limited results
    """
    for r in results:
        r["combined_score"] = calculate_combined_score(
            similarity=r.get("similarity", 0),
            anime_score=r.get("metadata", {}).get("score", 0),
            popularity=r.get("metadata", {}).get("popularity")
        )
    
    # Sort by combined score
    reranked = sorted(results, key=lambda x: x["combined_score"], reverse=True)
    
    return reranked[:limit]


def build_genre_filter(genres: list[str]) -> dict:
    """Build ChromaDB where filter for genres"""
    if not genres:
        return None
    
    # ChromaDB uses $contains for partial string match
    if len(genres) == 1:
        return {"genres": {"$contains": genres[0]}}
    
    # Multiple genres: any match
    return {"$or": [{"genres": {"$contains": g}} for g in genres]}


def extract_keywords(query: str) -> list[str]:
    """Extract important keywords from search query"""
    # Common words to ignore
    stop_words = {
        "anime", "like", "similar", "to", "with", "the", "a", "an", "and", "or",
        "that", "has", "have", "good", "best", "top", "show", "series", "want",
        "looking", "for", "something", "recommend", "me", "please", "i", "my"
    }
    
    words = query.lower().split()
    keywords = [w.strip(",.!?") for w in words if w.strip(",.!?") not in stop_words]
    
    return keywords


# Genre keyword mappings for better matching
GENRE_KEYWORDS = {
    "action": ["action", "fight", "battle", "combat", "war"],
    "romance": ["romance", "love", "romantic", "relationship", "dating"],
    "comedy": ["comedy", "funny", "humor", "hilarious", "laugh"],
    "drama": ["drama", "emotional", "feels", "sad", "tear"],
    "horror": ["horror", "scary", "terrifying", "creepy", "dark"],
    "psychological": ["psychological", "mind", "mental", "thriller", "mindbending"],
    "slice of life": ["slice of life", "daily", "everyday", "relaxing", "wholesome"],
    "fantasy": ["fantasy", "magic", "wizard", "isekai", "magical"],
    "sci-fi": ["sci-fi", "scifi", "science fiction", "future", "space", "mecha"],
    "sports": ["sports", "basketball", "soccer", "volleyball", "baseball"],
    "mystery": ["mystery", "detective", "investigation", "whodunit"],
    "supernatural": ["supernatural", "ghost", "spirit", "demon", "paranormal"],
}


def detect_genres_from_query(query: str) -> list[str]:
    """Detect genre preferences from natural language query"""
    query_lower = query.lower()
    detected = []
    
    for genre, keywords in GENRE_KEYWORDS.items():
        for kw in keywords:
            if kw in query_lower:
                detected.append(genre.title())
                break
    
    return detected
