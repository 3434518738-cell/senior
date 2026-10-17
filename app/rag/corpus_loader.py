"""Load and validate the reviewed Task 1 and Task 2 source records."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

TaskType = Literal["task1", "task2"]
ExamType = Literal["academic"]

_EXCLUDED_REVIEW_FLAGS = {
    "source_contains_incomplete_instruction_fragment",
    "source_answer_ends_without_terminal_punctuation",
}


@dataclass(frozen=True)
class CorpusSample:
    """A validated source essay with its retrieval eligibility decision."""

    sample_id: str
    exam_type: ExamType
    task_type: TaskType
    title: str
    question: str
    answer: str
    source_pages: tuple[int, ...]
    question_type: str | None
    chart_type: str | None
    chart_subtype: str | None
    topic: str | None
    reported_word_count: int | None
    reported_band: float | None
    review_flags: tuple[str, ...]
    retrieval_eligible: bool


def _optional_string(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _parse_sample(path: Path, expected_task: TaskType) -> CorpusSample:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"无法读取语料 JSON {path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise ValueError(f"语料记录必须是 JSON 对象: {path}")

    sample_id = raw.get("sample_id")
    question = raw.get("question")
    answer = raw.get("answer")
    task_type = raw.get("task_type")
    exam_type = raw.get("exam_type")
    if not isinstance(sample_id, str) or not sample_id.strip():
        raise ValueError(f"语料缺少有效 sample_id: {path}")
    if sample_id != path.stem:
        raise ValueError(f"sample_id 与文件名不一致: {path}")
    if task_type != expected_task:
        raise ValueError(f"{sample_id} 的 task_type 应为 {expected_task}")
    if exam_type != "academic":
        raise ValueError(
            f"{sample_id} 的 exam_type 必须显式为 academic，拒绝混入其他模块语料"
        )
    if not isinstance(question, str) or not question.strip():
        raise ValueError(f"{sample_id} 缺少 question")
    if not isinstance(answer, str) or not answer.strip():
        raise ValueError(f"{sample_id} 缺少 answer")

    question_type = _optional_string(raw.get("question_type"))
    chart_type = _optional_string(raw.get("chart_type"))
    if expected_task == "task1" and (not question_type or not chart_type):
        raise ValueError(
            f"{sample_id} 缺少 Academic Task 1 必需的 question_type/chart_type"
        )

    pages = raw.get("source_pages")
    if (
        not isinstance(pages, list)
        or not pages
        or any(not isinstance(page, int) or page < 1 for page in pages)
    ):
        raise ValueError(f"{sample_id} 的 source_pages 无效")

    flags_value = raw.get("review_flags", [])
    if not isinstance(flags_value, list) or any(
        not isinstance(flag, str) for flag in flags_value
    ):
        raise ValueError(f"{sample_id} 的 review_flags 无效")
    flags = tuple(flags_value)
    eligible = not any(flag in _EXCLUDED_REVIEW_FLAGS for flag in flags)

    word_count = raw.get("reported_word_count")
    if word_count is not None and (not isinstance(word_count, int) or word_count < 0):
        word_count = None
    band = raw.get("reported_band")
    if band is not None and not isinstance(band, (int, float)):
        band = None

    return CorpusSample(
        sample_id=sample_id,
        exam_type="academic",
        task_type=expected_task,
        title=_optional_string(raw.get("title")) or sample_id,
        question=question.strip(),
        answer=answer.strip(),
        source_pages=tuple(pages),
        question_type=question_type,
        chart_type=chart_type,
        chart_subtype=_optional_string(raw.get("chart_subtype")),
        topic=_optional_string(raw.get("topic")),
        reported_word_count=word_count,
        reported_band=float(band) if band is not None else None,
        review_flags=flags,
        retrieval_eligible=eligible,
    )


def load_corpus(
    corpus_dir: Path,
    task_type: TaskType | None = None,
    *,
    include_ineligible: bool = False,
) -> list[CorpusSample]:
    """Load reviewed samples, excluding source-marked records by default.

    Task 1's printed/chart mismatch is retained as a review flag but remains
    searchable using the corrected chart-aligned question. Incomplete source
    prompts and the incomplete Task 2 source ending are kept out of retrieval.
    """

    if task_type not in (None, "task1", "task2"):
        raise ValueError(f"不支持的 IELTS Academic task_type: {task_type}")
    task_types: tuple[TaskType, ...] = (
        (task_type,) if task_type is not None else ("task1", "task2")
    )
    samples: list[CorpusSample] = []
    seen_ids: set[str] = set()
    for current_task in task_types:
        folder = corpus_dir / current_task
        if not folder.is_dir():
            raise FileNotFoundError(f"找不到语料目录: {folder}")
        for path in sorted(folder.glob("*.json")):
            sample = _parse_sample(path, current_task)
            if sample.sample_id in seen_ids:
                raise ValueError(f"重复 sample_id: {sample.sample_id}")
            seen_ids.add(sample.sample_id)
            if include_ineligible or sample.retrieval_eligible:
                samples.append(sample)
    return samples
