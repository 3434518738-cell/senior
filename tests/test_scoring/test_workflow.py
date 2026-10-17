"""Offline tests for the LangGraph scoring orchestration."""

from __future__ import annotations

from app.scoring.pipeline import ScoringPipeline
from app.scoring.schemas import ScoreRequest
from app.scoring.workflow import ScoringWorkflow

from .test_pipeline import FakeModel, FakeRubricStore, FakeSearcher


def _workflow(task_type: str) -> ScoringWorkflow:
    pipeline = ScoringPipeline(FakeModel(), FakeRubricStore(), FakeSearcher())
    return ScoringWorkflow(pipeline)


def test_task2_workflow_runs_all_four_criteria() -> None:
    report = _workflow("task2").score(
        ScoreRequest(
            task_type="task2",
            question="Discuss both views.",
            essay="This essay uses clear ideas.",
        )
    )
    assert [item.criterion for item in report.criterion_results] == [
        "task_response",
        "coherence_and_cohesion",
        "lexical_resource",
        "grammatical_range_and_accuracy",
    ]


def test_task1_workflow_switches_first_criterion() -> None:
    report = _workflow("task1").score(
        ScoreRequest(
            task_type="task1",
            question="The chart shows changes.",
            essay="This essay uses clear ideas.",
            chart_type="line_graph",
            chart_context="A line graph compares three years.",
        )
    )
    assert report.task_criterion == "task_achievement"
    assert report.criterion_results[0].criterion == "task_achievement"
