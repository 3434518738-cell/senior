"""Offline tests for the serial, all-or-nothing scoring pipeline."""

from __future__ import annotations

import json
import re
from typing import Any

import pytest

from app.scoring.pipeline import (
    ScoringPipeline,
    ScoringPipelineError,
    round_to_half_band,
)
from app.scoring.schemas import ScoreRequest


class FakeRubricStore:
    def descriptors(self, task_type: str, criterion: str) -> list[dict[str, Any]]:
        return [
            {
                "id": f"{task_type}_{criterion}_{band}",
                "text": f"Band {band} descriptor",
                "metadata": {
                    "band": band,
                    "task_type": task_type,
                    "criterion": criterion,
                    "source_page": 3,
                },
            }
            for band in range(10)
        ]

    def guidance(self, task_type: str, criterion: str) -> list[dict[str, Any]]:
        return [
            {
                "id": f"guidance_{task_type}_{criterion}",
                "text": "Use relevant evidence.",
                "metadata": {
                    "task_type": task_type,
                    "criterion": criterion,
                    "scope": task_type,
                },
            }
        ]


class FakeSearcher:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def search(
        self,
        query: str,
        task_type: str,
        *,
        chart_type: str | None = None,
        top_k: int | None = None,
    ) -> list[dict[str, Any]]:
        self.calls.append(
            {
                "query": query,
                "task_type": task_type,
                "chart_type": chart_type,
                "top_k": top_k,
            }
        )
        return [{"id": "sample_1", "text": "A sample essay."}]


class FakeModel:
    def __init__(self, *, invalid_first: bool = False, bad_quote: bool = False) -> None:
        self.invalid_first = invalid_first
        self.bad_quote = bad_quote
        self.calls: list[dict[str, Any]] = []

    def generate(
        self, prompt: str, *, response_format: str | dict[str, Any] | None = None
    ) -> str:
        self.calls.append({"prompt": prompt, "response_format": response_format})
        if self.invalid_first and len(self.calls) == 1:
            return "not json"
        marker = re.search(r"criterion(?: is|:| )\s*([a-z_]+)", prompt)
        assert marker is not None
        criterion = marker.group(1)
        quote = "not from essay" if self.bad_quote else "This essay uses clear ideas."
        return json.dumps(
            {
                "criterion": criterion,
                "band": 7.0,
                "rationale": "The response is clear.",
                "evidence": [
                    {"quote": quote, "explanation": "This supports the judgement."}
                ],
                "strengths": ["clear ideas"],
                "issues": [],
                "improvements": ["extend support"],
            }
        )


def _pipeline(
    model: FakeModel, searcher: FakeSearcher | None = None
) -> ScoringPipeline:
    return ScoringPipeline(model, FakeRubricStore(), searcher)


def test_rounding_uses_half_up_not_bankers_rounding() -> None:
    assert round_to_half_band(6.25) == 6.5
    assert round_to_half_band(6.75) == 7.0


def test_task2_scores_all_four_criteria_and_warns_on_short_essay() -> None:
    model = FakeModel()
    searcher = FakeSearcher()
    report = _pipeline(model, searcher).score(
        ScoreRequest(
            task_type="task2",
            question="Discuss both views.",
            essay="This essay uses clear ideas.",
        )
    )
    assert {item.criterion for item in report.criterion_results} == {
        "task_response",
        "coherence_and_cohesion",
        "lexical_resource",
        "grammatical_range_and_accuracy",
    }
    assert report.essay_band_estimate == 7.0
    assert report.warnings
    assert searcher.calls[0]["task_type"] == "task2"
    assert len(model.calls) == 4


def test_task1_search_is_filtered_by_chart_type() -> None:
    searcher = FakeSearcher()
    _pipeline(FakeModel(), searcher).score(
        ScoreRequest(
            task_type="task1",
            question="The chart shows changes.",
            essay="This essay uses clear ideas.",
            chart_type="line_graph",
            chart_context="A line graph compares three years.",
        )
    )
    assert searcher.calls[0]["task_type"] == "task1"
    assert searcher.calls[0]["chart_type"] == "line_graph"


def test_invalid_json_is_repaired_once() -> None:
    model = FakeModel(invalid_first=True)
    report = _pipeline(model).score(
        ScoreRequest(
            task_type="task2",
            question="Discuss both views.",
            essay="This essay uses clear ideas.",
        )
    )
    assert report.essay_band_estimate == 7.0
    assert len(model.calls) == 5


def test_bad_evidence_fails_without_partial_report() -> None:
    with pytest.raises(ScoringPipelineError, match="未生成部分报告"):
        _pipeline(FakeModel(bad_quote=True)).score(
            ScoreRequest(
                task_type="task2",
                question="Discuss both views.",
                essay="This essay uses clear ideas.",
            )
        )
