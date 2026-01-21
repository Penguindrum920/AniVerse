"""Build manga embeddings and store in ChromaDB"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from data.manga_loader import load_manga_dataset, iter_manga, create_manga_embedding_text
from embeddings.manga_chroma_store import MangaVectorStore


def build_manga_embeddings(limit: int = None):
    """Build embeddings for manga dataset"""
    print("="*50)
    print("Building Manga Embeddings")
    print("="*50)
    
    # Load dataset
    df = load_manga_dataset(limit=limit)
    
    # Initialize vector store
    store = MangaVectorStore()
    
    # Collect data for batch insert
    ids = []
    texts = []
    metadatas = []
    
    print("\nProcessing manga entries...")
    for manga in iter_manga(df):
        embedding_text = create_manga_embedding_text(manga)
        
        metadata = {
            "title": manga.title,
            "media_type": manga.media_type or "manga",
            "score": manga.score or 0,
            "rank": manga.rank or 0,
            "members": manga.members or 0,
            "volumes": manga.volumes or 0,
            "genres": ", ".join(manga.genres) if manga.genres else "",
            "authors": ", ".join(manga.authors[:3]) if manga.authors else "",
            "image_url": manga.image_url or "",
            "published": manga.published or "",
        }
        
        ids.append(manga.mal_id)
        texts.append(embedding_text)
        metadatas.append(metadata)
    
    print(f"\nAdding {len(ids)} manga to vector store...")
    store.add_batch(ids, texts, metadatas, batch_size=100)
    
    print(f"\n✓ Successfully indexed {store.get_count()} manga entries!")
    print("="*50)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Build manga embeddings")
    parser.add_argument("--limit", type=int, help="Limit number of entries")
    args = parser.parse_args()
    
    build_manga_embeddings(limit=args.limit)
