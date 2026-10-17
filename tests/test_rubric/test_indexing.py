"""Tests for Academic rubric vector indexing and deterministic context lookup."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from app.config import AppSettings
from app.rubric.indexing import (
    AcademicRubricIndexer,
    RubricVectorStore,
    retrieve_rubric_context,
)

RUBRIC_PATH = Path("docs/rubrics/academic_writing_rubric.json")


class FakeEmbedder:
    def __init__(self, dimension: int = 3) -> None:
        self.dimension = dimension
        self.calls: list[str] = []

    def embed(self, text: str) -> list[float]:
        self.calls.append(text)
        return [0.1] * self.dimension


class FakeCollection:
    def __init__(self) -> None:
        self.rows: dict[str, dict[str, Any]] = {}

    def get(
        self,
        where: dict[str, Any] | None = None,
        include: list[str] | None = None,
    ) -> dict[str, list[Any]]:
        records = [
            (doc_id, row)
            for doc_id, row in self.rows.items()
            if where is None or _matches(row["metadata"], where)
        ]
        return {
            "ids": [doc_id for doc_id, _ in records],
            "documents": [row["text"] for _, row in records],
            "metadatas": [row["metadata"] for _, row in records],
        }

    def upsert(
        self,
        ids: list[str],
        documents: list[str],
        metadatas: list[dict[str, Any]],
        embeddings: list[list[float]],
    ) -> None:
        for doc_id, document, metadata, vector in zip(
            ids, documents, metadatas, embeddings
        ):
            self.rows[doc_id] = {
                "text": document,
                "metadata": metadata,
                "embedding": vector,
            }

    def delete(self, ids: list[str]) -> None:
        for doc_id in ids:
            self.rows.pop(doc_id, None)


class FakeChromaClient:
    def __init__(self) -> None:
        self.collections: dict[str, FakeCollection] = {}

    def get_or_create_collection(
        self, name: str, metadata: dict[str, Any]
    ) -> FakeCollection:
        assert metadata["exam_type"] == "academic"
        self.collections.setdefault(name, FakeCollection())
        return self.collections[name]


def _matches(metadata: dict[str, Any], clause: dict[str, Any]) -> bool:
    if "$and" in clause:
        return all(_matches(metadata, item) for item in clause["$and"])
    return all(
        metadata.get(key) == condition.get("$eq") for key, condition in clause.items()
    )


def _build_index(
    tmp_path: Path, *, embedder: FakeEmbedder | None = None
) -> tuple[RubricVectorStore, FakeEmbedder]:
    settings = AppSettings(
        _env_file=None,
        chroma_persist_dir=tmp_path,
        embedding_dimension=3,
        exam_type="academic",
    )
    client = FakeChromaClient()
    store = RubricVectorStore(settings=settings, chroma_client=client)
    active_embedder = embedder or FakeEmbedder()
    indexer = AcademicRubricIndexer(active_embedder, store, settings=settings)
    indexer.build(RUBRIC_PATH)
    return store, active_embedder


def test_build_indexes_all_academic_descriptors_and_guidance(tmp_path: Path) -> None:
    store, embedder = _build_index(tmp_path)

    collection = store._collection()
    assert len(collection.rows) == 88
    assert len(embedder.calls) == 88
    assert all(
        row["metadata"]["exam_type"] == "academic" for row in collection.rows.values()
    )
    assert (
        sum(
            row["metadata"]["doc_type"] == "descriptor"
            for row in collection.rows.values()
        )
        == 80
    )
    assert (
        sum(
            row["metadata"]["doc_type"] == "guidance"
            for row in collection.rows.values()
        )
        == 8
    )


def test_context_returns_all_bands_and_correct_academic_criterion(
    tmp_path: Path,
) -> None:
    store, _ = _build_index(tmp_path)

    task1_context = retrieve_rubric_context(store, "task1", "task_achievement")
    task2_context = retrieve_rubric_context(store, "task2", "task_response")

    assert [row["metadata"]["band"] for row in task1_context["descriptors"]] == list(
        range(10)
    )
    assert all(
        row["metadata"]["criterion"] == "task_achievement"
        and row["metadata"]["task_type"] == "task1"
        for row in task1_context["descriptors"]
    )
    assert all(
        row["metadata"]["criterion"] == "task_response"
        and row["metadata"]["task_type"] == "task2"
        for row in task2_context["descriptors"]
    )
    assert task1_context["guidance"]
    assert task2_context["guidance"]


def test_task1_cannot_request_task2_response_standard(tmp_path: Path) -> None:
    store, _ = _build_index(tmp_path)

    with pytest.raises(ValueError, match="不支持 Academic 评分维度"):
        store.descriptors("task1", "task_response")  # type: ignore[arg-type]


def test_bad_embedding_does_not_clear_existing_rubric_index(tmp_path: Path) -> None:
    store, _ = _build_index(tmp_path)
    previous_ids = set(store._collection().rows)
    wrong_embedder = FakeEmbedder(dimension=2)
    indexer = AcademicRubricIndexer(
        wrong_embedder,
        store,
        settings=AppSettings(_env_file=None, embedding_dimension=3),
    )

    with pytest.raises(ValueError, match="向量维度"):
        indexer.build(RUBRIC_PATH)

    assert set(store._collection().rows) == previous_ids


def test_rubric_source_has_unique_ids() -> None:
    raw = json.loads(RUBRIC_PATH.read_text(encoding="utf-8"))
    descriptor_ids = [item["id"] for item in raw["descriptors"]]
    guidance_ids = [item["id"] for item in raw["guidance"]]
    assert len(descriptor_ids) == len(set(descriptor_ids))
    assert len(guidance_ids) == len(set(guidance_ids))
