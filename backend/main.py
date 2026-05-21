"""AniVerse API - Main Entry Point"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent))

from routes import search, chat, anime, auth, lists, recommendations, mal_import, manga

# Create FastAPI app
app = FastAPI(
    title="AniVerse API",
    description="AI-powered anime & manga discovery platform with semantic search, personalized recommendations, and user lists",
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS middleware - Allow ALL origins for cross-domain requests
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,  # Must be False when using wildcard
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(search.router)
app.include_router(chat.router)
app.include_router(anime.router)
app.include_router(auth.router)
app.include_router(lists.router)
app.include_router(recommendations.router)
app.include_router(mal_import.router)
app.include_router(manga.router)


@app.get("/")
async def root():
    """API root - health check and info"""
    return {
        "name": "AniVerse API",
        "version": "2.0.0",
        "status": "running",
        "endpoints": {
            "docs": "/docs",
            "search": "/api/search",
            "chat": "/api/chat",
            "anime": "/api/anime",
            "manga": "/api/manga",
            "auth": "/api/auth",
            "lists": "/api/lists",
            "recommendations": "/api/recommendations",
        }
    }


@app.get("/api/health")
async def health_check():
    """Health check endpoint for Docker/k8s"""
    return {"status": "healthy"}


@app.get("/api/stats")
async def get_stats():
    """Get database statistics"""
    from config import DATASET_PATH, MANGA_DATASET_PATH
    import pandas as pd

    total_anime = len(pd.read_csv(DATASET_PATH)) if DATASET_PATH.exists() else 0
    total_manga = len(pd.read_csv(MANGA_DATASET_PATH)) if MANGA_DATASET_PATH.exists() else 0
    indexed_anime = 0
    indexed_manga = 0
    vector_store_errors = {}

    try:
        from embeddings.chroma_store import get_vector_store
        indexed_anime = get_vector_store().get_count()
    except Exception as e:
        vector_store_errors["anime"] = str(e)

    try:
        from embeddings.manga_chroma_store import get_manga_vector_store
        indexed_manga = get_manga_vector_store().get_count()
    except Exception as e:
        vector_store_errors["manga"] = str(e)

    try:
        from embeddings.local_retrieval_model import get_model_artifact_info
        retrieval_model = get_model_artifact_info()
    except Exception as e:
        retrieval_model = {"available": False, "error": str(e)}

    return {
        "total_anime": total_anime,
        "total_manga": total_manga,
        "indexed_anime": indexed_anime,
        "indexed_manga": indexed_manga,
        "retrieval_model": retrieval_model,
        "vector_store_errors": vector_store_errors,
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
