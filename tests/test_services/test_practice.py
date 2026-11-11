"""Offline tests for the unified three-entry-point practice service."""

from __future__ import annotations

import base64
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.scoring.pipeline import ScoringPipeline
from app.scoring.schemas import (
    ChartUnderstanding,
    UnifiedPracticeRequest,
)
from app.scoring.workflow import ScoringWorkflow
from app.practice.repository import QuestionBankRepository
from app.services.practice import PracticeService

from tests.test_scoring.test_pipeline import FakeModel, FakeRubricStore, FakeSearcher


ROOT = Path(__file__).resolve().parents[2]


def _service(
    repository: QuestionBankRepository | None = None,
) -> tuple[PracticeService, FakeModel]:
    model = FakeModel()
    pipeline = ScoringPipeline(model, FakeRubricStore(), FakeSearcher())
    workflow = ScoringWorkflow(pipeline)
    return PracticeService(pipeline, workflow, repository), model


def test_uploaded_image_is_inspected_automatically_before_scoring() -> None:
    image = base64.b64encode(b"\x89PNG\r\n\x1a\nimage").decode("ascii")
    service, model = _service()

    request = UnifiedPracticeRequest(
        mode="upload",
        task_type="task1",
        essay="This essay uses clear ideas.",
        chart_image_base64=image,
    )
    response = service.score(request)

    assert response.report.chart_understanding is not None
    assert response.report.chart_understanding.chart_type == "line_graph"
    assert any("自动识别" in warning for warning in response.report.warnings)
    assert sum(call["images"] == [image] for call in model.calls) == 3
    assert all(call["images"] is None for call in model.calls[3:])


def test_confirmed_upload_uses_reviewed_visual_facts_without_sample_rag() -> None:
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
            essay="This essay uses clear ideas.",
            chart_type="line_graph",
            question_image_base64=base64.b64encode(
                b"\x89PNG\r\n\x1a\nquestion-photo"
            ).decode("ascii"),
            visual_understanding=visual,
            visual_confirmed=True,
        )
    )

    assert response.mode == "upload"
    assert response.report.chart_understanding == visual
    assert response.retrieved_samples == []
    assert response.improvement_plan is None
    assert service.pipeline.sample_searcher.calls == []
    assert response.report.essay_band_estimate is None
    assert model.calls[0]["images"] is not None
    assert all(call["images"] is None for call in model.calls[1:])
    assert "A sample essay." not in model.calls[1]["prompt"]
    assert not any("学习教练" in call["prompt"] for call in model.calls)
    assert any("Structured visual facts" in call["prompt"] for call in model.calls)


def test_task2_question_bank_uses_same_unified_score_contract_without_samples() -> None:
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
    assert response.retrieved_samples == []
    assert service.pipeline.sample_searcher.calls == []


def test_daily_practice_adds_sample_learning_after_independent_scoring() -> None:
    service, model = _service()
    response = service.score(
        UnifiedPracticeRequest(
            mode="daily",
            task_type="task2",
            question="Discuss both views.",
            essay="This essay uses clear ideas.",
        )
    )
    assert response.improvement_plan is not None
    assert response.improvement_plan.sample_lessons[0].sample_quote == "A sample essay."
    assert response.retrieved_samples[0].sample_id == "sample_1"
    assert len(service.pipeline.sample_searcher.calls) == 1
    assert all("A sample essay." not in call["prompt"] for call in model.calls[:4])
    assert "学习教练" in model.calls[-1]["prompt"]


@pytest.mark.parametrize("failure_mode", ["invalid_json", "english_feedback"])
def test_sample_lesson_failure_does_not_fail_the_scoring_result(
    failure_mode: str,
) -> None:
    service, model = _service()
    original_generate = model.generate

    def fail_only_learning_plan(prompt: str, **kwargs: object) -> str:
        if "你是 IELTS Academic 写作学习教练" in prompt:
            if failure_mode == "invalid_json":
                return "not valid JSON"
            payload = json.loads(original_generate(prompt, **kwargs))
            payload["sample_lessons"][0]["how_to_apply"] = "Add an explanation."
            return json.dumps(payload)
        return original_generate(prompt, **kwargs)

    model.generate = fail_only_learning_plan  # type: ignore[method-assign]
    response = service.score(
        UnifiedPracticeRequest(
            mode="daily",
            task_type="task2",
            question="Discuss both views.",
            essay="This essay uses clear ideas.",
        )
    )

    assert len(response.report.criterion_results) == 4
    assert response.improvement_plan is None
    assert any("原评分结果不受影响" in warning for warning in response.report.warnings)


def test_question_bank_session_submission_persists_unified_report(
    tmp_path: Path,
) -> None:
    repository = QuestionBankRepository(
        tmp_path / "practice.sqlite3", ROOT / "data" / "corpus_staging"
    )
    service, _ = _service(repository)
    question = service.list_questions(task_type="task2", limit=1).items[0]
    session = service.start_session(
        {
            "mode": "question_bank",
            "task_type": "task2",
            "question_id": question.question_id,
        }
    )

    result = service.submit_session_item(
        session.session_id,
        {"item_order": 0, "essay": "This essay uses clear ideas."},
    )

    assert result.session.status == "submitted"
    assert result.session.items[0].report is not None
    assert result.result.mode == "question_bank"


def test_task1_session_submission_can_use_a_photo_without_manual_chart_context(
    tmp_path: Path,
) -> None:
    image = base64.b64encode(b"\x89PNG\r\n\x1a\nimage").decode("ascii")
    repository = QuestionBankRepository(
        tmp_path / "practice.sqlite3", ROOT / "data" / "corpus_staging"
    )
    service, _ = _service(repository)
    question = service.list_questions(task_type="task1", limit=1).items[0]
    session = service.start_session(
        {
            "mode": "question_bank",
            "task_type": "task1",
            "question_id": question.question_id,
        }
    )

    result = service.submit_session_item(
        session.session_id,
        {
            "item_order": 0,
            "essay": "This essay uses clear ideas.",
            "chart_image_base64": image,
        },
    )

    assert result.result.report.chart_understanding is not None
    assert any("自动识别" in warning for warning in result.result.report.warnings)


def test_task1_daily_submission_automatically_uses_question_bank_image(
    tmp_path: Path,
) -> None:
    repository = QuestionBankRepository(
        tmp_path / "practice.sqlite3", ROOT / "data" / "corpus_staging"
    )
    service, model = _service(repository)
    chosen = [
        service.list_questions(task_type=task, limit=1).items[0].question_id
        for task in ("task1", "task2")
    ]
    session = service.start_session({"mode": "daily", "question_ids": chosen})
    image_path = (
        ROOT
        / "frontend"
        / "assets"
        / "question-images"
        / Path(session.items[0].chart_image_url or "").name
    )

    result = service.submit_session_item(
        session.session_id,
        {"item_order": 0, "essay": "This essay uses clear ideas."},
    )

    expected_image = base64.b64encode(image_path.read_bytes()).decode("ascii")
    assert any(call["images"] == [expected_image] for call in model.calls)
    assert result.result.report.chart_understanding is not None


def test_task1_without_image_context_or_visual_facts_is_rejected() -> None:
    with pytest.raises(ValidationError):
        UnifiedPracticeRequest(
            mode="upload",
            task_type="task1",
            essay="This essay uses clear ideas.",
        )


def test_upload_task2_reads_question_from_photo_before_scoring() -> None:
    image = base64.b64encode(b"\x89PNG\r\n\x1a\nquestion-photo").decode("ascii")
    service, model = _service()

    response = service.score(
        UnifiedPracticeRequest(
            mode="upload",
            task_type="task2",
            essay="This essay uses clear ideas.",
            question_image_base64=image,
        )
    )

    assert response.recognized_question is not None
    assert "transport" in response.recognized_question.question_text
    assert any("recognized_question" in warning for warning in response.report.warnings)
    assert model.calls[0]["images"] == [image]
    assert all(call["images"] is None for call in model.calls[1:])


def test_upload_task1_can_use_one_photo_for_question_and_visual() -> None:
    image = base64.b64encode(b"\x89PNG\r\n\x1a\nquestion-and-chart").decode("ascii")
    service, _ = _service()

    response = service.score(
        UnifiedPracticeRequest(
            mode="upload",
            task_type="task1",
            essay="This essay uses clear ideas.",
            question_image_base64=image,
        )
    )

    assert response.recognized_question is not None
    assert response.report.chart_understanding is not None
