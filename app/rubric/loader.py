"""Load and validate the reviewed IELTS Academic rubric data."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

TaskType = Literal["task1", "task2"]
Criterion = Literal[
    "task_achievement",
    "task_response",
    "coherence_and_cohesion",
    "lexical_resource",
    "grammatical_range_and_accuracy",
]

_TASK_CRITERIA: dict[TaskType, tuple[Criterion, ...]] = {
    "task1": (
        "task_achievement",
        "coherence_and_cohesion",
        "lexical_resource",
        "grammatical_range_and_accuracy",
    ),
    "task2": (
        "task_response",
        "coherence_and_cohesion",
        "lexical_resource",
        "grammatical_range_and_accuracy",
    ),
}


@dataclass(frozen=True)
class RubricDescriptor:
    """One Academic descriptor for one task, criterion and band."""

    descriptor_id: str
    task_type: TaskType
    criterion: Criterion
    band: int
    text: str
    source_file: str
    source_page: int


@dataclass(frozen=True)
class RubricGuidance:
    """Operational assessment guidance from the official criteria sheet."""

    guidance_id: str
    scope: str
    task_type: TaskType | None
    criterion: Criterion | None
    points: tuple[str, ...]
    source_file: str
    source_page: int


@dataclass(frozen=True)
class AcademicRubric:
    """Validated Academic Writing rubric and its source metadata."""

    schema_version: str
    exam_type: Literal["academic"]
    source_version: str
    descriptors: tuple[RubricDescriptor, ...]
    guidance: tuple[RubricGuidance, ...]
    policy: dict[str, Any]


def _parse_descriptor(raw: Any, index: int) -> RubricDescriptor:
    if not isinstance(raw, dict):
        raise ValueError(f"descriptors[{index}] 必须是对象")
    required = ("id", "task_type", "criterion", "band", "text")
    if any(key not in raw for key in required):
        raise ValueError(f"descriptors[{index}] 缺少必要字段")
    task_type = raw["task_type"]
    criterion = raw["criterion"]
    band = raw["band"]
    text = raw["text"]
    if task_type not in _TASK_CRITERIA:
        raise ValueError(f"不支持的 task_type: {task_type}")
    if criterion not in _TASK_CRITERIA[task_type]:
        raise ValueError(f"{task_type} 不支持评分维度: {criterion}")
    if isinstance(band, bool) or not isinstance(band, int) or not 0 <= band <= 9:
        raise ValueError(f"评分 band 必须是 0 到 9 的整数: {band}")
    if not isinstance(text, str) or not text.strip():
        raise ValueError(f"descriptors[{index}] 的 text 不能为空")
    if "General Training" in text or "bullet points" in text:
        raise ValueError(f"Academic descriptor 混入 General Training 内容: {raw['id']}")
    descriptor_id = raw["id"]
    source_file = raw.get("source_file")
    source_page = raw.get("source_page")
    if not isinstance(descriptor_id, str) or not descriptor_id.strip():
        raise ValueError(f"descriptors[{index}] 的 id 不能为空")
    if not isinstance(source_file, str) or not source_file.strip():
        raise ValueError(f"{descriptor_id} 缺少来源文件")
    if (
        isinstance(source_page, bool)
        or not isinstance(source_page, int)
        or source_page < 1
    ):
        raise ValueError(f"{descriptor_id} 的 source_page 必须是正整数")
    return RubricDescriptor(
        descriptor_id=descriptor_id,
        task_type=task_type,
        criterion=criterion,
        band=band,
        text=text.strip(),
        source_file=source_file,
        source_page=source_page,
    )


def _parse_guidance(raw: Any, index: int) -> RubricGuidance:
    if not isinstance(raw, dict):
        raise ValueError(f"guidance[{index}] 必须是对象")
    points = raw.get("points")
    if (
        not isinstance(points, list)
        or not points
        or not all(isinstance(point, str) and point.strip() for point in points)
    ):
        raise ValueError(f"guidance[{index}] 的 points 必须是非空字符串列表")
    task_type = raw.get("task_type")
    if task_type is not None and task_type not in _TASK_CRITERIA:
        raise ValueError(f"guidance[{index}] 的 task_type 无效: {task_type}")
    criterion = raw.get("criterion")
    all_criteria = set(_TASK_CRITERIA["task1"]) | set(_TASK_CRITERIA["task2"])
    if criterion is not None and (
        criterion not in all_criteria
        or (task_type is not None and criterion not in _TASK_CRITERIA[task_type])
    ):
        raise ValueError(f"guidance[{index}] 的 criterion 无效: {criterion}")
    guidance_id = raw.get("id")
    scope = raw.get("scope")
    source_file = raw.get("source_file")
    source_page = raw.get("source_page")
    if not isinstance(guidance_id, str) or not guidance_id.strip():
        raise ValueError(f"guidance[{index}] 的 id 不能为空")
    if not isinstance(scope, str) or not scope.strip():
        raise ValueError(f"{guidance_id} 缺少 scope")
    if not isinstance(source_file, str) or not source_file.strip():
        raise ValueError(f"{guidance_id} 缺少来源文件")
    if (
        isinstance(source_page, bool)
        or not isinstance(source_page, int)
        or source_page < 1
    ):
        raise ValueError(f"{guidance_id} 的 source_page 必须是正整数")
    return RubricGuidance(
        guidance_id=guidance_id,
        scope=scope,
        task_type=task_type,
        criterion=criterion,
        points=tuple(point.strip() for point in points),
        source_file=source_file,
        source_page=source_page,
    )


def load_academic_rubric(path: Path) -> AcademicRubric:
    """Read a JSON rubric file and enforce Academic-only coverage."""

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"无法读取评分标准 JSON {path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise ValueError("评分标准根节点必须是 JSON 对象")
    if raw.get("exam_type") != "academic":
        raise ValueError("评分标准资料必须固定为 IELTS Academic")

    descriptor_values = raw.get("descriptors")
    guidance_values = raw.get("guidance")
    if not isinstance(descriptor_values, list) or not isinstance(guidance_values, list):
        raise ValueError("评分标准必须包含 descriptors 和 guidance 列表")
    descriptors = tuple(
        _parse_descriptor(value, index) for index, value in enumerate(descriptor_values)
    )
    guidance = tuple(
        _parse_guidance(value, index) for index, value in enumerate(guidance_values)
    )
    if len(descriptors) != 80 or len(guidance) != 8:
        raise ValueError(
            f"评分资料数量异常: descriptors={len(descriptors)}, guidance={len(guidance)}"
        )
    descriptor_ids = [item.descriptor_id for item in descriptors]
    guidance_ids = [item.guidance_id for item in guidance]
    if len(set(descriptor_ids)) != len(descriptor_ids):
        raise ValueError("评分描述 id 必须唯一")
    if len(set(guidance_ids)) != len(guidance_ids):
        raise ValueError("评分指引 id 必须唯一")
    _validate_coverage(descriptors)
    policy = raw.get("policy")
    if not isinstance(policy, dict):
        raise ValueError("评分标准缺少 policy")
    if (
        policy.get("task1_minimum_words") != 150
        or policy.get("task2_minimum_words") != 250
        or policy.get("task1_criterion") != "task_achievement"
        or policy.get("task2_criterion") != "task_response"
        or policy.get("general_training_task1_included") is not False
    ):
        raise ValueError("评分标准 policy 与 IELTS Academic 写作要求不一致")
    return AcademicRubric(
        schema_version=str(raw.get("schema_version", "")),
        exam_type="academic",
        source_version=str(raw.get("source_version", "")),
        descriptors=descriptors,
        guidance=guidance,
        policy=dict(policy),
    )


def _validate_coverage(descriptors: tuple[RubricDescriptor, ...]) -> None:
    expected = {
        (task_type, criterion, band)
        for task_type, criteria in _TASK_CRITERIA.items()
        for criterion in criteria
        for band in range(10)
    }
    actual = {(item.task_type, item.criterion, item.band) for item in descriptors}
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        raise ValueError(f"评分描述覆盖不完整，缺失={missing}，多余={extra}")
