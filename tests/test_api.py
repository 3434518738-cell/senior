"""API contract tests using an injected, offline scoring workflow."""

from __future__ import annotations

import base64

from fastapi.testclient import TestClient

from app.api import create_app
from app.scoring.pipeline import ScoringPipeline
from app.scoring.workflow import ScoringWorkflow

from tests.test_scoring.test_pipeline import FakeModel, FakeRubricStore, FakeSearcher


def _client() -> TestClient:
    pipeline = ScoringPipeline(FakeModel(), FakeRubricStore(), FakeSearcher())
    return TestClient(create_app(ScoringWorkflow(pipeline)))


def test_health_endpoint_reports_academic_mode() -> None:
    with _client() as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "exam_type": "academic"}


def test_local_frontend_home_is_available() -> None:
    with _client() as client:
        response = client.get("/")
        assets = client.get("/assets/styles.css")
    assert response.status_code == 200
    assert "把题目拍下来" in response.text
    assert assets.status_code == 200


def test_score_endpoint_returns_validated_academic_report() -> None:
    with _client() as client:
        response = client.post(
            "/api/v1/score",
            json={
                "task_type": "task2",
                "question": "Discuss both views.",
                "essay": "This essay uses clear ideas.",
            },
        )
    assert response.status_code == 200
    report = response.json()
    assert report["exam_type"] == "academic"
    assert report["task_criterion"] == "task_response"
    assert len(report["criterion_results"]) == 4
    assert report["essay_band_estimate"] is None
    assert report["estimate_status"] == "unreliable_under_minimum_words"


def test_score_endpoint_rejects_general_training() -> None:
    with _client() as client:
        response = client.post(
            "/api/v1/score",
            json={
                "exam_type": "general_training",
                "task_type": "task2",
                "question": "Write a letter.",
                "essay": "This essay uses clear ideas.",
            },
        )
    assert response.status_code == 422


def test_unified_practice_endpoint_returns_mode_and_retrieved_samples() -> None:
    with _client() as client:
        response = client.post(
            "/api/v1/practice/score",
            json={
                "mode": "daily",
                "task_type": "task2",
                "question": "Discuss both views.",
                "essay": "This essay uses clear ideas.",
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["mode"] == "daily"
    assert payload["task_type"] == "task2"
    assert payload["report"]["task_criterion"] == "task_response"
    assert payload["retrieved_samples"][0]["sample_id"] == "sample_1"


def test_task1_inspect_endpoint_returns_visual_facts_before_scoring() -> None:
    image = base64.b64encode(b"\x89PNG\r\n\x1a\nmock-image-data").decode("ascii")
    with _client() as client:
        response = client.post(
            "/api/v1/task1/inspect",
            json={"chart_image_base64": image},
        )

    assert response.status_code == 200
    assert response.json()["visual_type"] == "chart"
    assert response.json()["series"][0]["name"] == "Car"


def test_unified_task1_endpoint_accepts_photo_without_manual_chart_context() -> None:
    image = base64.b64encode(b"\x89PNG\r\n\x1a\nmock-image-data").decode("ascii")
    with _client() as client:
        response = client.post(
            "/api/v1/practice/score",
            json={
                "mode": "upload",
                "task_type": "task1",
                "question": "Summarise the chart.",
                "essay": "This essay uses clear ideas.",
                "chart_image_base64": image,
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["report"]["chart_understanding"]["chart_type"] == "line_graph"
    assert any("自动识别" in warning for warning in payload["report"]["warnings"])


def test_unified_task2_endpoint_reads_question_from_photo() -> None:
    image = base64.b64encode(b"\x89PNG\r\n\x1a\nmock-question-photo").decode("ascii")
    with _client() as client:
        response = client.post(
            "/api/v1/practice/score",
            json={
                "mode": "upload",
                "task_type": "task2",
                "essay": "This essay uses clear ideas.",
                "question_image_base64": image,
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert "transport" in payload["recognized_question"]["question_text"]


def test_question_bank_and_daily_session_endpoints_are_connected() -> None:
    with _client() as client:
        question_response = client.get(
            "/api/v1/question-bank", params={"task_type": "task2", "limit": 1}
        )
        assert question_response.status_code == 200
        question = question_response.json()["items"][0]

        bank_session = client.post(
            "/api/v1/practice/sessions",
            json={
                "mode": "question_bank",
                "task_type": "task2",
                "question_id": question["question_id"],
            },
        )
        assert bank_session.status_code == 200
        assert len(bank_session.json()["items"]) == 1

        daily_session = client.post(
            "/api/v1/practice/sessions",
            json={"mode": "daily", "daily_date": "2026-10-19"},
        )
        assert daily_session.status_code == 200
        assert [item["task_type"] for item in daily_session.json()["items"]] == [
            "task1",
            "task2",
        ]
