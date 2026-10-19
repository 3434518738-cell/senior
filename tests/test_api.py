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
