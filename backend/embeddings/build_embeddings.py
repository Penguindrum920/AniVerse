"""Build anime embeddings and populate vector store"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from data.data_loader import load_anime_dataset, iter_anime, create_embedding_text
from embeddings.chroma_store import get_vector_store


def build_embeddings(limit: int = None, batch_size: int = 100):
    """Build embeddings for all anime and store in ChromaDB"""
    print("=" * 50)
    print("AniVerse Embedding Builder")
    print("=" * 50)
    
    # Load dataset
    df = load_anime_dataset(limit=limit)
    
    # Initialize vector store
    store = get_vector_store()
    existing_count = store.get_count()
    print(f"Existing entries in vector store: {existing_count}")
    
    # Prepare batch data
    ids = []
    texts = []
    metadatas = []
    
    print("Processing anime entries...")
    for anime in iter_anime(df):
        # Skip entries without synopsis (poor embeddings)
        if not anime.synopsis or len(anime.synopsis) < 20:
            continue
        
        ids.append(anime.mal_id)
        texts.append(create_embedding_text(anime))
        metadatas.append({
            "title": anime.title,
            "score": anime.score or 0,
            "genres": ", ".join(anime.genres) if anime.genres else "",
            "media_type": anime.media_type,
            "status": anime.status,
            "image_url": anime.image_url or "",
        })
    
    print(f"Prepared {len(ids)} anime entries for embedding")
    
    # Add to vector store
    print("Generating embeddings and storing in ChromaDB...")
    store.add_batch(ids, texts, metadatas, batch_size=batch_size)
    
    print("=" * 50)
    print(f"Complete! Vector store now has {store.get_count()} entries")
    print("=" * 50)


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Build anime embeddings")
    parser.add_argument("--limit", type=int, default=None, help="Limit number of entries to process")
    parser.add_argument("--batch-size", type=int, default=100, help="Batch size for embedding generation")
    
    args = parser.parse_args()
    build_embeddings(limit=args.limit, batch_size=args.batch_size)
