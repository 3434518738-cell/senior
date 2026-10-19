"""Unified Academic practice service for intake, vision, retrieval, and scoring."""

from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from app.scoring.pipeline import ScoringPipeline, ScoringPipelineError
from app.rag.corpus_loader import TaskType
from app.scoring.schemas import (
    ChartUnderstanding,
    RetrievedSampleReference,
    ScoreRequest,
    UnifiedPracticeRequest,
    UnifiedPracticeResponse,
    VisualInspectionRequest,
)
from app.scoring.workflow import ScoringWorkflow
from app.practice.repository import QuestionBankError, QuestionBankRepository
from app.practice.schemas import (
    PracticeSessionCreateRequest,
    PracticeSessionResponse,
    PracticeSessionSubmissionResponse,
    PracticeSessionSubmitRequest,
    QuestionListResponse,
    QuestionSummary,
)


class PracticeServiceError(RuntimeError):
    """Raised when a practice submission cannot enter the unified workflow."""


class PracticeService:
    """Coordinate the same Academic workflow for daily, bank, and upload modes."""

    def __init__(
        self,
        pipeline: ScoringPipeline,
        workflow: ScoringWorkflow | None = None,
        repository: QuestionBankRepository | None = None,
    ) -> None:
        self.pipeline = pipeline
        self.workflow = workflow or ScoringWorkflow(pipeline)
        self.repository = repository
        if repository is not None:
            repository.seed_from_corpus()

    def list_questions(
        self,
        *,
        task_type: TaskType | None = None,
        question_type: str | None = None,
        chart_type: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> QuestionListResponse:
        """List reviewed Academic questions for the question-bank screen."""

        repository = self._require_repository()
        rows = repository.list_questions(
            task_type=task_type,
            question_type=question_type,
            chart_type=chart_type,
            limit=limit,
            offset=offset,
        )
        return QuestionListResponse(
            items=[self._question_summary(row) for row in rows],
            limit=limit,
            offset=offset,
        )

    def get_question(self, question_id: str) -> QuestionSummary:
        """Return one reviewed question for a practice detail page."""

        try:
            row = self._require_repository().get_question(question_id)
            return self._question_summary(row)
        except (QuestionBankError, ValidationError) as exc:
            raise PracticeServiceError(str(exc)) from exc

    def start_session(
        self, request: PracticeSessionCreateRequest | dict[str, Any]
    ) -> PracticeSessionResponse:
        """Create a daily pair or selected question-bank practice session."""

        try:
            validated = (
                request
                if isinstance(request, PracticeSessionCreateRequest)
                else PracticeSessionCreateRequest.model_validate(request)
            )
            row = self._require_repository().create_session(
                validated.mode,
                task_type=validated.task_type,
                question_id=validated.question_id,
                duration_seconds=validated.duration_seconds,
                daily_date=validated.daily_date,
            )
            return PracticeSessionResponse.model_validate(row)
        except (ValidationError, QuestionBankError, ValueError) as exc:
            raise PracticeServiceError(f"创建练习会话失败: {exc}") from exc

    def get_session(self, session_id: str) -> PracticeSessionResponse:
        """Return a session with its questions and any saved reports."""

        try:
            row = self._require_repository().get_session(session_id)
            return PracticeSessionResponse.model_validate(row)
        except (QuestionBankError, ValidationError) as exc:
            raise PracticeServiceError(str(exc)) from exc

    def submit_session_item(
        self,
        session_id: str,
        request: PracticeSessionSubmitRequest | dict[str, Any],
    ) -> PracticeSessionSubmissionResponse:
        """Score and persist one item from a question-bank/daily session."""

        try:
            validated = (
                request
                if isinstance(request, PracticeSessionSubmitRequest)
                else PracticeSessionSubmitRequest.model_validate(request)
            )
            repository = self._require_repository()
            session = repository.get_session(session_id)
            item = next(
                (
                    item
                    for item in session["items"]
                    if item["item_order"] == validated.item_order
                ),
                None,
            )
            if item is None:
                raise QuestionBankError("练习项目序号不存在")
            if item.get("essay") is not None:
                raise QuestionBankError("该练习项目已经提交")
            result = self.score(
                UnifiedPracticeRequest(
                    mode=session["mode"],
                    task_type=item["task_type"],
                    question=item["question"],
                    essay=validated.essay,
                    chart_type=item.get("chart_type"),
                    chart_context=validated.chart_context,
                    chart_image_base64=validated.chart_image_base64,
                    visual_understanding=validated.visual_understanding,
                    visual_confirmed=validated.visual_confirmed,
                )
            )
            saved = repository.save_submission(
                session_id,
                validated.item_order,
                validated.essay,
                result.model_dump(mode="json"),
            )
            return PracticeSessionSubmissionResponse(
                session=PracticeSessionResponse.model_validate(saved),
                result=result,
            )
        except (ValidationError, QuestionBankError, PracticeServiceError) as exc:
            if isinstance(exc, PracticeServiceError):
                raise
            raise PracticeServiceError(f"提交练习失败: {exc}") from exc

    def inspect_task1_image(
        self, request: VisualInspectionRequest | dict[str, Any]
    ) -> ChartUnderstanding:
        """Read an image and return structured facts for preview or scoring."""

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
        """Score one submission, automatically reading an uploaded Task 1 image."""

        try:
            validated = (
                request
                if isinstance(request, UnifiedPracticeRequest)
                else UnifiedPracticeRequest.model_validate(request)
            )
        except ValidationError as exc:
            raise PracticeServiceError(f"统一练习输入无效: {exc}") from exc

        visual = validated.visual_understanding
        auto_inspected = False
        if (
            validated.task_type == "task1"
            and validated.chart_image_base64
            and visual is None
        ):
            # The photo is the user's source input.  Do not require a second
            # manual inspection request or a hand-written chart_context.
            visual = self.inspect_task1_image(
                VisualInspectionRequest(
                    chart_image_base64=validated.chart_image_base64,
                )
            )
            auto_inspected = True
        try:
            score_request = self._to_score_request(validated, visual)
        except (ValidationError, ValueError) as exc:
            raise PracticeServiceError(f"统一练习输入无效: {exc}") from exc
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
            if auto_inspected:
                warning = "题目事实由 Qwen 自动识别，建议核对 chart_understanding 后再参考评分。"
                if warning not in warnings:
                    warnings.append(warning)
            if visual.uncertain_or_unreadable or any(
                point.precision == "estimated"
                for series in visual.series
                for point in series.points
            ):
                warning = (
                    "题目视觉事实仍包含估读或不确定内容；"
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
        chart_type = request.chart_type
        if visual is not None:
            structured = (
                "Structured visual facts (read from the Task 1 image or user reviewed):\n"
                + visual.model_dump_json(indent=2)
            )
            chart_context = (
                f"{chart_context}\n{structured}" if chart_context else structured
            )
            chart_type = chart_type or visual.chart_type or visual.visual_type
        if request.task_type == "task1" and not chart_type:
            raise ValueError("无法确定 Academic Task 1 的图表类型")
        return ScoreRequest(
            task_type=request.task_type,
            question=request.question,
            essay=request.essay,
            chart_type=chart_type,
            chart_context=chart_context,
            # An already confirmed image must never be sent through vision a
            # second time; the reviewed structured facts are the source of truth.
            chart_image_base64=None,
        )

    def _require_repository(self) -> QuestionBankRepository:
        if self.repository is None:
            raise PracticeServiceError("题库服务尚未配置")
        return self.repository

    @staticmethod
    def _question_summary(row: dict[str, Any]) -> QuestionSummary:
        """Map storage-only fields out of the public question contract."""

        public_fields = {
            "question_id",
            "exam_type",
            "task_type",
            "title",
            "question",
            "question_type",
            "chart_type",
            "chart_subtype",
            "topic",
            "source_pages",
        }
        return QuestionSummary.model_validate(
            {key: value for key, value in row.items() if key in public_fields}
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
