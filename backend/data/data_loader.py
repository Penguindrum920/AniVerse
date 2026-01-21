"""Load and process anime dataset"""
import pandas as pd
from pathlib import Path
from typing import Generator
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import DATASET_PATH
from data.anime_schema import Anime, parse_list_field


def load_anime_dataset(limit: int = None) -> pd.DataFrame:
    """Load anime dataset from CSV"""
    print(f"Loading dataset from {DATASET_PATH}...")
    
    df = pd.read_csv(DATASET_PATH, nrows=limit)
    
    # Rename columns to match our schema
    column_mapping = {
        "id": "mal_id",
        "mean": "score",
        "num_scoring_users": "scored_by",
        "num_favorites": "favorites",
        "main_picture_medium": "image_url",
        "alternative_titles_en": "title_english",
        "alternative_titles_ja": "title_japanese",
    }
    df = df.rename(columns=column_mapping)
    
    print(f"Loaded {len(df)} anime entries")
    return df


def parse_anime_row(row: pd.Series) -> Anime:
    """Convert DataFrame row to Anime model"""
    return Anime(
        mal_id=int(row["mal_id"]),
        title=str(row.get("title", "Unknown")),
        title_english=row.get("title_english") if pd.notna(row.get("title_english")) else None,
        title_japanese=row.get("title_japanese") if pd.notna(row.get("title_japanese")) else None,
        media_type=str(row.get("media_type", "unknown")),
        episodes=int(row["num_episodes"]) if pd.notna(row.get("num_episodes")) and row.get("num_episodes") != 0 else None,
        status=str(row.get("status", "unknown")),
        score=float(row["score"]) if pd.notna(row.get("score")) else None,
        scored_by=int(row["scored_by"]) if pd.notna(row.get("scored_by")) else None,
        rank=int(row["rank"]) if pd.notna(row.get("rank")) else None,
        popularity=int(row["popularity"]) if pd.notna(row.get("popularity")) else None,
        favorites=int(row["favorites"]) if pd.notna(row.get("favorites")) else None,
        synopsis=str(row.get("synopsis", "")) if pd.notna(row.get("synopsis")) else None,
        genres=parse_list_field(row.get("genres", "[]")),
        studios=parse_list_field(row.get("studios", "[]")),
        source=str(row.get("source")) if pd.notna(row.get("source")) else None,
        rating=str(row.get("rating")) if pd.notna(row.get("rating")) else None,
        image_url=str(row.get("image_url")) if pd.notna(row.get("image_url")) else None,
        start_date=str(row.get("start_date")) if pd.notna(row.get("start_date")) else None,
        end_date=str(row.get("end_date")) if pd.notna(row.get("end_date")) else None,
    )


def iter_anime(df: pd.DataFrame) -> Generator[Anime, None, None]:
    """Iterate over anime entries as Pydantic models"""
    for _, row in df.iterrows():
        try:
            yield parse_anime_row(row)
        except Exception as e:
            print(f"Error parsing row {row.get('mal_id', 'unknown')}: {e}")
            continue


def create_embedding_text(anime: Anime) -> str:
    """Create text for embedding generation"""
    parts = [anime.title]
    
    if anime.title_english and anime.title_english != anime.title:
        parts.append(anime.title_english)
    
    if anime.genres:
        parts.append(f"Genres: {', '.join(anime.genres)}")
    
    if anime.synopsis:
        # Truncate synopsis to prevent overly long embeddings
        synopsis = anime.synopsis[:1000]
        parts.append(synopsis)
        
        # Extract scene keywords for better scene-based search
        scene_keywords = extract_scene_keywords(synopsis, anime.genres or [])
        if scene_keywords:
            parts.append(f"Scenes and tropes: {', '.join(scene_keywords)}")
    
    return " | ".join(parts)


# Scene/trope detection patterns
SCENE_PATTERNS = {
    # Romantic scenes
    "confession": ["confess", "confession", "i love you", "feelings for", "admit feelings"],
    "rooftop scene": ["rooftop", "on the roof", "school rooftop"],
    "beach episode": ["beach", "swimsuit", "ocean", "summer vacation"],
    "festival date": ["festival", "fireworks", "yukata", "summer festival"],
    "accidental kiss": ["accidental", "lips touched", "fell on"],
    
    # Action scenes
    "training arc": ["training", "train harder", "become stronger", "special training"],
    "tournament arc": ["tournament", "competition", "championship", "finals"],
    "final battle": ["final battle", "last fight", "ultimate showdown", "final boss"],
    "power awakening": ["awakens", "hidden power", "true power", "unleash"],
    "sacrifice": ["sacrifice", "gave their life", "protect everyone", "died saving"],
    
    # Emotional scenes
    "tearful goodbye": ["goodbye", "farewell", "parting", "separation"],
    "death scene": ["death", "died", "killed", "passed away", "funeral"],
    "reunion": ["reunite", "reunion", "meet again", "found each other"],
    "flashback": ["flashback", "memories", "past", "childhood"],
    "redemption arc": ["redemption", "atone", "make amends", "change their ways"],
    
    # Character tropes
    "overpowered protagonist": ["overpowered", "strongest", "unbeatable", "one punch", "no match"],
    "hidden identity": ["secret identity", "hiding", "disguise", "true self"],
    "underdog story": ["underdog", "weakest", "looked down upon", "prove them wrong"],
    "transfer student": ["transfer student", "new student", "just arrived"],
    "chosen one": ["chosen", "prophecy", "destined", "fate"],
    
    # Setting/atmosphere
    "post-apocalyptic": ["apocalypse", "post-apocalyptic", "destroyed world", "ruins"],
    "isekai": ["another world", "transported", "reincarnated", "summoned to"],
    "time loop": ["time loop", "repeating", "stuck in time", "groundhog"],
    "school setting": ["high school", "academy", "school", "classroom"],
    "dystopian": ["dystopia", "oppressive", "government control", "rebellion"],
}


def extract_scene_keywords(synopsis: str, genres: list[str]) -> list[str]:
    """Extract scene/trope keywords from synopsis for better search"""
    if not synopsis:
        return []
    
    synopsis_lower = synopsis.lower()
    detected = []
    
    for scene_name, patterns in SCENE_PATTERNS.items():
        for pattern in patterns:
            if pattern in synopsis_lower:
                detected.append(scene_name)
                break
    
    # Add genre-based common tropes
    genre_tropes = {
        "Romance": ["love triangle", "slow burn romance"],
        "Action": ["battle scenes", "fight choreography"],
        "Comedy": ["comedic moments", "slapstick"],
        "Drama": ["emotional moments", "character development"],
        "Horror": ["scary scenes", "tension building"],
        "Sports": ["match scenes", "team dynamics"],
        "Music": ["performance scenes", "concert"],
    }
    
    for genre in genres:
        if genre in genre_tropes:
            detected.extend(genre_tropes[genre])
    
    return list(set(detected))[:10]  # Limit to 10 keywords


if __name__ == "__main__":
    # Test loading
    df = load_anime_dataset(limit=10)
    for anime in iter_anime(df):
        print(f"{anime.mal_id}: {anime.title} ({anime.score}) - {anime.genres}")
        print(f"  Embedding text: {create_embedding_text(anime)[:150]}...")
        print()
