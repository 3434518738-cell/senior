"""Unit tests for the reviewed corpus loader and sample-level documents."""

from __future__ import annotations

import json
from pathlib import Path

from app.rag.chunking import build_essay_document
from app.rag.corpus_loader import load_corpus


def _write_sample(
    root: Path,
    sample_id: str,
    task_type: str,
    flags: list[str] | None = None,
) -> None:
    folder = root / task_type
    folder.mkdir(parents=True, exist_ok=True)
    payload = {
        "sample_id": sample_id,
        "exam_type": "academic",
        "task_type": task_type,
        "title": "A reviewed essay",
        "question": "Describe the chart or discuss the issue.",
        "answer": "A complete answer with its original paragraph breaks.\nSecond paragraph.",
        "source_pages": [1, 2],
        "question_type": "line_graph" if task_type == "task1" else "opinion",
        "chart_type": "line_graph" if task_type == "task1" else None,
        "topic": "education",
        "review_flags": flags or [],
        "reported_word_count": 170,
        "reported_band": 9,
    }
    (folder / f"{sample_id}.json").write_text(
        json.dumps(payload, ensure_ascii=False), encoding="utf-8"
    )


def test_loader_excludes_source_fragments_and_keeps_chart_mismatch(
    tmp_path: Path,
) -> None:
    _write_sample(
        tmp_path,
        "task1_014",
        "task1",
        ["printed_prompt_mismatched_with_chart_corrected_using_source_chart"],
    )
    _write_sample(
        tmp_path,
        "task1_016",
        "task1",
        ["source_contains_incomplete_instruction_fragment"],
    )

    samples = load_corpus(tmp_path, "task1")

    assert [sample.sample_id for sample in samples] == ["task1_014"]
    assert samples[0].retrieval_eligible is True
    assert samples[0].review_flags
    all_samples = load_corpus(tmp_path, "task1", include_ineligible=True)
    assert len(all_samples) == 2
    assert all_samples[1].retrieval_eligible is False


def test_sample_document_is_academic_and_does_not_fake_chunks(tmp_path: Path) -> None:
    _write_sample(tmp_path, "task2_001", "task2")
    sample = load_corpus(tmp_path, "task2")[0]

    document = build_essay_document(sample)

    assert document.document_id == "task2_001"
    assert document.text.startswith("IELTS Academic Writing Task 2")
    assert "Question: Describe the chart or discuss the issue." in document.text
    assert "Second paragraph." in document.text
    assert document.metadata["exam_type"] == "academic"
    assert document.metadata["source_pages_json"] == "[1, 2]"
    assert document.metadata["question_type"] == "opinion"
