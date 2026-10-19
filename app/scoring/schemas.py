"""Pydantic schemas for strict, Academic-only scoring requests and reports."""

from __future__ import annotations

import base64
import binascii
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

TaskType = Literal["task1", "task2"]
Criterion = Literal[
    "task_achievement",
    "task_response",
    "coherence_and_cohesion",
    "lexical_resource",
    "grammatical_range_and_accuracy",
]
TaskCriterion = Literal["task_achievement", "task_response"]
TaskCheckKey = Literal[
    "overview",
    "key_feature_selection",
    "data_accuracy",
    "comparisons",
    "visual_scope",
    "prompt_coverage",
    "position",
    "idea_development",
    "support",
    "relevance",
]
CheckStatus = Literal["met", "partial", "missing", "not_verifiable"]
EstimateStatus = Literal["reliable", "unreliable_under_minimum_words"]

TASK1_REVIEW_KEYS = {
    "overview",
    "key_feature_selection",
    "data_accuracy",
    "comparisons",
    "visual_scope",
}
TASK2_REVIEW_KEYS = {
    "prompt_coverage",
    "position",
    "idea_development",
    "support",
    "relevance",
}


def expected_criteria(task_type: TaskType) -> tuple[Criterion, ...]:
    """Return the four official criteria for one Academic writing task."""

    first: TaskCriterion = (
        "task_achievement" if task_type == "task1" else "task_response"
    )
    return (
        first,
        "coherence_and_cohesion",
        "lexical_resource",
        "grammatical_range_and_accuracy",
    )


def _validate_band(value: float) -> float:
    """Allow only IELTS half-band values from 0.0 to 9.0."""

    if not 0 <= value <= 9:
        raise ValueError("band 必须在 0 到 9 之间")
    doubled = Decimal(str(value)) * 2
    if doubled != doubled.to_integral_value():
        raise ValueError("band 只能使用整数或 0.5 档位")
    return float(value)


def _validate_band_input(value: object) -> object:
    """Reject booleans and strings before Pydantic converts numeric values."""

    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("band 必须是数字")
    return value


class ScoreRequest(BaseModel):
    """One explicit IELTS Academic task submitted for scoring."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    exam_type: Literal["academic"] = "academic"
    task_type: TaskType
    question: str = Field(min_length=1)
    essay: str = Field(min_length=1)
    chart_type: str | None = Field(default=None, min_length=1)
    chart_context: str | None = Field(default=None, min_length=1)
    chart_image_base64: str | None = Field(default=None, max_length=14_000_000)

    @model_validator(mode="after")
    def validate_task_context(self) -> "ScoreRequest":
        """Require chart information before assessing Academic Task 1."""

        if self.task_type == "task1":
            if not self.chart_type:
                raise ValueError("Academic Task 1 必须提供 chart_type")
            if not self.chart_context and not self.chart_image_base64:
                raise ValueError(
                    "Academic Task 1 必须提供 chart_context 或 chart_image_base64"
                )
            if self.chart_image_base64:
                try:
                    image = base64.b64decode(self.chart_image_base64, validate=True)
                except (binascii.Error, ValueError) as exc:
                    raise ValueError("chart_image_base64 不是有效的 Base64") from exc
                if not image or len(image) > 10_000_000:
                    raise ValueError("图表图片必须小于 10 MB")
                valid_signatures = (
                    image.startswith(b"\x89PNG\r\n\x1a\n"),
                    image.startswith(b"\xff\xd8\xff"),
                    image.startswith((b"GIF87a", b"GIF89a")),
                    image.startswith(b"RIFF") and image[8:12] == b"WEBP",
                )
                if not any(valid_signatures):
                    raise ValueError("图表图片格式仅支持 PNG、JPEG、GIF 或 WebP")
        return self


class EvidenceItem(BaseModel):
    """One evidence-grounded observation from the submitted essay."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    quote: str | None = None
    explanation: str = Field(min_length=1, max_length=240)


class TaskFulfilmentCheck(BaseModel):
    """One explicit task-fulfilment check grounded in the submitted essay."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    key: TaskCheckKey
    status: CheckStatus
    quote: str | None = None
    explanation: str = Field(min_length=1, max_length=240)


class TaskFulfilmentReview(BaseModel):
    """Task-specific review supporting Academic TA or TR judgements."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    checks: list[TaskFulfilmentCheck] = Field(min_length=5, max_length=5)

    @model_validator(mode="after")
    def validate_unique_checks(self) -> "TaskFulfilmentReview":
        keys = [check.key for check in self.checks]
        if len(set(keys)) != len(keys):
            raise ValueError("task_review 检查项不能重复")
        return self


class ChartDataPoint(BaseModel):
    """One value transcribed from an uploaded Academic Task 1 visual."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    label: str = Field(min_length=1, max_length=80)
    value: float
    precision: Literal["explicit", "estimated"]


class ChartSeries(BaseModel):
    """Named data series and its image-derived values."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=80)
    points: list[ChartDataPoint] = Field(max_length=100)
    trend: str = Field(default="", max_length=240)


class ChartStructure(BaseModel):
    """Task 1 visual structure identified before extracting its details."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    visual_type: Literal["chart", "process", "map"] = "chart"
    chart_type: str = Field(min_length=1, max_length=80)
    title: str = Field(default="", max_length=240)
    x_axis: str = Field(default="", max_length=160)
    y_axis: str = Field(default="", max_length=160)
    categories: list[str] = Field(default_factory=list, max_length=100)
    series_names: list[str] = Field(default_factory=list, max_length=20)
    has_explicit_data_labels: bool = False
    process_stages: list["ProcessStage"] = Field(default_factory=list, max_length=40)
    map_features: list["MapFeature"] = Field(default_factory=list, max_length=80)


class ProcessStage(BaseModel):
    """One ordered stage and its outgoing links in a process diagram."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    order: int = Field(ge=0, le=100)
    label: str = Field(min_length=1, max_length=160)
    next_steps: list[str] = Field(default_factory=list, max_length=10)


class MapFeature(BaseModel):
    """One location or change represented in a map task."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    location: str = Field(min_length=1, max_length=160)
    direction: str = Field(default="", max_length=80)
    before: str = Field(default="", max_length=160)
    after: str = Field(default="", max_length=160)
    change_type: str = Field(default="", max_length=80)


class ChartValueExtraction(BaseModel):
    """Compact retry result for values omitted in the first visual pass."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    series: list[ChartSeries] = Field(min_length=1, max_length=20)
    uncertain_or_unreadable: list[str] = Field(default_factory=list, max_length=20)


class ChartUnderstanding(BaseModel):
    """Structured reading of a chart, process diagram, or map."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    visual_type: Literal["chart", "process", "map"] = "chart"
    chart_type: str = Field(default="", max_length=80)
    chart_summary: str = Field(min_length=1, max_length=400)
    axes_or_categories: list[str] = Field(default_factory=list, max_length=30)
    series: list[ChartSeries] = Field(default_factory=list, max_length=20)
    process_stages: list[ProcessStage] = Field(default_factory=list, max_length=40)
    map_features: list[MapFeature] = Field(default_factory=list, max_length=80)
    uncertain_or_unreadable: list[str] = Field(default_factory=list, max_length=20)


class VisualInspectionRequest(BaseModel):
    """Request to inspect an Academic Task 1 image before essay scoring."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    exam_type: Literal["academic"] = "academic"
    task_type: Literal["task1"] = "task1"
    chart_image_base64: str = Field(min_length=1, max_length=14_000_000)

    @field_validator("chart_image_base64")
    @classmethod
    def validate_image(cls, value: str) -> str:
        """Reject malformed or unsupported image payloads before Ollama."""

        try:
            image = base64.b64decode(value, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise ValueError("chart_image_base64 不是有效的 Base64") from exc
        valid_signatures = (
            image.startswith(b"\x89PNG\r\n\x1a\n"),
            image.startswith(b"\xff\xd8\xff"),
            image.startswith((b"GIF87a", b"GIF89a")),
            image.startswith(b"RIFF") and image[8:12] == b"WEBP",
        )
        if not image or len(image) > 10_000_000 or not any(valid_signatures):
            raise ValueError("图表图片必须是小于 10 MB 的 PNG、JPEG、GIF 或 WebP")
        return value


class QuestionImageUnderstanding(BaseModel):
    """Question text read from a photographed IELTS writing prompt."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    question_text: str = Field(min_length=1, max_length=4000)
    uncertain_or_unreadable: list[str] = Field(default_factory=list, max_length=20)


PracticeMode = Literal["daily", "question_bank", "upload"]


class UnifiedPracticeRequest(BaseModel):
    """One submission shape shared by daily, bank, and upload workflows."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    exam_type: Literal["academic"] = "academic"
    mode: PracticeMode
    task_type: TaskType
    question: str | None = Field(default=None, min_length=1)
    essay: str = Field(min_length=1)
    chart_type: str | None = Field(default=None, min_length=1)
    chart_context: str | None = Field(default=None, min_length=1)
    question_image_base64: str | None = Field(default=None, max_length=14_000_000)
    chart_image_base64: str | None = Field(default=None, max_length=14_000_000)
    visual_understanding: ChartUnderstanding | None = None
    visual_confirmed: bool = False

    @field_validator("chart_image_base64")
    @classmethod
    def validate_image(cls, value: str | None) -> str | None:
        """Validate optional source images before sending them to Ollama."""

        if value is None:
            return None
        return VisualInspectionRequest.validate_image(value)

    @field_validator("question_image_base64")
    @classmethod
    def validate_question_image(cls, value: str | None) -> str | None:
        """Validate the photographed question sheet before OCR."""

        if value is None:
            return None
        return VisualInspectionRequest.validate_image(value)

    @model_validator(mode="after")
    def validate_submission(self) -> "UnifiedPracticeRequest":
        """Require an image for uploads and preserve stored questions for sessions."""

        if self.mode == "upload":
            if self.task_type == "task2" and not self.question_image_base64:
                raise ValueError("Task 2 上传模式必须提供题目图片")
            if self.task_type == "task1" and not (
                self.question_image_base64 or self.chart_image_base64
            ):
                raise ValueError("Task 1 上传模式必须提供题目图片")
        elif not self.question:
            raise ValueError("每日一练和题库练习必须包含系统题目")

        if self.task_type == "task2":
            if (
                any(
                    value is not None
                    for value in (
                        self.chart_type,
                        self.chart_context,
                        self.chart_image_base64,
                        self.visual_understanding,
                    )
                )
                or self.visual_confirmed
            ):
                raise ValueError("Academic Task 2 不能携带 Task 1 图片事实")
            return self
        # A user-uploaded photo is the original input.  Its visual type and
        # chart type are discovered by Qwen in the service layer, so callers
        # do not need to transcribe or classify the image first.
        if (
            not self.chart_type
            and not self.chart_image_base64
            and not self.question_image_base64
            and not self.visual_understanding
        ):
            raise ValueError("Academic Task 1 必须提供 chart_type 或题目图片")
        if self.visual_understanding is not None and not self.visual_confirmed:
            raise ValueError("提交评分前必须确认 visual_understanding")
        if not (
            self.chart_context
            or self.chart_image_base64
            or self.question_image_base64
            or self.visual_understanding
        ):
            raise ValueError(
                "Academic Task 1 必须提供 chart_context 或已确认的视觉事实"
            )
        return self


class RetrievedSampleReference(BaseModel):
    """Safe, short reference to a retrieved Academic example."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    sample_id: str = Field(min_length=1, max_length=160)
    task_type: TaskType
    question_type: str | None = None
    chart_type: str | None = None
    excerpt: str = Field(default="", max_length=500)
    distance: float | None = None


class CriterionResult(BaseModel):
    """A single criterion assessment returned by the local model."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    criterion: Criterion
    band: Annotated[float, Field(ge=0, le=9)]
    rationale: str = Field(min_length=1, max_length=600)
    evidence: list[EvidenceItem] = Field(default_factory=list, max_length=2)
    strengths: list[Annotated[str, Field(min_length=1, max_length=240)]] = Field(
        default_factory=list, max_length=2
    )
    issues: list[EvidenceItem] = Field(default_factory=list, max_length=2)
    improvements: list[Annotated[str, Field(min_length=1, max_length=240)]] = Field(
        default_factory=list, max_length=2
    )
    task_review: TaskFulfilmentReview | None

    @field_validator("band")
    @classmethod
    def validate_band(cls, value: float) -> float:
        """Reject unsupported quarter-band values."""

        return _validate_band(value)

    @field_validator("band", mode="before")
    @classmethod
    def validate_band_type(cls, value: object) -> object:
        """Keep the model response numeric instead of accepting numeric strings."""

        return _validate_band_input(value)

    @model_validator(mode="after")
    def validate_task_review(self) -> "CriterionResult":
        """Require a checklist only for the task-specific criterion."""

        expected_keys: set[str] | None = None
        if self.criterion == "task_achievement":
            expected_keys = TASK1_REVIEW_KEYS
        elif self.criterion == "task_response":
            expected_keys = TASK2_REVIEW_KEYS
        if expected_keys is None:
            if self.task_review is not None:
                raise ValueError("仅 Task Achievement/Task Response 可包含 task_review")
        elif self.task_review is None:
            raise ValueError("Task Achievement/Task Response 必须提供 task_review")
        elif {check.key for check in self.task_review.checks} != expected_keys:
            raise ValueError("task_review 检查项必须与 Task 类型完全匹配")
        return self


class ScoreReport(BaseModel):
    """Complete, validated report for one essay (not the official writing score)."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    exam_type: Literal["academic"] = "academic"
    task_type: TaskType
    task_criterion: TaskCriterion
    word_count: int = Field(ge=0)
    minimum_word_count: int = Field(ge=1)
    criterion_results: list[CriterionResult] = Field(min_length=4, max_length=4)
    essay_band_estimate: Annotated[float | None, Field(ge=0, le=9)] = None
    estimate_status: EstimateStatus = "reliable"
    warnings: list[str] = Field(default_factory=list)
    chart_understanding: ChartUnderstanding | None = None
    processing_time_ms: int = Field(ge=0)
    rubric_version: str = Field(min_length=1)

    @field_validator("essay_band_estimate")
    @classmethod
    def validate_estimate_band(cls, value: float | None) -> float | None:
        """Ensure the aggregate uses an IELTS half-band value."""

        return None if value is None else _validate_band(value)

    @field_validator("essay_band_estimate", mode="before")
    @classmethod
    def validate_estimate_type(cls, value: object) -> object:
        """Keep the aggregate numeric instead of accepting numeric strings."""

        if value is None:
            return None
        return _validate_band_input(value)

    @model_validator(mode="after")
    def validate_criteria(self) -> "ScoreReport":
        """Ensure all and only the task's four criteria are present."""

        expected_minimum = 150 if self.task_type == "task1" else 250
        if self.minimum_word_count != expected_minimum:
            raise ValueError(f"{self.task_type} 的最低字数必须为 {expected_minimum}")
        if self.word_count < expected_minimum:
            if self.estimate_status != "unreliable_under_minimum_words":
                raise ValueError("低于最低字数时必须标记为不可靠估分")
            if self.essay_band_estimate is not None:
                raise ValueError("低于最低字数时不能返回 Band 估分")
        elif self.estimate_status == "unreliable_under_minimum_words":
            raise ValueError("达到最低字数后不能标记为字数不足估分")
        elif self.essay_band_estimate is None:
            raise ValueError("可靠估分必须包含 essay_band_estimate")

        expected = set(expected_criteria(self.task_type))
        actual = [item.criterion for item in self.criterion_results]
        if len(set(actual)) != 4 or set(actual) != expected:
            raise ValueError(
                f"{self.task_type} 的评分维度必须为 {sorted(expected)}，当前为 {actual}"
            )
        expected_task_criterion: TaskCriterion = (
            "task_achievement" if self.task_type == "task1" else "task_response"
        )
        if self.task_criterion != expected_task_criterion:
            raise ValueError("task_criterion 与 task_type 不匹配")
        return self


class UnifiedPracticeResponse(BaseModel):
    """Unified result returned by all three practice entry points."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    mode: PracticeMode
    task_type: TaskType
    recognized_question: QuestionImageUnderstanding | None = None
    report: ScoreReport
    retrieved_samples: list[RetrievedSampleReference] = Field(default_factory=list)
