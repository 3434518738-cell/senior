"""Offline tests for the unified three-entry-point practice service."""

from __future__ import annotations

import base64

import pytest
from pydantic import ValidationError

from app.scoring.pipeline import ScoringPipeline
from app.scoring.schemas import (
    ChartUnderstanding,
    UnifiedPracticeRequest,
)
from app.scoring.workflow import ScoringWorkflow
from app.services.practice import PracticeService

from tests.test_scoring.test_pipeline import FakeModel, FakeRubricStore, FakeSearcher


def _service() -> tuple[PracticeService, FakeModel]:
    model = FakeModel()
    pipeline = ScoringPipeline(model, FakeRubricStore(), FakeSearcher())
    workflow = ScoringWorkflow(pipeline)
    return PracticeService(pipeline, workflow), model


def test_upload_image_cannot_skip_visual_confirmation() -> None:
    image = base64.b64encode(b"\x89PNG\r\n\x1a\nimage").decode("ascii")

    with pytest.raises(ValidationError, match="必须先识图并确认"):
        UnifiedPracticeRequest(
            mode="upload",
            task_type="task1",
            question="Summarise the chart.",
            essay="This essay uses clear ideas.",
            chart_type="line_graph",
            chart_image_base64=image,
        )


def test_confirmed_upload_uses_reviewed_visual_facts_and_returns_references() -> None:
    service, model = _service()
    visual = ChartUnderstanding(
        visual_type="chart",
        chart_type="line_graph",
        chart_summary="A line graph comparing two series.",
        axes_or_categories=["2000", "2020"],
        series=[],
    )
    response = service.score(
        UnifiedPracticeRequest(
            mode="upload",
            task_type="task1",
            question="Summarise the chart.",
            essay="This essay uses clear ideas.",
            chart_type="line_graph",
            visual_understanding=visual,
            visual_confirmed=True,
        )
    )

    assert response.mode == "upload"
    assert response.report.chart_understanding == visual
    assert response.retrieved_samples[0].sample_id == "sample_1"
    assert response.retrieved_samples[0].task_type == "task1"
    assert all(call["images"] is None for call in model.calls)
    assert any("Confirmed visual facts" in call["prompt"] for call in model.calls)


def test_task2_question_bank_uses_same_unified_score_contract() -> None:
    service, _ = _service()
    response = service.score(
        UnifiedPracticeRequest(
            mode="question_bank",
            task_type="task2",
            question="Discuss both views.",
            essay="This essay uses clear ideas.",
        )
    )

    assert response.mode == "question_bank"
    assert response.task_type == "task2"
    assert response.report.task_criterion == "task_response"
