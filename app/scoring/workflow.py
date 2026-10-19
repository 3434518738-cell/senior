"""LangGraph orchestration for the Academic writing scoring pipeline."""

from __future__ import annotations

import time
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from app.scoring.pipeline import (
    ScoringPipeline,
    ScoringPreparation,
)
from app.scoring.schemas import (
    Criterion,
    CriterionResult,
    ScoreReport,
    ScoreRequest,
    expected_criteria,
)


class ScoringWorkflowState(TypedDict, total=False):
    """State passed between validation, retrieval, criterion, and aggregation nodes."""

    request: ScoreRequest | dict[str, Any]
    preparation: ScoringPreparation
    started_at: float
    criterion_results: dict[str, CriterionResult]
    report: ScoreReport


def _validate_input(
    state: ScoringWorkflowState, *, pipeline: ScoringPipeline
) -> dict[str, Any]:
    started_at = time.perf_counter()
    preparation = pipeline.prepare(state["request"])
    return {
        "preparation": preparation,
        "started_at": started_at,
    }


def _score_criterion_node(
    state: ScoringWorkflowState,
    *,
    pipeline: ScoringPipeline,
    criterion: Criterion,
) -> dict[str, Any]:
    preparation = state["preparation"]
    result = pipeline.score_criterion(preparation, criterion)
    previous = dict(state.get("criterion_results", {}))
    previous[criterion] = result
    return {"criterion_results": previous}


def _aggregate(
    state: ScoringWorkflowState, *, pipeline: ScoringPipeline
) -> dict[str, Any]:
    preparation = state["preparation"]
    results_by_criterion = state.get("criterion_results", {})
    criteria = expected_criteria(preparation.request.task_type)
    if set(results_by_criterion) != set(criteria):
        missing = sorted(set(criteria) - set(results_by_criterion))
        raise RuntimeError(f"LangGraph 评分维度不完整，缺少: {missing}")
    results = [results_by_criterion[criterion] for criterion in criteria]
    return {
        "report": pipeline.build_report(
            preparation, results, start_time=state["started_at"]
        )
    }


def build_scoring_graph(pipeline: ScoringPipeline) -> Any:
    """Build and compile the four-criterion Academic scoring graph.

    Retrieval is performed once before the four criterion nodes. The criterion
    nodes are intentionally explicit so later versions can add review or retry
    edges for an individual dimension without changing the scoring core.
    """

    graph = StateGraph(ScoringWorkflowState)
    graph.add_node(
        "validate_and_retrieve",
        lambda state: _validate_input(state, pipeline=pipeline),
    )
    criteria = expected_criteria("task2")
    # The graph uses the same four slots for both task types. The first node
    # selects Task Achievement or Task Response at runtime before dispatch.
    graph.add_node(
        "score_task_criterion",
        lambda state: _score_criterion_node(
            state,
            pipeline=pipeline,
            criterion=(
                "task_achievement"
                if state["preparation"].request.task_type == "task1"
                else "task_response"
            ),
        ),
    )
    for criterion in criteria[1:]:
        graph.add_node(
            f"score_{criterion}",
            lambda state, criterion=criterion: _score_criterion_node(
                state, pipeline=pipeline, criterion=criterion
            ),
        )
    graph.add_node("aggregate", lambda state: _aggregate(state, pipeline=pipeline))

    graph.add_edge(START, "validate_and_retrieve")
    graph.add_edge("validate_and_retrieve", "score_task_criterion")
    graph.add_edge("score_task_criterion", "score_coherence_and_cohesion")
    graph.add_edge("score_coherence_and_cohesion", "score_lexical_resource")
    graph.add_edge("score_lexical_resource", "score_grammatical_range_and_accuracy")
    graph.add_edge("score_grammatical_range_and_accuracy", "aggregate")
    graph.add_edge("aggregate", END)
    return graph.compile()


class ScoringWorkflow:
    """Run the compiled LangGraph and return only a complete report."""

    def __init__(self, pipeline: ScoringPipeline) -> None:
        self.pipeline = pipeline
        self.graph = build_scoring_graph(pipeline)

    def score(self, request: ScoreRequest | dict[str, Any]) -> ScoreReport:
        """Invoke the graph for one Academic essay."""

        result = self.run(request)
        report = result.get("report")
        if not isinstance(report, ScoreReport):
            raise RuntimeError("LangGraph 未生成完整评分报告")
        return report

    def run(self, request: ScoreRequest | dict[str, Any]) -> ScoringWorkflowState:
        """Invoke the graph and retain preparation context for a higher-level service."""

        result = self.graph.invoke({"request": request})
        report = result.get("report")
        if not isinstance(report, ScoreReport):
            raise RuntimeError("LangGraph 未生成完整评分报告")
        return result
