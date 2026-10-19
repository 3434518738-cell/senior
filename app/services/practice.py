"""Unified Academic practice service for intake, vision, retrieval, and scoring."""

from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from app.scoring.pipeline import ScoringPipeline, ScoringPipelineError
from app.scoring.schemas import (
    ChartUnderstanding,
    RetrievedSampleReference,
    ScoreRequest,
    UnifiedPracticeRequest,
    UnifiedPracticeResponse,
    VisualInspectionRequest,
)
from app.scoring.workflow import ScoringWorkflow


class PracticeServiceError(RuntimeError):
    """Raised when a practice submission cannot enter the unified workflow."""


class PracticeService:
    """Coordinate the same Academic workflow for daily, bank, and upload modes."""

    def __init__(
        self,
        pipeline: ScoringPipeline,
        workflow: ScoringWorkflow | None = None,
    ) -> None:
        self.pipeline = pipeline
        self.workflow = workflow or ScoringWorkflow(pipeline)

    def inspect_task1_image(
        self, request: VisualInspectionRequest | dict[str, Any]
    ) -> ChartUnderstanding:
        """Read an image only; callers must confirm the result before scoring."""

        try:
            validated = (
                request
                if isinstance(request, VisualInspectionRequest)
                else VisualInspectionRequest.model_validate(request)
            )
            return self.pipeline._understand_chart_image(validated.chart_image_base64)
        except (ValidationError, ScoringPipelineError, ValueError) as exc:
            raise PracticeServiceError(f"Task 1 图片识别失败: {exc}") from exc

    def score(
        self, request: UnifiedPracticeRequest | dict[str, Any]
    ) -> UnifiedPracticeResponse:
        """Score one submission after enforcing visual confirmation rules."""

        try:
            validated = (
                request
                if isinstance(request, UnifiedPracticeRequest)
                else UnifiedPracticeRequest.model_validate(request)
            )
        except ValidationError as exc:
            raise PracticeServiceError(f"统一练习输入无效: {exc}") from exc

        visual = validated.visual_understanding
        score_request = self._to_score_request(validated, visual)
        try:
            state = self.workflow.run(score_request)
        except (ScoringPipelineError, RuntimeError, ValueError) as exc:
            raise PracticeServiceError(f"统一评分流程失败: {exc}") from exc
        report = state.get("report")
        preparation = state.get("preparation")
        if report is None or preparation is None:
            raise PracticeServiceError("统一评分流程未生成完整结果")
        if visual is not None:
            warnings = list(report.warnings)
            if visual.uncertain_or_unreadable or any(
                point.precision == "estimated"
                for series in visual.series
                for point in series.points
            ):
                warning = (
                    "题目视觉事实由用户确认，但仍包含估读或不确定内容；"
                    "这些内容不应单独作为确定性扣分依据。"
                )
                if warning not in warnings:
                    warnings.append(warning)
            report = report.model_copy(
                update={"chart_understanding": visual, "warnings": warnings}
            )
        return UnifiedPracticeResponse(
            mode=validated.mode,
            task_type=validated.task_type,
            report=report,
            retrieved_samples=[
                self._sample_reference(sample, validated.task_type)
                for sample in preparation.samples
            ],
        )

    @staticmethod
    def _to_score_request(
        request: UnifiedPracticeRequest,
        visual: ChartUnderstanding | None,
    ) -> ScoreRequest:
        """Convert the unified contract into the existing strict score contract."""

        chart_context = request.chart_context
        if visual is not None:
            structured = (
                "Confirmed visual facts (user reviewed):\n"
                + visual.model_dump_json(indent=2)
            )
            chart_context = (
                f"{chart_context}\n{structured}" if chart_context else structured
            )
        return ScoreRequest(
            task_type=request.task_type,
            question=request.question,
            essay=request.essay,
            chart_type=request.chart_type,
            chart_context=chart_context,
            # An already confirmed image must never be sent through vision a
            # second time; the reviewed structured facts are the source of truth.
            chart_image_base64=None,
        )

    @staticmethod
    def _sample_reference(
        sample: dict[str, Any], task_type: str
    ) -> RetrievedSampleReference:
        """Expose only concise metadata and an excerpt from a retrieved sample."""

        metadata = sample.get("metadata")
        metadata = metadata if isinstance(metadata, dict) else {}
        text = sample.get("text", "")
        excerpt = " ".join(str(text).split())[:500] if text else ""
        distance = sample.get("distance")
        return RetrievedSampleReference(
            sample_id=str(sample.get("id", "unknown")),
            task_type=metadata.get("task_type", task_type),
            question_type=metadata.get("question_type"),
            chart_type=metadata.get("chart_type"),
            excerpt=excerpt,
            distance=float(distance) if isinstance(distance, (int, float)) else None,
        )
