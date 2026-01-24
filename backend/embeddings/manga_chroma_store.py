"""ChromaDB Vector Store for Manga Similarity Search"""
import chromadb
from chromadb.config import Settings
from chromadb.utils import embedding_functions
from typing import Optional
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import MANGA_CHROMA_DB_PATH, EMBEDDING_MODEL


class MangaVectorStore:
    """Vector database for manga semantic search"""
    
    def __init__(self, persist_directory: str = None):
        self.persist_dir = persist_directory or str(MANGA_CHROMA_DB_PATH)
        
        try:
            # Initialize ChromaDB client
            self.client = chromadb.PersistentClient(
                path=self.persist_dir,
                settings=Settings(
                    anonymized_telemetry=False,
                    allow_reset=True
                )
            )
            
            # Use ChromaDB's default embedding function
            self.embedding_fn = embedding_functions.DefaultEmbeddingFunction()
            
            # Get or create manga collection
            try:
                # Try getting without specifying function first
                self.collection = self.client.get_collection(
                    name="manga",
                    embedding_function=self.embedding_fn
                )
            except Exception:
                # Fallback to create/get
                self.collection = self.client.get_or_create_collection(
                    name="manga",
                    metadata={"hnsw:space": "cosine"},
                    embedding_function=self.embedding_fn
                )
            
            print(f"Manga vector store initialized at {self.persist_dir}")
            print(f"Manga collection count: {self.collection.count()}")
        except Exception as e:
            print(f"ERROR initializing manga vector store: {e}")
            import traceback
            traceback.print_exc()
            raise
    
    def add_manga(
        self,
        mal_id: int,
        embedding_text: str,
        metadata: dict
    ) -> None:
        """Add or update manga entry in vector store"""
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
        """Add multiple manga entries in batches"""
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
            
            print(f"  Added {min(i+batch_size, total)}/{total} manga entries...")
    
    def search(
        self,
        query: str,
        n_results: int = 10,
        where: Optional[dict] = None
    ) -> list[dict]:
        """Search for similar manga by text query"""
        results = self.collection.query(
            query_texts=[query],
            n_results=n_results,
            where=where,
            include=["metadatas", "documents", "distances"]
        )
        
        formatted = []
        for i, mal_id in enumerate(results["ids"][0]):
            formatted.append({
                "mal_id": int(mal_id),
                "metadata": results["metadatas"][0][i],
                "document": results["documents"][0][i],
                "similarity": 1 - results["distances"][0][i]
            })
        
        return formatted
    
    def search_similar(
        self,
        mal_id: int,
        n_results: int = 10
    ) -> list[dict]:
        """Find manga similar to a given manga by MAL ID"""
        result = self.collection.get(
            ids=[str(mal_id)],
            include=["documents"]
        )
        
        if not result["documents"]:
            return []
        
        results = self.collection.query(
            query_texts=result["documents"],
            n_results=n_results + 1,
            include=["metadatas", "documents", "distances"]
        )
        
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
_manga_store: Optional[MangaVectorStore] = None


def get_manga_vector_store() -> MangaVectorStore:
    """Get or create manga vector store instance"""
    global _manga_store
    if _manga_store is None:
        _manga_store = MangaVectorStore()
    return _manga_store
