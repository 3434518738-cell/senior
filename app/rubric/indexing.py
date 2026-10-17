"""Build and query the separate IELTS Academic rubric collection."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, Sequence

from app.config import AppSettings, get_settings
from app.rubric.loader import (
    AcademicRubric,
    Criterion,
    RubricGuidance,
    TaskType,
    load_academic_rubric,
)

_VALID_CRITERIA: dict[TaskType, set[str]] = {
    "task1": {
        "task_achievement",
        "coherence_and_cohesion",
        "lexical_resource",
        "grammatical_range_and_accuracy",
    },
    "task2": {
        "task_response",
        "coherence_and_cohesion",
        "lexical_resource",
        "grammatical_range_and_accuracy",
    },
}


class Embedder(Protocol):
    """Minimal interface implemented by the Ollama BGE-M3 client."""

    def embed(self, text: str) -> list[float]:
        """Return a vector for text using BGE-M3 on CPU."""


@dataclass(frozen=True)
class RubricDocument:
    """One searchable, source-traceable rubric record."""

    document_id: str
    text: str
    metadata: dict[str, str | int]


@dataclass(frozen=True)
class RubricIndexResult:
    """Summary of a rubric collection rebuild."""

    collection_name: str
    descriptor_count: int
    guidance_count: int


def build_rubric_documents(rubric: AcademicRubric) -> list[RubricDocument]:
    """Convert validated descriptors and guidance into Chroma records."""

    documents: list[RubricDocument] = []
    for descriptor in rubric.descriptors:
        documents.append(
            RubricDocument(
                document_id=descriptor.descriptor_id,
                text=descriptor.text,
                metadata={
                    "exam_type": "academic",
                    "doc_type": "descriptor",
                    "task_type": descriptor.task_type,
                    "criterion": descriptor.criterion,
                    "band": descriptor.band,
                    "source_file": descriptor.source_file,
                    "source_page": descriptor.source_page,
                    "source_version": rubric.source_version,
                },
            )
        )
    for guidance in rubric.guidance:
        documents.append(_guidance_document(guidance, rubric.source_version))
    return documents


def _guidance_document(guidance: RubricGuidance, source_version: str) -> RubricDocument:
    metadata: dict[str, str | int] = {
        "exam_type": "academic",
        "doc_type": "guidance",
        "scope": guidance.scope,
        "source_file": guidance.source_file,
        "source_page": guidance.source_page,
        "source_version": source_version,
    }
    if guidance.task_type:
        metadata["task_type"] = guidance.task_type
    if guidance.criterion:
        metadata["criterion"] = guidance.criterion
    return RubricDocument(
        document_id=guidance.guidance_id,
        text="\n".join(f"- {point}" for point in guidance.points),
        metadata=metadata,
    )


class RubricVectorStore:
    """Persist Academic rubric records separately from example essays."""

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

    def _collection(self) -> Any:
        return self._client.get_or_create_collection(
            name=self.settings.rubric_collection_name,
            metadata={"hnsw:space": "cosine", "exam_type": "academic"},
        )

    def reset(self) -> None:
        """Clear this rubric collection before a complete rebuild."""

        collection = self._collection()
        ids = collection.get().get("ids", [])
        if ids:
            collection.delete(ids=ids)

    def upsert(
        self,
        documents: Sequence[RubricDocument],
        embeddings: Sequence[Sequence[float]],
    ) -> None:
        """Write validated Academic rubric records with explicit vectors."""

        if len(documents) != len(embeddings):
            raise ValueError("rubric documents 与 embeddings 数量不一致")
        if not documents:
            return
        if any(doc.metadata.get("exam_type") != "academic" for doc in documents):
            raise ValueError("评分标准索引只接受 IELTS Academic 资料")
        self._collection().upsert(
            ids=[doc.document_id for doc in documents],
            documents=[doc.text for doc in documents],
            metadatas=[doc.metadata for doc in documents],
            embeddings=[list(vector) for vector in embeddings],
        )

    def descriptors(
        self, task_type: TaskType, criterion: Criterion
    ) -> list[dict[str, Any]]:
        """Fetch all ten official band descriptors for one task criterion."""

        if criterion not in _VALID_CRITERIA[task_type]:
            raise ValueError(f"{task_type} 不支持 Academic 评分维度: {criterion}")
        result = self._collection().get(
            where={
                "$and": [
                    {"exam_type": {"$eq": "academic"}},
                    {"doc_type": {"$eq": "descriptor"}},
                    {"task_type": {"$eq": task_type}},
                    {"criterion": {"$eq": criterion}},
                ]
            },
            include=["documents", "metadatas"],
        )
        rows = _rows_from_get(result)
        rows.sort(key=lambda row: int(row["metadata"]["band"]))
        if [row["metadata"].get("band") for row in rows] != list(range(10)):
            raise RuntimeError(
                f"Academic {task_type}/{criterion} 必须有完整 Band 0–9 描述，"
                f"当前返回 {len(rows)} 条"
            )
        return rows

    def guidance(
        self, task_type: TaskType, criterion: Criterion
    ) -> list[dict[str, Any]]:
        """Fetch task-specific and shared official guidance for a criterion."""

        if criterion not in _VALID_CRITERIA[task_type]:
            raise ValueError(f"{task_type} 不支持 Academic 评分维度: {criterion}")
        result = self._collection().get(
            where={
                "$and": [
                    {"exam_type": {"$eq": "academic"}},
                    {"doc_type": {"$eq": "guidance"}},
                ]
            },
            include=["documents", "metadatas"],
        )
        selected: list[dict[str, Any]] = []
        for row in _rows_from_get(result):
            metadata = row["metadata"]
            row_task = metadata.get("task_type")
            row_criterion = metadata.get("criterion")
            is_task_match = row_task == task_type
            is_shared_match = (
                row_task is None and metadata.get("scope") == "academic_shared"
            )
            is_criterion_match = row_criterion in (criterion, None)
            if (is_task_match or is_shared_match) and is_criterion_match:
                selected.append(row)
        return selected


def _rows_from_get(result: dict[str, Any]) -> list[dict[str, Any]]:
    ids = result.get("ids", [])
    documents = result.get("documents", [])
    metadatas = result.get("metadatas", [])
    rows: list[dict[str, Any]] = []
    for index, document_id in enumerate(ids):
        rows.append(
            {
                "id": document_id,
                "text": documents[index] if index < len(documents) else "",
                "metadata": metadatas[index] if index < len(metadatas) else {},
            }
        )
    return rows


class AcademicRubricIndexer:
    """Validate, CPU-embed and persist the official rubric records."""

    def __init__(
        self,
        embedder: Embedder,
        store: RubricVectorStore,
        settings: AppSettings | None = None,
    ) -> None:
        self.embedder = embedder
        self.store = store
        self.settings = settings or get_settings()
        if self.settings.exam_type != "academic":
            raise ValueError("评分标准索引只支持 IELTS Academic")

    def build(self, rubric_path: Path, *, rebuild: bool = True) -> RubricIndexResult:
        """Build a collection only after every source record embeds cleanly."""

        rubric = load_academic_rubric(rubric_path)
        documents = build_rubric_documents(rubric)
        vectors: list[list[float]] = []
        for document in documents:
            vector = self.embedder.embed(document.text)
            if len(vector) != self.settings.embedding_dimension:
                raise ValueError(
                    f"{document.document_id} 向量维度为 {len(vector)}，"
                    f"预期 {self.settings.embedding_dimension}"
                )
            vectors.append(vector)
        if rebuild:
            self.store.reset()
        self.store.upsert(documents, vectors)
        return RubricIndexResult(
            collection_name=self.settings.rubric_collection_name,
            descriptor_count=len(rubric.descriptors),
            guidance_count=len(rubric.guidance),
        )


def build_default_rubric_index(
    rubric_path: Path | None = None, *, rebuild: bool = True
) -> RubricIndexResult:
    """Build the local rubric index with BGE-M3 explicitly on CPU."""

    from app.ollama_client import OllamaClient

    settings = get_settings()
    source = rubric_path or Path("docs/rubrics/academic_writing_rubric.json")
    store = RubricVectorStore(settings=settings)
    with OllamaClient(settings=settings) as client:
        indexer = AcademicRubricIndexer(client, store, settings=settings)
        return indexer.build(source, rebuild=rebuild)


def retrieve_rubric_context(
    store: RubricVectorStore, task_type: TaskType, criterion: Criterion
) -> dict[str, list[dict[str, Any]]]:
    """Return complete official band descriptors and relevant guidance."""

    return {
        "descriptors": store.descriptors(task_type, criterion),
        "guidance": store.guidance(task_type, criterion),
    }
