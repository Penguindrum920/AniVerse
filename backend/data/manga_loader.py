"""Load and process manga dataset"""
import pandas as pd
from pathlib import Path
from typing import Generator
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import MANGA_DATASET_PATH
from data.manga_schema import Manga, parse_list_field


def load_manga_dataset(limit: int = None) -> pd.DataFrame:
    """Load manga dataset from CSV"""
    print(f"Loading manga dataset from {MANGA_DATASET_PATH}...")
    
    df = pd.read_csv(MANGA_DATASET_PATH, nrows=limit)
    
    # Clean up column names
    df.columns = df.columns.str.strip()
    
    print(f"Loaded {len(df)} manga entries")
    print(f"Columns: {df.columns.tolist()}")
    return df


def parse_manga_row(row: pd.Series) -> Manga:
    """Convert DataFrame row to Manga model"""
    # Extract mal_id from URL if available
    mal_id = None
    if pd.notna(row.get("page_url")):
        try:
            # URL format: https://myanimelist.net/manga/ID/title
            url = str(row["page_url"])
            parts = url.split("/manga/")
            if len(parts) > 1:
                mal_id = int(parts[1].split("/")[0])
        except (ValueError, IndexError):
            pass
    
    if mal_id is None:
        # Use index or unnamed column
        mal_id = int(row.get("Unnamed: 0", row.name)) if pd.notna(row.get("Unnamed: 0")) else row.name
    
    # Parse volumes
    volumes = None
    if pd.notna(row.get("Volumes")):
        try:
            vol_str = str(row["Volumes"]).strip()
            if vol_str.isdigit():
                volumes = int(vol_str)
        except ValueError:
            pass
    
    # Parse score
    score = None
    if pd.notna(row.get("Score")):
        try:
            score = float(row["Score"])
        except (ValueError, TypeError):
            pass
    
    # Parse members
    members = None
    if pd.notna(row.get("Members")):
        try:
            members = int(str(row["Members"]).replace(",", ""))
        except (ValueError, TypeError):
            pass
    
    # Parse rank
    rank = None
    if pd.notna(row.get("Rank")):
        try:
            rank = int(row["Rank"])
        except (ValueError, TypeError):
            pass
    
    return Manga(
        mal_id=mal_id,
        title=str(row.get("Title", "Unknown")).strip(),
        media_type=str(row.get("Type", "Manga")).strip().lower() if pd.notna(row.get("Type")) else "manga",
        volumes=volumes,
        score=score,
        rank=rank,
        members=members,
        published=str(row.get("Published")) if pd.notna(row.get("Published")) else None,
        genres=parse_list_field(row.get("Genres", "[]")),
        authors=parse_list_field(row.get("Authors", "[]")),
        image_url=str(row.get("image_url")) if pd.notna(row.get("image_url")) else None,
    )


def iter_manga(df: pd.DataFrame) -> Generator[Manga, None, None]:
    """Iterate over manga entries as Pydantic models"""
    for _, row in df.iterrows():
        try:
            yield parse_manga_row(row)
        except Exception as e:
            print(f"Error parsing manga row {row.get('Title', 'unknown')}: {e}")
            continue


def create_manga_embedding_text(manga: Manga) -> str:
    """Create text for embedding generation"""
    parts = [manga.title]
    
    if manga.genres:
        parts.append(f"Genres: {', '.join(manga.genres)}")
    
    if manga.media_type:
        parts.append(f"Type: {manga.media_type}")
    
    if manga.authors:
        parts.append(f"Authors: {', '.join(manga.authors[:3])}")
    
    if manga.synopsis:
        synopsis = manga.synopsis[:1000]
        parts.append(synopsis)
    
    return " | ".join(parts)


if __name__ == "__main__":
    # Test loading
    df = load_manga_dataset(limit=10)
    for manga in iter_manga(df):
        print(f"{manga.mal_id}: {manga.title} (Score: {manga.score}) - {manga.genres}")
        print(f"  Type: {manga.media_type}, Volumes: {manga.volumes}")
        print()
