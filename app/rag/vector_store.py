"""Small Chroma adapter with no built-in embedding function.

Embeddings are supplied explicitly by the project Ollama client so BGE-M3
continues to run on CPU through ``num_gpu=0``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Sequence

from app.config import AppSettings, get_settings
from app.rag.chunking import EssayDocument
from app.rag.corpus_loader import TaskType


class ChromaVectorStore:
    """Persist academic Task 1 and Task 2 samples in separate collections."""

    def __init__(
        self,
        persist_directory: Path | None = None,
        settings: AppSettings | None = None,
        chroma_client: Any | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.persist_directory = persist_directory or self.settings.chroma_persist_dir
        if chroma_client is None:
            try:
                import chromadb
            except ImportError as exc:
                raise RuntimeError(
                    "缺少 chromadb 依赖，请运行：python -m pip install -r requirements.txt"
                ) from exc
            self.persist_directory.mkdir(parents=True, exist_ok=True)
            chroma_client = chromadb.PersistentClient(path=str(self.persist_directory))
        self._client = chroma_client

    def collection_name(self, task_type: TaskType) -> str:
        """Return the configured Academic collection for a task type."""

        if task_type == "task1":
            return self.settings.task1_collection_name
        if task_type == "task2":
            return self.settings.task2_collection_name
        raise ValueError(f"不支持的 IELTS Academic task_type: {task_type}")

    def _collection(self, task_type: TaskType) -> Any:
        return self._client.get_or_create_collection(
            name=self.collection_name(task_type),
            metadata={"hnsw:space": "cosine", "exam_type": "academic"},
        )

    def reset(self, task_type: TaskType) -> None:
        """Remove all documents in one collection before a full rebuild."""

        collection = self._collection(task_type)
        document_ids = collection.get().get("ids", [])
        if document_ids:
            collection.delete(ids=document_ids)

    def remove_stale(self, task_type: TaskType, valid_ids: set[str]) -> None:
        """Delete records absent from the current eligible source corpus."""

        collection = self._collection(task_type)
        stored_ids = collection.get().get("ids", [])
        stale_ids = [
            document_id for document_id in stored_ids if document_id not in valid_ids
        ]
        if stale_ids:
            collection.delete(ids=stale_ids)

    def upsert(
        self,
        task_type: TaskType,
        documents: Sequence[EssayDocument],
        embeddings: Sequence[Sequence[float]],
    ) -> None:
        """Insert or update documents using caller-provided CPU embeddings."""

        if len(documents) != len(embeddings):
            raise ValueError("documents 与 embeddings 数量不一致")
        if not documents:
            return
        for document in documents:
            if document.metadata.get("exam_type") != "academic":
                raise ValueError("只允许索引 IELTS Academic 语料")
            if document.metadata.get("task_type") != task_type:
                raise ValueError("文档 task_type 与目标 Chroma collection 不一致")
        self._collection(task_type).upsert(
            ids=[document.document_id for document in documents],
            documents=[document.text for document in documents],
            metadatas=[document.metadata for document in documents],
            embeddings=[list(vector) for vector in embeddings],
        )

    def query(
        self,
        task_type: TaskType,
        embedding: Sequence[float],
        *,
        top_k: int,
        question_type: str | None = None,
        chart_type: str | None = None,
    ) -> list[dict[str, Any]]:
        """Search one Academic task collection with metadata filters."""

        if top_k < 1:
            raise ValueError("top_k 必须大于 0")
        clauses: list[dict[str, Any]] = [
            {"exam_type": {"$eq": "academic"}},
            {"task_type": {"$eq": task_type}},
            {"retrieval_eligible": {"$eq": True}},
        ]
        if question_type:
            clauses.append({"question_type": {"$eq": question_type}})
        if chart_type:
            clauses.append({"chart_type": {"$eq": chart_type}})
        result = self._collection(task_type).query(
            query_embeddings=[list(embedding)],
            n_results=top_k,
            where={"$and": clauses},
            include=["documents", "metadatas", "distances"],
        )
        ids = result.get("ids", [[]])
        documents = result.get("documents", [[]])
        metadatas = result.get("metadatas", [[]])
        distances = result.get("distances", [[]])
        rows: list[dict[str, Any]] = []
        for index, document_id in enumerate(ids[0] if ids else []):
            rows.append(
                {
                    "id": document_id,
                    "text": documents[0][index] if documents and documents[0] else "",
                    "metadata": (
                        metadatas[0][index] if metadatas and metadatas[0] else {}
                    ),
                    "distance": (
                        distances[0][index] if distances and distances[0] else None
                    ),
                }
            )
        return rows
