"""Academic sample retrieval with task and chart-type filters."""

from __future__ import annotations

from typing import Any

from app.config import AppSettings, get_settings
from app.rag.corpus_loader import TaskType
from app.rag.vector_store import ChromaVectorStore


class AcademicRetriever:
    """Retrieve similar essays without crossing Academic task collections."""

    def __init__(
        self,
        embedder: Any,
        store: ChromaVectorStore,
        settings: AppSettings | None = None,
    ) -> None:
        self.embedder = embedder
        self.store = store
        self.settings = settings or get_settings()
        if self.settings.exam_type != "academic":
            raise ValueError("此检索器仅支持 IELTS Academic")

    def search(
        self,
        query: str,
        task_type: TaskType,
        *,
        question_type: str | None = None,
        chart_type: str | None = None,
        top_k: int | None = None,
    ) -> list[dict[str, Any]]:
        """Retrieve the closest eligible samples for an Academic prompt."""

        if not query.strip():
            raise ValueError("检索内容不能为空")
        requested_top_k = top_k if top_k is not None else self.settings.retrieval_top_k
        if requested_top_k < 1:
            raise ValueError("top_k 必须大于 0")
        embedding = self.embedder.embed(query)
        if len(embedding) != self.settings.embedding_dimension:
            raise ValueError(
                f"查询向量维度为 {len(embedding)}，"
                f"预期 {self.settings.embedding_dimension}"
            )
        return self.store.query(
            task_type,
            embedding,
            top_k=requested_top_k,
            question_type=question_type,
            chart_type=chart_type,
        )
