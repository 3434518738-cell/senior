"""Build retrieval-sized documents from the available corpus records."""

from __future__ import annotations

import json
from dataclasses import dataclass

from app.rag.corpus_loader import CorpusSample


@dataclass(frozen=True)
class EssayDocument:
    """One whole essay and its prompt; source paragraph boundaries are unknown."""

    document_id: str
    text: str
    metadata: dict[str, str | int | float | bool]


def build_essay_document(sample: CorpusSample) -> EssayDocument:
    """Create one sample-level document without inventing paragraph splits."""

    task_label = "Task 1" if sample.task_type == "task1" else "Task 2"
    content = (
        f"IELTS Academic Writing {task_label}\n"
        f"Title: {sample.title}\n"
        f"Question: {sample.question}\n"
        f"Essay: {sample.answer}"
    )
    metadata: dict[str, str | int | float | bool] = {
        "sample_id": sample.sample_id,
        "exam_type": sample.exam_type,
        "task_type": sample.task_type,
        "title": sample.title,
        "source_pages_json": json.dumps(sample.source_pages),
        "review_flags_json": json.dumps(sample.review_flags, ensure_ascii=False),
        "retrieval_eligible": sample.retrieval_eligible,
    }
    for key in ("question_type", "chart_type", "chart_subtype", "topic"):
        value = getattr(sample, key)
        if value:
            metadata[key] = value
    if sample.reported_word_count is not None:
        metadata["reported_word_count"] = sample.reported_word_count
    if sample.reported_band is not None:
        metadata["reported_band"] = sample.reported_band
    return EssayDocument(document_id=sample.sample_id, text=content, metadata=metadata)
