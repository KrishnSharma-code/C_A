"""
ChromaDB vector store for semantic code search.
Embedding function resolution order:
  1. DefaultEmbeddingFunction (ChromaDB built-in ONNX)
  2. ONNXMiniLM_L6_V2 (direct import path for ChromaDB 1.x)
  3. SentenceTransformerEmbeddingFunction (if sentence-transformers installed)
  4. Keyword-based fallback
"""
import logging
from typing import List, Dict, Any, Optional
from backend.config import CHROMA_DIR

logger = logging.getLogger(__name__)


def _resolve_ef():
    """Try embedding functions in order; return the first that works."""

    try:
        from chromadb.utils.embedding_functions import DefaultEmbeddingFunction
        ef = DefaultEmbeddingFunction()
        ef(["warmup"])
        logger.info("Using DefaultEmbeddingFunction (ONNX)")
        return ef
    except Exception as e:
        logger.debug(f"DefaultEmbeddingFunction failed: {e}")

    try:
        from chromadb.utils.embedding_functions.onnx_mini_lm_l6_v2 import ONNXMiniLM_L6_V2
        ef = ONNXMiniLM_L6_V2()
        ef(["warmup"])
        logger.info("Using ONNXMiniLM_L6_V2")
        return ef
    except Exception as e:
        logger.debug(f"ONNXMiniLM_L6_V2 failed: {e}")

    try:
        from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction
        ef = SentenceTransformerEmbeddingFunction(model_name="all-MiniLM-L6-v2")
        logger.info("Using SentenceTransformerEmbeddingFunction")
        return ef
    except Exception as e:
        logger.debug(f"SentenceTransformer failed: {e}")

    logger.warning(
        "No embedding function available. "
        "Semantic search will fall back to keyword matching."
    )
    return None


_GLOBAL_EF = _resolve_ef()


class CodeVectorStore:
    """
    In-process ChromaDB store for code chunks.
    Each project gets its own collection identified by project_id.
    """

    def __init__(self, project_id: str):
        self.project_id      = project_id
        self.collection_name = f"proj_{project_id.replace('-', '_')}"
        self._collection     = None
        self._client         = None

    @property
    def client(self):
        if self._client is None:
            import chromadb
            self._client = chromadb.PersistentClient(path=str(CHROMA_DIR))
        return self._client

    @property
    def collection(self):
        if self._collection is None:
            if _GLOBAL_EF is not None:
                self._collection = self.client.get_or_create_collection(
                    name=self.collection_name,
                    embedding_function=_GLOBAL_EF,
                    metadata={"project_id": self.project_id}
                )
            else:
                self._collection = self.client.get_or_create_collection(
                    name=self.collection_name,
                    metadata={"project_id": self.project_id}
                )
        return self._collection

    def add_chunks(self, chunks: List[Dict[str, Any]]) -> int:
        """Index code chunks. Returns number of chunks successfully stored."""
        if not chunks:
            return 0

        documents, metadatas, ids = [], [], []

        for i, chunk in enumerate(chunks):
            content = (chunk.get("content") or "").strip()
            if not content:
                continue

            chunk_id = f"{self.project_id}_{i}_{chunk.get('name', 'chunk')}"[:100]
            documents.append(content[:2000])
            metadatas.append({
                "type":       str(chunk.get("type",      "unknown"))[:50],
                "name":       str(chunk.get("name",      ""))[:100],
                "file_path":  str(chunk.get("file_path", ""))[:200],
                "start_line": int(chunk.get("start_line", 0)),
                "end_line":   int(chunk.get("end_line",   0)),
                "language":   str(chunk.get("language",  "unknown"))[:30],
            })
            ids.append(chunk_id)

        if not documents:
            return 0

        total = 0
        for i in range(0, len(documents), 100):
            b_docs  = documents[i:i+100]
            b_metas = metadatas[i:i+100]
            b_ids   = ids[i:i+100]
            try:
                self.collection.add(documents=b_docs, metadatas=b_metas, ids=b_ids)
                total += len(b_docs)
            except Exception:
                try:
                    self.collection.upsert(documents=b_docs, metadatas=b_metas, ids=b_ids)
                    total += len(b_docs)
                except Exception as e:
                    logger.warning(f"batch upsert failed: {e}")

        return total

    def search(self, query: str, n_results: int = 5,
               filter_type: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Semantic search when an embedding function is available,
        keyword search otherwise.
        """
        try:
            n = min(n_results, max(1, self.collection.count()))
            if n == 0:
                return []

            if _GLOBAL_EF is not None:
                kwargs: Dict[str, Any] = {
                    "query_texts": [query],
                    "n_results":   n,
                    "include":     ["documents", "metadatas", "distances"],
                }
                if filter_type:
                    kwargs["where"] = {"type": filter_type}

                results = self.collection.query(**kwargs)

                chunks = []
                if results and results.get("documents") and results["documents"][0]:
                    for doc, meta, dist in zip(
                        results["documents"][0],
                        results["metadatas"][0],
                        results["distances"][0],
                    ):
                        # ChromaDB returns L2 distances; convert to 0-1 similarity
                        similarity = max(0.0, 1.0 - dist)
                        chunks.append({
                            "content":         doc,
                            "metadata":        meta,
                            "relevance_score": round(similarity, 4),
                        })
                return chunks

            return self._keyword_search(query, n_results, filter_type)

        except Exception as e:
            logger.error(f"search error: {e}")
            try:
                return self._keyword_search(query, n_results, filter_type)
            except Exception:
                return []

    def _keyword_search(self, query: str, n_results: int = 5,
                        filter_type: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Simple keyword search over all stored chunks.
        Works even when no embedding function is available.
        """
        all_chunks = self.get_all_chunks(limit=1000)
        if not all_chunks:
            return []

        q_words = set(query.lower().split())

        scored = []
        for chunk in all_chunks:
            meta = chunk.get("metadata", {})
            if filter_type and meta.get("type") != filter_type:
                continue
            content_lower = chunk["content"].lower()
            hits  = sum(1 for w in q_words if w in content_lower)
            score = hits / max(len(q_words), 1)
            if score > 0:
                scored.append({**chunk, "relevance_score": round(score, 4)})

        scored.sort(key=lambda x: x["relevance_score"], reverse=True)
        return scored[:n_results]

    def count(self) -> int:
        try:
            return self.collection.count()
        except Exception:
            return 0

    def delete_collection(self) -> None:
        try:
            self.client.delete_collection(self.collection_name)
        except Exception:
            pass

    def get_all_chunks(self, limit: int = 500) -> List[Dict[str, Any]]:
        try:
            results = self.collection.get(
                limit=limit,
                include=["documents", "metadatas"]
            )
            if results and results.get("documents"):
                return [
                    {"content": doc, "metadata": meta}
                    for doc, meta in zip(results["documents"], results["metadatas"])
                ]
            return []
        except Exception as e:
            logger.error(f"get_all_chunks error: {e}")
            return []
