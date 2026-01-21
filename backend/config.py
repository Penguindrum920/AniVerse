"""AniVerse Configuration"""
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# Paths - support both local development and container deployment
BASE_DIR = Path(__file__).parent.parent
BACKEND_DIR = Path(__file__).parent

# Check if running in container (dataset will be in /app/dataset)
if (BACKEND_DIR / "dataset").exists():
    DATASET_PATH = BACKEND_DIR / "dataset" / "anime.csv"
    MANGA_DATASET_PATH = BACKEND_DIR / "dataset" / "manga_data" / "MAL-manga.csv"
else:
    DATASET_PATH = BASE_DIR / "dataset" / "anime.csv"
    MANGA_DATASET_PATH = BASE_DIR / "dataset" / "manga data" / "MAL-manga.csv"

# ChromaDB paths - use environment variables with fallbacks
CHROMA_DB_PATH = Path(os.getenv("CHROMA_DB_PATH", str(BACKEND_DIR / "chroma_db")))
MANGA_CHROMA_DB_PATH = Path(os.getenv("MANGA_CHROMA_DB_PATH", str(BACKEND_DIR / "manga_chroma_db")))

# API Keys
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")

# Model Settings
EMBEDDING_MODEL = "all-MiniLM-L6-v2"
LLM_MODEL = "llama-3.1-8b-instant"  # Fast, free on Groq

# API Settings
JIKAN_BASE_URL = "https://api.jikan.moe/v4"
JIKAN_RATE_LIMIT = 3  # requests per second
