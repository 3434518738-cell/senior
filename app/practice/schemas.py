"""API contracts for question-bank and practice-session operations."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.rag.corpus_loader import TaskType
from app.scoring.schemas import (
    ChartUnderstanding,
    UnifiedPracticeResponse,
)


class QuestionSummary(BaseModel):
    """A question-bank item safe to show before an essay is submitted."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    question_id: str
    exam_type: Literal["academic"] = "academic"
    task_type: TaskType
    title: str
    question: str
    chart_image_url: str | None = None
    question_type: str | None = None
    chart_type: str | None = None
    chart_subtype: str | None = None
    topic: str | None = None
    source_pages: list[int] = Field(default_factory=list)


class QuestionListResponse(BaseModel):
    """Paginated question-bank response."""

    items: list[QuestionSummary]
    limit: int
    offset: int


class PracticeSessionCreateRequest(BaseModel):
    """Create one daily pair or one selected question-bank session."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    mode: Literal["daily", "question_bank"]
    task_type: TaskType | None = None
    question_id: str | None = Field(default=None, min_length=1)
    duration_seconds: int | None = Field(default=None, ge=0, le=7200)
    question_ids: list[Annotated[str, Field(min_length=1)]] | None = Field(
        default=None, min_length=2, max_length=2
    )

    @model_validator(mode="after")
    def validate_mode(self) -> "PracticeSessionCreateRequest":
        if self.mode == "daily":
            if self.task_type or self.question_id:
                raise ValueError("每日一练请通过 question_ids 选择两道题")
            if not self.question_ids or len(set(self.question_ids)) != 2:
                raise ValueError("每日一练请先选择 Task 1 和 Task 2 各一道题")
        elif not self.task_type or not self.question_id:
            raise ValueError("专项练习必须指定 task_type 和 question_id")
        elif self.question_ids is not None:
            raise ValueError("专项练习请通过 question_id 选择一道题")
        return self


class PracticeSessionItem(BaseModel):
    """One question inside a practice session."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    item_order: int
    question_id: str
    task_type: TaskType
    title: str
    question: str
    chart_image_url: str | None = None
    question_type: str | None = None
    chart_type: str | None = None
    chart_subtype: str | None = None
    topic: str | None = None
    source_pages: list[int] = Field(default_factory=list)
    essay: str | None = None
    report: dict[str, object] | None = None
    submitted_at: str | None = None


class PracticeSessionResponse(BaseModel):
    """Session state returned to a client."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    session_id: str
    mode: Literal["daily", "question_bank"]
    status: Literal["active", "submitted"]
    duration_seconds: int | None = None
    started_at: str
    submitted_at: str | None = None
    items: list[PracticeSessionItem]


class PracticeSessionSubmitRequest(BaseModel):
    """Essay payload for one item in an existing session."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    item_order: int = Field(ge=0, le=10)
    essay: str = Field(min_length=1)
    chart_context: str | None = Field(default=None, min_length=1)
    chart_image_base64: str | None = Field(default=None, max_length=14_000_000)
    visual_understanding: ChartUnderstanding | None = None
    visual_confirmed: bool = False


class PracticeSessionSubmissionResponse(BaseModel):
    """Saved session state plus the unified scoring response."""

    session: PracticeSessionResponse
    result: UnifiedPracticeResponse
