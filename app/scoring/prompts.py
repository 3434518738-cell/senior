"""Prompt construction for one strict JSON criterion assessment."""

from __future__ import annotations

import json
from typing import Any

from app.scoring.schemas import Criterion, ScoreRequest


def build_criterion_prompt(
    request: ScoreRequest,
    cleaned_essay: str,
    criterion: Criterion,
    rubric_context: dict[str, list[dict[str, Any]]],
    sample_context: list[dict[str, Any]],
    *,
    word_count: int | None = None,
) -> str:
    """Build a grounded prompt that asks Qwen for one criterion only."""

    rubric_json = json.dumps(rubric_context, ensure_ascii=False, indent=2)
    examples = "\n\n".join(
        f"Sample {index}: {row.get('text', '')[:1200]}"
        for index, row in enumerate(sample_context[:3], start=1)
    )
    chart = ""
    if request.task_type == "task1":
        chart = (
            f"\nChart type: {request.chart_type}\n"
            f"Chart context/data description: {request.chart_context}\n"
        )
    minimum_words = 150 if request.task_type == "task1" else 250
    measured_word_count = (
        word_count if word_count is not None else len(cleaned_essay.split())
    )
    length_boundary = (
        "The essay is below the required minimum length. Treat all criterion "
        "bands as provisional diagnostics only: do not infer missing development, "
        "and do not award a high band merely because the task is mentioned."
        if measured_word_count < minimum_words
        else (
            "The essay meets the minimum word-count gate; still judge task "
            "fulfilment from substantive evidence."
        )
    )
    return f"""You are an IELTS Academic Writing examiner.
Assess exactly one criterion: {criterion}.
Task type: Academic {request.task_type}.
Question: {request.question}{chart}

Official Academic rubric context (compare the essay against all supplied bands):
{rubric_json}

Retrieved Simon-style samples are examples of organisation and language only.
Do not use their reported scores as labels or as a scoring anchor:
{examples or "(no sample was retrieved)"}

Essay (quote evidence exactly from this text):
{cleaned_essay}

Word count: {measured_word_count}. Minimum for Academic {request.task_type}: {minimum_words}.
Boundary instruction: {length_boundary}

Return only valid JSON with exactly these fields:
{{"criterion":"{criterion}","band":7.0,"rationale":"...",
"evidence":[{{"quote":"exact text from essay","explanation":"..."}}],
"strengths":["..."],"issues":[{{"quote":"exact text from essay","explanation":"..."}}],
"improvements":["..."]}}
The band must be 0.0 to 9.0 in 0.5 increments. Do not add markdown or extra fields.
"""
