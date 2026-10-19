"""Offline tests for the serial, all-or-nothing scoring pipeline."""

from __future__ import annotations

import json
import re
import base64
from typing import Any

from app.scoring.pipeline import ScoringPipeline, round_to_half_band
from app.scoring.schemas import (
    ChartSeries,
    ChartStructure,
    ChartUnderstanding,
    ScoreRequest,
)


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
        self,
        prompt: str,
        *,
        response_format: str | dict[str, Any] | None = None,
        images: list[str] | None = None,
    ) -> str:
        self.calls.append(
            {"prompt": prompt, "response_format": response_format, "images": images}
        )
        if images and "structure-only pass" in prompt:
            return json.dumps(
                {
                    "chart_type": "line_graph",
                    "title": "Transport modes",
                    "x_axis": "Year",
                    "y_axis": "Percentage",
                    "categories": ["2000"],
                    "series_names": ["Car"],
                }
            )
        if images:
            return json.dumps(
                {
                    "chart_summary": "Line graph of transport modes.",
                    "axes_or_categories": ["Year", "Percentage"],
                    "series": [
                        {
                            "name": "Car",
                            "points": [
                                {
                                    "label": "2000",
                                    "value": 60,
                                    "precision": "estimated",
                                }
                            ],
                            "trend": "decreasing",
                        }
                    ],
                    "uncertain_or_unreadable": ["Car/2000: approximately 60%"],
                }
            )
        if self.invalid_first and len(self.calls) == 1:
            return "not json"
        marker = re.search(r"criterion(?: is|:| )\s*([a-z_]+)", prompt)
        assert marker is not None
        criterion = marker.group(1)
        quote = "not from essay" if self.bad_quote else "This essay uses clear ideas."
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
                        "quote": "This essay uses clear ideas.",
                        "explanation": f"Evidence for {key}.",
                    }
                    for key in keys
                ]
            }
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
                "task_review": task_review,
            }
        )


def _pipeline(
    model: FakeModel, searcher: FakeSearcher | None = None
) -> ScoringPipeline:
    return ScoringPipeline(model, FakeRubricStore(), searcher)


def test_rounding_uses_half_up_not_bankers_rounding() -> None:
    assert round_to_half_band(6.25) == 6.5
    assert round_to_half_band(6.75) == 7.0


def test_non_task_criterion_discards_irrelevant_model_task_review() -> None:
    model = FakeModel()
    payload = json.loads(model.generate("criterion: coherence_and_cohesion"))
    payload["criterion"] = "coherence_and_cohesion"
    payload["task_review"] = {"checks": [{"key": "irrelevant"}]}
    result = ScoringPipeline._parse_result(
        json.dumps(payload), "coherence_and_cohesion", "This essay uses clear ideas."
    )
    assert result.task_review is None


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
    assert report.essay_band_estimate is None
    assert report.estimate_status == "unreliable_under_minimum_words"
    assert report.warnings
    task_review = next(
        item.task_review
        for item in report.criterion_results
        if item.criterion == "task_response"
    )
    assert task_review is not None
    assert {check.key for check in task_review.checks} == {
        "prompt_coverage",
        "position",
        "idea_development",
        "support",
        "relevance",
    }
    assert "Do not treat an essay roadmap" in model.calls[0]["prompt"]
    assert "Do not run a separate pre-submission check" in model.calls[0]["prompt"]
    assert (
        "tell the user that the submitted essay appears unfinished"
        in model.calls[0]["prompt"]
    )
    assert "Do not assign an otherwise fully developed Task Response assessment" in (
        model.calls[0]["prompt"]
    )
    assert "Sample 1:" not in model.calls[0]["prompt"]
    assert searcher.calls[0]["task_type"] == "task2"
    assert all("Sample 1:" not in call["prompt"] for call in model.calls)
    assert len(model.calls) == 4


def test_short_task2_reports_diagnostics_without_reliable_band_estimate() -> None:
    report = _pipeline(FakeModel()).score(
        ScoreRequest(
            task_type="task2",
            question="Discuss both views.",
            essay="This essay uses clear ideas.",
        )
    )
    assert report.word_count < 250
    assert report.essay_band_estimate is None
    assert report.estimate_status == "unreliable_under_minimum_words"
    assert any("不能生成可靠 Band 估分" in warning for warning in report.warnings)


def test_task1_search_is_filtered_by_chart_type() -> None:
    searcher = FakeSearcher()
    model = FakeModel()
    report = _pipeline(model, searcher).score(
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
    review = report.criterion_results[0].task_review
    assert review is not None
    assert {check.key for check in review.checks} == {
        "overview",
        "key_feature_selection",
        "data_accuracy",
        "comparisons",
        "visual_scope",
    }
    assert "Do not invent missing chart facts" in model.calls[0]["prompt"]
    assert 'precision "estimated"' in model.calls[0]["prompt"]
    assert "Academic Task 1 does not require a conclusion paragraph" in (
        model.calls[0]["prompt"]
    )
    assert "<CHART_CONTEXT>" in model.calls[0]["prompt"]
    assert "Never attribute" in (model.calls[0]["prompt"])


def test_task1_prompt_structures_explicit_chart_points() -> None:
    from app.scoring.prompts import build_criterion_prompt

    request = ScoreRequest(
        task_type="task1",
        question="Summarise the graph.",
        essay="Car use fell.",
        chart_type="line_graph",
        chart_context=(
            "Car: 60% in 2000, 30% in 2020. " "Bus: 30% in 2000, 25% in 2020."
        ),
    )
    prompt = build_criterion_prompt(
        request, request.essay, "task_achievement", {}, [], word_count=3
    )
    assert '"series": "Car", "year": 2000, "percent": 60.0' in prompt
    assert '"series": "Bus", "year": 2020, "percent": 25.0' in prompt


def test_task1_task_achievement_prompt_handles_process_steps_and_branches() -> None:
    from app.scoring.prompts import build_criterion_prompt

    request = ScoreRequest(
        task_type="task1",
        question="Summarise the process.",
        essay="Paper is first collected.",
        chart_type="process_diagram",
        chart_context=(
            '{"visual_type": "process", "process_stages": [], '
            '"uncertain_or_unreadable": []}'
        ),
    )
    prompt = build_criterion_prompt(
        request, request.essay, "task_achievement", {}, [], word_count=4
    )

    assert "preserves their order and any" in prompt
    assert "branches/cycles" in prompt
    assert "Do not expect numerical\ndata" in prompt


def test_task1_task_achievement_prompt_handles_map_changes_and_locations() -> None:
    from app.scoring.prompts import build_criterion_prompt

    request = ScoreRequest(
        task_type="task1",
        question="Compare the maps.",
        essay="The woodland was replaced by housing.",
        chart_type="map_comparison",
        chart_context=(
            '{"visual_type": "map", "map_features": [], '
            '"uncertain_or_unreadable": []}'
        ),
    )
    prompt = build_criterion_prompt(
        request, request.essay, "task_achievement", {}, [], word_count=7
    )

    assert "main spatial changes" in prompt
    assert "locates salient\nfeatures correctly" in prompt
    assert "before/after fields" in prompt


def test_task1_image_is_read_once_and_reported_as_structured_facts() -> None:
    model = FakeModel()
    image = base64.b64encode(b"\x89PNG\r\n\x1a\nmock-image-data").decode()
    report = _pipeline(model).score(
        ScoreRequest(
            task_type="task1",
            question="Summarise the graph.",
            essay="This essay uses clear ideas.",
            chart_type="line_graph",
            chart_image_base64=image,
        )
    )
    assert report.chart_understanding is not None
    assert report.chart_understanding.series[0].name == "Car"
    assert any("估读值" in warning for warning in report.warnings)
    assert model.calls[0]["images"] == [image]
    assert model.calls[1]["images"] == [image]
    assert all(call["images"] is None for call in model.calls[2:])
    assert '"name": "Car"' in model.calls[2]["prompt"]


def test_task1_process_diagram_extracts_ordered_stages_and_branches() -> None:
    class ProcessModel(FakeModel):
        def generate(
            self,
            prompt: str,
            *,
            response_format: str | dict[str, Any] | None = None,
            images: list[str] | None = None,
        ) -> str:
            self.calls.append(
                {"prompt": prompt, "response_format": response_format, "images": images}
            )
            if images and "structure-only pass" in prompt:
                return json.dumps(
                    {
                        "visual_type": "process",
                        "chart_type": "process_diagram",
                        "process_stages": [
                            {
                                "order": 0,
                                "label": "Collect paper",
                                "next_steps": ["Sort paper"],
                            },
                            {
                                "order": 1,
                                "label": "Sort paper",
                                "next_steps": ["Remove staples", "Wash paper"],
                            },
                        ],
                    }
                )
            return super().generate(
                prompt, response_format=response_format, images=images
            )

    model = ProcessModel()
    image = base64.b64encode(b"\x89PNG\r\n\x1a\nmock-image-data").decode()
    report = _pipeline(model).score(
        ScoreRequest(
            task_type="task1",
            question="Summarise the process.",
            essay="This essay uses clear ideas.",
            chart_type="process_diagram",
            chart_image_base64=image,
        )
    )

    assert report.chart_understanding is not None
    assert report.chart_understanding.visual_type == "process"
    assert [stage.label for stage in report.chart_understanding.process_stages] == [
        "Collect paper",
        "Sort paper",
    ]
    assert report.chart_understanding.process_stages[1].next_steps == [
        "Remove staples",
        "Wash paper",
    ]
    assert report.chart_understanding.series == []
    assert not any("题目图片中有无法可靠辨认的信息" in item for item in report.warnings)


def test_task1_map_extracts_before_after_changes_and_supported_direction() -> None:
    class MapModel(FakeModel):
        def generate(
            self,
            prompt: str,
            *,
            response_format: str | dict[str, Any] | None = None,
            images: list[str] | None = None,
        ) -> str:
            self.calls.append(
                {"prompt": prompt, "response_format": response_format, "images": images}
            )
            if images and "structure-only pass" in prompt:
                return json.dumps(
                    {
                        "visual_type": "map",
                        "chart_type": "map_comparison",
                        "map_features": [
                            {
                                "location": "north-west corner",
                                "direction": "north-west",
                                "before": "woodland",
                                "after": "car park",
                                "change_type": "replacement",
                            }
                        ],
                    }
                )
            return super().generate(
                prompt, response_format=response_format, images=images
            )

    model = MapModel()
    image = base64.b64encode(b"\x89PNG\r\n\x1a\nmock-image-data").decode()
    report = _pipeline(model).score(
        ScoreRequest(
            task_type="task1",
            question="Compare the maps.",
            essay="This essay uses clear ideas.",
            chart_type="map_comparison",
            chart_image_base64=image,
        )
    )

    assert report.chart_understanding is not None
    assert report.chart_understanding.visual_type == "map"
    feature = report.chart_understanding.map_features[0]
    assert feature.location == "north-west corner"
    assert feature.direction == "north-west"
    assert feature.before == "woodland"
    assert feature.after == "car park"
    assert feature.change_type == "replacement"


def test_chart_structure_reconciliation_adds_missing_series_and_drops_unknown_points() -> (
    None
):
    understanding = ChartUnderstanding(
        chart_summary="A graph.",
        axes_or_categories=["Year"],
        series=[
            ChartSeries(
                name="Car",
                points=[
                    {"label": "2000", "value": 60, "precision": "estimated"},
                    {"label": "1990", "value": 70, "precision": "estimated"},
                ],
            )
        ],
        uncertain_or_unreadable=[],
    )
    structure = ChartStructure(
        chart_type="line",
        title="",
        x_axis="Year",
        y_axis="Percentage",
        categories=["2000"],
        series_names=["Car", "Bus"],
    )

    result = ScoringPipeline._reconcile_chart_structure(understanding, structure)

    assert [series.name for series in result.series] == ["Car", "Bus"]
    assert [point.label for point in result.series[0].points] == ["2000"]
    assert result.series[1].points == []
    assert len(result.uncertain_or_unreadable) == 2


def test_chart_summary_uses_reconciled_estimates_without_unverified_numbers() -> None:
    understanding = ChartUnderstanding(
        chart_summary="The model claims a value of 99.",
        axes_or_categories=["2000", "2010"],
        series=[
            ChartSeries(
                name="Car",
                points=[
                    {"label": "2000", "value": 20, "precision": "estimated"},
                    {"label": "2010", "value": 70, "precision": "estimated"},
                ],
            )
        ],
        uncertain_or_unreadable=[],
    )
    structure = ChartStructure(
        chart_type="line",
        categories=["2000", "2010"],
        series_names=["Car"],
    )

    result = ScoringPipeline._summarize_chart(understanding, structure)

    assert "rising overall" in result.chart_summary
    assert "99" not in result.chart_summary


def test_chart_summary_does_not_infer_trend_from_nominal_categories() -> None:
    understanding = ChartUnderstanding(
        chart_summary="A pie chart compares household energy use.",
        axes_or_categories=["Heating", "Lighting", "Cooling"],
        series=[
            ChartSeries(
                name="Share (%)",
                points=[
                    {"label": "Heating", "value": 36, "precision": "explicit"},
                    {"label": "Lighting", "value": 9, "precision": "explicit"},
                    {"label": "Cooling", "value": 15, "precision": "explicit"},
                ],
            )
        ],
        uncertain_or_unreadable=[],
    )
    structure = ChartStructure(
        chart_type="pie_chart",
        categories=["Heating", "Lighting", "Cooling"],
        series_names=["Share (%)"],
        has_explicit_data_labels=True,
    )

    result = ScoringPipeline._summarize_chart(understanding, structure)

    assert result.series[0].trend == ""
    assert "rising overall" not in result.chart_summary
    assert "falling overall" not in result.chart_summary


def test_invalid_json_is_repaired_once() -> None:
    model = FakeModel(invalid_first=True)
    report = _pipeline(model).score(
        ScoreRequest(
            task_type="task2",
            question="Discuss both views.",
            essay="This essay uses clear ideas.",
        )
    )
    assert report.essay_band_estimate is None
    assert len(model.calls) == 5


def test_bad_evidence_quote_is_removed_and_report_completes() -> None:
    report = _pipeline(FakeModel(bad_quote=True)).score(
        ScoreRequest(
            task_type="task2",
            question="Discuss both views.",
            essay="This essay uses clear ideas.",
        )
    )
    assert report.criterion_results[0].evidence[0].quote is None


def test_unsupported_task_review_quote_is_removed_without_losing_report() -> None:
    model = FakeModel()
    pipeline = _pipeline(model)
    preparation = pipeline.prepare(
        ScoreRequest(
            task_type="task2",
            question="Discuss both views.",
            essay="This essay uses clear ideas.",
        )
    )
    result = json.loads(model.generate("criterion: task_response"))
    result["task_review"]["checks"][0]["quote"] = "invented evidence"
    parsed = pipeline._parse_result(
        json.dumps(result), "task_response", preparation.cleaned_essay
    )
    assert parsed.task_review is not None
    assert parsed.task_review.checks[0].quote is None


def test_invented_evidence_quote_is_removed_without_losing_report() -> None:
    model = FakeModel()
    result = json.loads(model.generate("criterion: task_response"))
    result["evidence"][0][
        "quote"
    ] = "could also be collected gradually after the student finds well-paid employment"
    parsed = ScoringPipeline._parse_result(
        json.dumps(result), "task_response", "This essay uses clear ideas."
    )
    assert parsed.evidence[0].quote is None
    assert parsed.evidence[0].explanation


def test_trailing_ellipsis_is_normalized_to_exact_essay_excerpt() -> None:
    model = FakeModel()
    result = json.loads(model.generate("criterion: task_response"))
    result["evidence"][0]["quote"] = "This essay uses clear ideas..."
    parsed = ScoringPipeline._parse_result(
        json.dumps(result), "task_response", "This essay uses clear ideas."
    )
    assert parsed.evidence[0].quote == "This essay uses clear ideas"


def test_ellipsis_omissions_expand_to_exact_contiguous_essay_excerpt() -> None:
    model = FakeModel()
    result = json.loads(model.generate("criterion: task_response"))
    result["evidence"][0]["quote"] = "This essay...clear ideas."
    parsed = ScoringPipeline._parse_result(
        json.dumps(result), "task_response", "This essay uses clear ideas."
    )
    assert parsed.evidence[0].quote == "This essay uses clear ideas."
