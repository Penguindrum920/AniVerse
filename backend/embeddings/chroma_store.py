"""ChromaDB Vector Store for Anime Similarity Search"""
import chromadb
from chromadb.config import Settings
from typing import Optional
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import CHROMA_DB_PATH, EMBEDDING_MODEL


class AnimeVectorStore:
    """Vector database for anime semantic search"""
    
    def __init__(self, persist_directory: str = None):
        self.persist_dir = persist_directory or str(CHROMA_DB_PATH)
        
        try:
            # Initialize ChromaDB client with telemetry disabled
            self.client = chromadb.PersistentClient(
                path=self.persist_dir,
                settings=Settings(
                    anonymized_telemetry=False,
                    allow_reset=True
                )
            )
            
            # Use ChromaDB's default embedding function
            from chromadb.utils import embedding_functions
            self.embedding_fn = embedding_functions.DefaultEmbeddingFunction()
            
            # Get or create anime collection
            # Try getting without specifying embedding function first to avoid conflicts
            try:
                self.collection = self.client.get_collection(
                    name="anime",
                    embedding_function=self.embedding_fn
                )
            except Exception:
                # If that fails or doesn't exist, try creating/getting with specific config
                self.collection = self.client.get_or_create_collection(
                    name="anime",
                    metadata={"hnsw:space": "cosine"},
                    embedding_function=self.embedding_fn
                )
            
            print(f"Vector store initialized at {self.persist_dir}")
            print(f"Collection count: {self.collection.count()}")
        except Exception as e:
            print(f"ERROR initializing vector store: {e}")
            # Try to load without embedding function as last resort (for reading only)
            try:
                if 'conflict' in str(e).lower():
                    print("Attempting to load collection without enforcing embedding function...")
                    self.collection = self.client.get_collection(name="anime")
                    print("Success! Loaded existing collection config.")
                    return
            except:
                pass
                
            import traceback
            traceback.print_exc()
            raise
    
    def add_anime(
        self,
        mal_id: int,
        embedding_text: str,
        metadata: dict
    ) -> None:
        """Add or update anime entry in vector store"""
        # Upsert to collection (embeddings auto-generated)
        self.collection.upsert(
            ids=[str(mal_id)],
            documents=[embedding_text],
            metadatas=[metadata]
        )
    
    def add_batch(
        self,
        ids: list[int],
        texts: list[str],
        metadatas: list[dict],
        batch_size: int = 100
    ) -> None:
        """Add multiple anime entries in batches"""
        total = len(ids)
        for i in range(0, total, batch_size):
            batch_ids = [str(id_) for id_ in ids[i:i+batch_size]]
            batch_texts = texts[i:i+batch_size]
            batch_meta = metadatas[i:i+batch_size]
            
            self.collection.upsert(
                ids=batch_ids,
                documents=batch_texts,
                metadatas=batch_meta
            )
            
            print(f"  Added {min(i+batch_size, total)}/{total} entries...")
    
    def search(
        self,
        query: str,
        n_results: int = 10,
        where: Optional[dict] = None
    ) -> list[dict]:
        """Search for similar anime by text query"""
        # Query ChromaDB (embedding auto-generated from query)
        results = self.collection.query(
            query_texts=[query],
            n_results=n_results,
            where=where,
            include=["metadatas", "documents", "distances"]
        )
        
        # Format results
        formatted = []
        for i, mal_id in enumerate(results["ids"][0]):
            formatted.append({
                "mal_id": int(mal_id),
                "metadata": results["metadatas"][0][i],
                "document": results["documents"][0][i],
                "similarity": 1 - results["distances"][0][i]  # Convert distance to similarity
            })
        
        return formatted
    
    def search_similar(
        self,
        mal_id: int,
        n_results: int = 10
    ) -> list[dict]:
        """Find anime similar to a given anime by MAL ID"""
        # Get the anime's document
        result = self.collection.get(
            ids=[str(mal_id)],
            include=["documents"]
        )
        
        if not result["documents"]:
            return []
        
        # Query with that document
        results = self.collection.query(
            query_texts=result["documents"],
            n_results=n_results + 1,  # +1 to exclude self
            include=["metadatas", "documents", "distances"]
        )
        
        # Format and exclude self
        formatted = []
        for i, id_ in enumerate(results["ids"][0]):
            if int(id_) == mal_id:
                continue
            formatted.append({
                "mal_id": int(id_),
                "metadata": results["metadatas"][0][i],
                "document": results["documents"][0][i],
                "similarity": 1 - results["distances"][0][i]
            })
        
        return formatted[:n_results]
    
    def get_count(self) -> int:
        """Get total number of entries in the collection"""
        return self.collection.count()


# Singleton instance
_store: Optional[AnimeVectorStore] = None


def get_vector_store() -> AnimeVectorStore:
    """Get or create vector store instance"""
    global _store
    if _store is None:
        _store = AnimeVectorStore()
    return _store
