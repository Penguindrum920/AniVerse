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

# CORS middleware for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify exact origins
    allow_credentials=True,
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
    from embeddings.chroma_store import get_vector_store
    from embeddings.manga_chroma_store import get_manga_vector_store
    from config import DATASET_PATH
    import pandas as pd
    
    anime_store = get_vector_store()
    manga_store = get_manga_vector_store()
    df = pd.read_csv(DATASET_PATH)
    
    return {
        "total_anime": len(df),
        "indexed_anime": anime_store.get_count(),
        "indexed_manga": manga_store.get_count(),
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
