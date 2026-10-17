"""Build persistent Academic essay indexes with BGE-M3 on CPU."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from app.config import AppSettings, get_settings
from app.rag.chunking import build_essay_document
from app.rag.corpus_loader import TaskType, load_corpus
from app.rag.vector_store import ChromaVectorStore


class Embedder(Protocol):
    """Minimal interface implemented by the existing Ollama client."""

    def embed(self, text: str) -> list[float]:
        """Embed one text using the project's configured local model."""


@dataclass(frozen=True)
class IndexBuildResult:
    """Counts from one task-specific index build."""

    task_type: TaskType
    collection_name: str
    indexed_count: int
    excluded_count: int


class AcademicIndexBuilder:
    """Load samples, create sample-level records and upsert their vectors."""

    def __init__(
        self,
        embedder: Embedder,
        store: ChromaVectorStore,
        settings: AppSettings | None = None,
    ) -> None:
        self.embedder = embedder
        self.store = store
        self.settings = settings or get_settings()
        if self.settings.exam_type != "academic":
            raise ValueError("此索引构建器仅支持 IELTS Academic")

    def build_task(
        self, task_type: TaskType, *, rebuild: bool = False
    ) -> IndexBuildResult:
        """Build or incrementally update a single task collection."""

        all_samples = load_corpus(
            self.settings.corpus_dir,
            task_type,
            include_ineligible=True,
        )
        eligible_samples = [
            sample for sample in all_samples if sample.retrieval_eligible
        ]
        documents = [build_essay_document(sample) for sample in eligible_samples]
        vectors: list[list[float]] = []
        for document in documents:
            vector = self.embedder.embed(document.text)
            if len(vector) != self.settings.embedding_dimension:
                raise ValueError(
                    f"{document.document_id} embedding 维度为 {len(vector)}，"
                    f"预期 {self.settings.embedding_dimension}"
                )
            vectors.append(vector)

        # Do not clear valid stored vectors until all new embeddings have been
        # produced and validated successfully.
        if rebuild:
            self.store.reset(task_type)
        else:
            self.store.remove_stale(
                task_type, {sample.sample_id for sample in eligible_samples}
            )
        self.store.upsert(task_type, documents, vectors)
        return IndexBuildResult(
            task_type=task_type,
            collection_name=self.store.collection_name(task_type),
            indexed_count=len(documents),
            excluded_count=len(all_samples) - len(eligible_samples),
        )

    def build_all(self, *, rebuild: bool = False) -> list[IndexBuildResult]:
        """Build both Academic Writing task collections."""

        return [
            self.build_task("task1", rebuild=rebuild),
            self.build_task("task2", rebuild=rebuild),
        ]


def build_default_index(*, rebuild: bool = False) -> list[IndexBuildResult]:
    """Create the configured Chroma indexes using the local Ollama client."""

    from app.ollama_client import OllamaClient

    settings = get_settings()
    store = ChromaVectorStore(settings=settings)
    with OllamaClient(settings=settings) as client:
        builder = AcademicIndexBuilder(client, store, settings=settings)
        return builder.build_all(rebuild=rebuild)
