"""Offline tests for Academic scoring schema rules."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.scoring.schemas import CriterionResult, ScoreReport, ScoreRequest


def _result(criterion: str, band: float = 7.0) -> dict[str, object]:
    task_review = None
    if criterion == "task_achievement":
        keys = [
            "overview",
            "key_feature_selection",
            "data_accuracy",
            "comparisons",
            "visual_scope",
        ]
    elif criterion == "task_response":
        keys = [
            "prompt_coverage",
            "position",
            "idea_development",
            "support",
            "relevance",
        ]
    else:
        keys = []
    if keys:
        task_review = {
            "checks": [
                {
                    "key": key,
                    "status": "partial",
                    "quote": None,
                    "explanation": "Needs further development.",
                }
                for key in keys
            ]
        }
    return {
        "criterion": criterion,
        "band": band,
        "rationale": "The response is clear.",
        "evidence": [],
        "strengths": ["clear progression"],
        "issues": [],
        "improvements": ["add more precise support"],
        "task_review": task_review,
    }


def test_task1_requires_chart_context() -> None:
    with pytest.raises(ValidationError, match="chart_type"):
        ScoreRequest(task_type="task1", question="Describe the chart", essay="text")


def test_task1_can_use_chart_image_instead_of_text_context() -> None:
    import base64

    image = base64.b64encode(b"\x89PNG\r\n\x1a\nimage-data").decode()
    request = ScoreRequest(
        task_type="task1",
        question="Describe the chart",
        essay="text",
        chart_type="line_graph",
        chart_image_base64=image,
    )
    assert request.chart_context is None


def test_task1_rejects_invalid_chart_image_encoding() -> None:
    with pytest.raises(ValidationError, match="Base64"):
        ScoreRequest(
            task_type="task1",
            question="Describe the chart",
            essay="text",
            chart_type="line_graph",
            chart_image_base64="not-base64!",
        )


def test_task2_does_not_require_chart_context() -> None:
    request = ScoreRequest(
        task_type="task2", question="Discuss both views.", essay="Some essay."
    )
    assert request.exam_type == "academic"


def test_criterion_rejects_quarter_band_and_extra_fields() -> None:
    with pytest.raises(ValidationError, match="0.5"):
        CriterionResult.model_validate(_result("task_response", 7.25))
    payload = _result("task_response")
    payload["unexpected"] = True
    with pytest.raises(ValidationError, match="unexpected"):
        CriterionResult.model_validate(payload)
    with pytest.raises(ValidationError, match="必须是数字"):
        CriterionResult.model_validate(_result("task_response", "7.0"))  # type: ignore[arg-type]
    empty_strength = _result("task_response")
    empty_strength["strengths"] = [""]
    with pytest.raises(ValidationError, match="at least 1 character"):
        CriterionResult.model_validate(empty_strength)


def test_task_criterion_requires_matching_review_checklist() -> None:
    missing = _result("task_response")
    missing["task_review"] = None
    with pytest.raises(ValidationError, match="必须提供 task_review"):
        CriterionResult.model_validate(missing)

    wrong = _result("task_response")
    wrong["task_review"] = _result("task_achievement")["task_review"]
    with pytest.raises(ValidationError, match="完全匹配"):
        CriterionResult.model_validate(wrong)

    unrelated = _result("lexical_resource")
    unrelated["task_review"] = _result("task_response")["task_review"]
    with pytest.raises(ValidationError, match="仅 Task Achievement"):
        CriterionResult.model_validate(unrelated)


def test_report_requires_exact_task_criteria() -> None:
    results = [
        _result("task_response"),
        _result("coherence_and_cohesion"),
        _result("lexical_resource"),
        _result("grammatical_range_and_accuracy"),
    ]
    report = ScoreReport(
        task_type="task2",
        task_criterion="task_response",
        word_count=250,
        minimum_word_count=250,
        criterion_results=results,
        essay_band_estimate=7.0,
        processing_time_ms=1,
        rubric_version="Updated May 2023",
    )
    assert report.essay_band_estimate == 7.0

    results[0] = _result("task_achievement")
    with pytest.raises(ValidationError, match="评分维度"):
        ScoreReport(
            task_type="task2",
            task_criterion="task_response",
            word_count=250,
            minimum_word_count=250,
            criterion_results=results,
            essay_band_estimate=7.0,
            processing_time_ms=1,
            rubric_version="Updated May 2023",
        )
