"""Pydantic schemas for strict, Academic-only scoring requests and reports."""

from __future__ import annotations

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
EstimateStatus = Literal["reliable", "unreliable_under_minimum_words"]


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

    @model_validator(mode="after")
    def validate_task_context(self) -> "ScoreRequest":
        """Require chart information before assessing Academic Task 1."""

        if self.task_type == "task1":
            if not self.chart_type:
                raise ValueError("Academic Task 1 必须提供 chart_type")
            if not self.chart_context:
                raise ValueError(
                    "Academic Task 1 必须提供 chart_context 或图表数据描述"
                )
        return self


class EvidenceItem(BaseModel):
    """One evidence-grounded observation from the submitted essay."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    quote: str = Field(min_length=1)
    explanation: str = Field(min_length=1)


class CriterionResult(BaseModel):
    """A single criterion assessment returned by the local model."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    criterion: Criterion
    band: Annotated[float, Field(ge=0, le=9)]
    rationale: str = Field(min_length=1)
    evidence: list[EvidenceItem] = Field(default_factory=list)
    strengths: list[Annotated[str, Field(min_length=1)]] = Field(default_factory=list)
    issues: list[EvidenceItem] = Field(default_factory=list)
    improvements: list[Annotated[str, Field(min_length=1)]] = Field(
        default_factory=list
    )

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
