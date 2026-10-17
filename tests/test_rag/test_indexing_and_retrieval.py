"""Unit tests for index-build policy and Academic retrieval filters."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from app.config import AppSettings
from app.rag.indexing import AcademicIndexBuilder
from app.rag.retrieval import AcademicRetriever
from app.rag.vector_store import ChromaVectorStore


def _write_sample(root: Path, sample_id: str, task_type: str, flags: list[str]) -> None:
    folder = root / task_type
    folder.mkdir(parents=True, exist_ok=True)
    payload = {
        "sample_id": sample_id,
        "exam_type": "academic",
        "task_type": task_type,
        "title": sample_id,
        "question": "A prompt",
        "answer": "An answer",
        "source_pages": [1],
        "question_type": "line_graph" if task_type == "task1" else "opinion",
        "chart_type": "line_graph" if task_type == "task1" else None,
        "review_flags": flags,
    }
    (folder / f"{sample_id}.json").write_text(json.dumps(payload), encoding="utf-8")


class FakeEmbedder:
    def __init__(self, vector: list[float] | None = None) -> None:
        self.vector = vector or [0.1, 0.2, 0.3]
        self.calls: list[str] = []

    def embed(self, text: str) -> list[float]:
        self.calls.append(text)
        return self.vector


class FakeCollection:
    def __init__(self) -> None:
        self.rows: dict[str, dict[str, Any]] = {}
        self.last_query: dict[str, Any] | None = None

    def get(self) -> dict[str, list[str]]:
        return {"ids": list(self.rows)}

    def upsert(
        self,
        ids: list[str],
        documents: list[str],
        metadatas: list[dict],
        embeddings: list[list[float]],
    ) -> None:
        for doc_id, text, metadata, embedding in zip(
            ids, documents, metadatas, embeddings
        ):
            self.rows[doc_id] = {
                "text": text,
                "metadata": metadata,
                "embedding": embedding,
            }

    def delete(self, ids: list[str]) -> None:
        for doc_id in ids:
            self.rows.pop(doc_id, None)

    def query(self, **kwargs: Any) -> dict[str, list[list[Any]]]:
        self.last_query = kwargs
        return {"ids": [[]], "documents": [[]], "metadatas": [[]], "distances": [[]]}


class FakeChromaClient:
    def __init__(self) -> None:
        self.collections: dict[str, FakeCollection] = {}

    def get_or_create_collection(
        self, name: str, metadata: dict[str, str]
    ) -> FakeCollection:
        assert metadata["exam_type"] == "academic"
        self.collections.setdefault(name, FakeCollection())
        return self.collections[name]


def test_index_builder_excludes_incomplete_source_records(tmp_path: Path) -> None:
    _write_sample(tmp_path, "task1_014", "task1", [])
    _write_sample(
        tmp_path,
        "task1_016",
        "task1",
        ["source_contains_incomplete_instruction_fragment"],
    )
    settings = AppSettings(
        _env_file=None,
        corpus_dir=tmp_path,
        embedding_dimension=3,
        exam_type="academic",
    )
    embedder = FakeEmbedder()
    store = ChromaVectorStore(settings=settings, chroma_client=FakeChromaClient())
    builder = AcademicIndexBuilder(embedder, store, settings=settings)

    result = builder.build_task("task1", rebuild=True)

    assert result.indexed_count == 1
    assert result.excluded_count == 1
    collection = store._collection("task1")
    assert list(collection.rows) == ["task1_014"]
    assert collection.rows["task1_014"]["metadata"]["exam_type"] == "academic"


def test_retriever_hard_filters_to_academic_task_and_chart_type() -> None:
    fake_client = FakeChromaClient()
    settings = AppSettings(_env_file=None, embedding_dimension=3)
    store = ChromaVectorStore(settings=settings, chroma_client=fake_client)
    embedder = FakeEmbedder()
    retriever = AcademicRetriever(embedder, store, settings=settings)

    assert retriever.search("line chart prompt", "task1", chart_type="line_graph") == []
    collection = store._collection("task1")
    assert collection.last_query is not None
    assert collection.last_query["where"] == {
        "$and": [
            {"exam_type": {"$eq": "academic"}},
            {"task_type": {"$eq": "task1"}},
            {"retrieval_eligible": {"$eq": True}},
            {"chart_type": {"$eq": "line_graph"}},
        ]
    }


def test_non_academic_configuration_is_rejected() -> None:
    with pytest.raises(ValueError):
        AppSettings(_env_file=None, exam_type="general_training")  # type: ignore[arg-type]


def test_loader_rejects_general_training_samples(tmp_path: Path) -> None:
    _write_sample(tmp_path, "task2_001", "task2", [])
    path = tmp_path / "task2" / "task2_001.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["exam_type"] = "general_training"
    path.write_text(json.dumps(payload), encoding="utf-8")
    settings = AppSettings(_env_file=None, corpus_dir=tmp_path)
    store = ChromaVectorStore(settings=settings, chroma_client=FakeChromaClient())
    builder = AcademicIndexBuilder(FakeEmbedder(), store, settings=settings)

    with pytest.raises(ValueError, match="exam_type 必须显式为 academic"):
        builder.build_task("task2")


def test_incremental_build_clears_records_newly_marked_ineligible(
    tmp_path: Path,
) -> None:
    _write_sample(tmp_path, "task2_001", "task2", [])
    settings = AppSettings(
        _env_file=None,
        corpus_dir=tmp_path,
        embedding_dimension=3,
        exam_type="academic",
    )
    store = ChromaVectorStore(settings=settings, chroma_client=FakeChromaClient())
    builder = AcademicIndexBuilder(FakeEmbedder(), store, settings=settings)
    builder.build_task("task2")
    assert list(store._collection("task2").rows) == ["task2_001"]

    path = tmp_path / "task2" / "task2_001.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["review_flags"] = ["source_answer_ends_without_terminal_punctuation"]
    path.write_text(json.dumps(payload), encoding="utf-8")
    result = builder.build_task("task2")

    assert result.indexed_count == 0
    assert result.excluded_count == 1
    assert store._collection("task2").rows == {}


def test_failed_rebuild_preserves_existing_vectors(tmp_path: Path) -> None:
    _write_sample(tmp_path, "task2_001", "task2", [])
    settings = AppSettings(
        _env_file=None,
        corpus_dir=tmp_path,
        embedding_dimension=3,
        exam_type="academic",
    )
    embedder = FakeEmbedder()
    store = ChromaVectorStore(settings=settings, chroma_client=FakeChromaClient())
    builder = AcademicIndexBuilder(embedder, store, settings=settings)
    builder.build_task("task2", rebuild=True)

    embedder.vector = [0.1, 0.2]
    with pytest.raises(ValueError, match="embedding 维度"):
        builder.build_task("task2", rebuild=True)

    assert list(store._collection("task2").rows) == ["task2_001"]


def test_retriever_rejects_zero_top_k() -> None:
    store = ChromaVectorStore(
        settings=AppSettings(_env_file=None, embedding_dimension=3),
        chroma_client=FakeChromaClient(),
    )
    retriever = AcademicRetriever(FakeEmbedder(), store)

    with pytest.raises(ValueError, match="top_k 必须大于 0"):
        retriever.search("prompt", "task2", top_k=0)
