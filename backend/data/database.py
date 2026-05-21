"""Database setup and models"""
import os
from datetime import datetime
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, ForeignKey, Enum as SQLEnum, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
import enum


# Database path
DB_PATH = os.getenv("DATABASE_PATH", os.path.join(os.path.dirname(os.path.dirname(__file__)), "aniverse.db"))
DATABASE_URL = f"sqlite:///{DB_PATH}"

# Create engine
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class AnimeStatus(enum.Enum):
    """User's status for an anime"""
    watching = "watching"
    completed = "completed"
    planned = "planned"
    dropped = "dropped"
    on_hold = "on_hold"


class User(Base):
    """User account model"""
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    username = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    anime_list = relationship("UserAnime", back_populates="user")
    manga_list = relationship("UserManga", back_populates="user")


class UserAnime(Base):
    """User's anime list entry"""
    __tablename__ = "user_anime"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    anime_id = Column(Integer, nullable=False)  # MAL ID
    status = Column(SQLEnum(AnimeStatus), default=AnimeStatus.planned)
    rating = Column(Float, nullable=True)  # 1-10 scale
    is_favorite = Column(Integer, default=0)  # SQLite boolean
    added_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    user = relationship("User", back_populates="anime_list")


class UserManga(Base):
    """User's manga list entry"""
    __tablename__ = "user_manga"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    manga_id = Column(Integer, nullable=False)  # MAL ID
    status = Column(SQLEnum(AnimeStatus), default=AnimeStatus.planned)  # Reuse status enum
    rating = Column(Float, nullable=True)  # 1-10 scale
    is_favorite = Column(Integer, default=0)  # SQLite boolean
    added_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    user = relationship("User", back_populates="manga_list")


class CachedAnime(Base):
    """Live provider anime cached for search, details, and lazy vector indexing."""
    __tablename__ = "cached_anime"

    id = Column(Integer, primary_key=True, index=True)  # public AniVerse ID
    mal_id = Column(Integer, index=True, nullable=True)
    anilist_id = Column(Integer, unique=True, index=True, nullable=True)
    provider = Column(String, default="anilist", nullable=False)

    title = Column(String, nullable=False)
    title_english = Column(String, nullable=True)
    title_japanese = Column(String, nullable=True)
    media_type = Column(String, nullable=True)
    episodes = Column(Integer, nullable=True)
    status = Column(String, nullable=True)
    score = Column(Float, nullable=True)
    scored_by = Column(Integer, nullable=True)
    rank = Column(Integer, nullable=True)
    popularity = Column(Integer, nullable=True)
    favorites = Column(Integer, nullable=True)
    synopsis = Column(Text, nullable=True)
    genres = Column(Text, nullable=True)  # JSON list
    studios = Column(Text, nullable=True)  # JSON list
    source = Column(String, nullable=True)
    rating = Column(String, nullable=True)
    image_url = Column(String, nullable=True)
    start_date = Column(String, nullable=True)
    end_date = Column(String, nullable=True)
    site_url = Column(String, nullable=True)
    raw_json = Column(Text, nullable=True)
    cached_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


def init_db():
    """Initialize database tables"""
    Base.metadata.create_all(bind=engine)
    print(f"Database initialized at {DB_PATH}")


def get_db():
    """Get database session"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


if __name__ == "__main__":
    init_db()
    print("Database tables created successfully!")
