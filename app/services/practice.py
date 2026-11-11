"""Unified Academic practice service for intake, vision, retrieval, and scoring."""

from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from app.scoring.pipeline import ScoringPipeline, ScoringPipelineError
from app.scoring.language import require_chinese_feedback
from app.rag.corpus_loader import TaskType
from app.scoring.schemas import (
    ChartUnderstanding,
    ImprovementPlan,
    QuestionImageUnderstanding,
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
                question_ids=validated.question_ids,
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
            chart_image_base64 = validated.chart_image_base64
            image_url = item.get("chart_image_url")
            if item["task_type"] == "task1" and image_url and not chart_image_base64:
                filename = Path(str(image_url)).name
                image_path = (
                    Path(__file__).resolve().parents[2]
                    / "frontend"
                    / "assets"
                    / "question-images"
                    / filename
                )
                if not image_path.is_file():
                    raise QuestionBankError("题库原始图表文件缺失，无法进行该题评分")
                chart_image_base64 = base64.b64encode(image_path.read_bytes()).decode(
                    "ascii"
                )
            result = self.score(
                UnifiedPracticeRequest(
                    mode=session["mode"],
                    task_type=item["task_type"],
                    question=item["question"],
                    essay=validated.essay,
                    chart_type=item.get("chart_type"),
                    chart_context=validated.chart_context,
                    chart_image_base64=chart_image_base64,
                    visual_understanding=validated.visual_understanding,
                    visual_confirmed=validated.visual_confirmed,
                )
            )
            saved = repository.save_submission(
                session_id,
                validated.item_order,
                validated.essay,
                {
                    **result.report.model_dump(mode="json"),
                    "improvement_plan": (
                        result.improvement_plan.model_dump(mode="json")
                        if result.improvement_plan
                        else None
                    ),
                },
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
        recognized_question: QuestionImageUnderstanding | None = None
        question_image = validated.question_image_base64
        if validated.mode == "upload":
            question_source = question_image or validated.chart_image_base64
            if question_source:
                try:
                    recognized_question = self.pipeline._understand_question_image(
                        question_source, validated.task_type
                    )
                except (ScoringPipelineError, ValueError) as exc:
                    raise PracticeServiceError(f"题目图片识别失败: {exc}") from exc
                validated = validated.model_copy(
                    update={"question": recognized_question.question_text}
                )
        auto_inspected = False
        visual_image = validated.chart_image_base64 or question_image
        if (
            validated.task_type == "task1"
            and visual_image is not None
            and visual is None
        ):
            # The photo is the user's source input.  Do not require a second
            # manual inspection request or a hand-written chart_context.
            visual = self.inspect_task1_image(
                VisualInspectionRequest(
                    chart_image_base64=visual_image,
                )
            )
            auto_inspected = True
        try:
            score_request = self._to_score_request(validated, visual)
        except (ValidationError, ValueError) as exc:
            raise PracticeServiceError(f"统一练习输入无效: {exc}") from exc
        try:
            state = self.workflow.run(
                score_request, retrieve_samples=validated.mode == "daily"
            )
        except (ScoringPipelineError, RuntimeError, ValueError) as exc:
            raise PracticeServiceError(f"统一评分流程失败: {exc}") from exc
        report = state.get("report")
        preparation = state.get("preparation")
        if report is None or preparation is None:
            raise PracticeServiceError("统一评分流程未生成完整结果")
        improvement_plan = (
            self._build_improvement_plan(
                report,
                score_request.question,
                preparation.cleaned_essay,
                preparation.samples,
            )
            if validated.mode == "daily"
            else None
        )
        if preparation.samples and improvement_plan is None:
            report = report.model_copy(
                update={
                    "warnings": [
                        *report.warnings,
                        "范文个性化改进建议本次未生成，原评分结果不受影响。",
                    ]
                }
            )
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
        if (
            recognized_question is not None
            and recognized_question.uncertain_or_unreadable
        ):
            warnings = list(report.warnings)
            warnings.append(
                "题目图片中存在无法可靠辨认的文字，请核对 recognized_question。"
            )
            report = report.model_copy(
                update={"warnings": list(dict.fromkeys(warnings))}
            )
        elif recognized_question is not None:
            warnings = list(report.warnings)
            warnings.append(
                "题目由 Qwen 从图片自动识别，建议核对 recognized_question 后再参考评分。"
            )
            report = report.model_copy(
                update={"warnings": list(dict.fromkeys(warnings))}
            )
        return UnifiedPracticeResponse(
            mode=validated.mode,
            task_type=validated.task_type,
            recognized_question=recognized_question,
            report=report,
            retrieved_samples=[
                self._sample_reference(sample, validated.task_type)
                for sample in preparation.samples
            ],
            improvement_plan=improvement_plan,
        )

    def _build_improvement_plan(
        self,
        report: Any,
        question: str,
        essay: str,
        samples: list[dict[str, Any]],
    ) -> ImprovementPlan | None:
        """Generate a separate, sample-grounded learning plan after scoring."""

        selected = [
            sample
            for sample in samples[:3]
            if isinstance(sample.get("id"), str)
            and isinstance(sample.get("text"), str)
            and sample["text"].strip()
        ]
        if not selected:
            return None

        sample_texts = {sample["id"]: sample["text"] for sample in selected}
        scored_feedback = [
            {
                "criterion": result.criterion,
                "band": result.band,
                "issues": [
                    {"quote": issue.quote, "explanation": issue.explanation}
                    for issue in result.issues
                ],
                "improvements": result.improvements,
                "task_review": (
                    result.task_review.model_dump(mode="json")
                    if result.task_review
                    else None
                ),
            }
            for result in report.criterion_results
        ]
        sample_payload = [
            {
                "sample_id": sample["id"],
                "text": " ".join(sample["text"].split())[:1600],
            }
            for sample in selected
        ]
        prompt = (
            "你是 IELTS Academic 写作学习教练。作文已经由独立评分阶段完成评分；"
            "你只能生成学习建议，绝不能调整、解释或重新计算分数。\n"
            "先从评分反馈中选出最多 3 个最值得改进的问题，给出能执行的改写/练习动作。"
            "再从给定范文中选最多 3 个有直接帮助的写法，每条必须提供范文中逐字连续摘录的"
            "sample_quote，并说明该写法解决什么问题、用户如何迁移到自己的题目。"
            "只引用给定范文；不声称范文的分数或范文作者身份已核验；不要整段照搬，"
            "不要把范文内容伪装成用户作文。没有贴切的范文就留空 sample_lessons。\n"
            "summary、problem、action、lesson、how_to_apply 全部使用简体中文；"
            "sample_quote 保留范文英文原文，英文改写示例须配中文解释。\n"
            "只返回符合 JSON Schema 的 JSON。\n"
            f"题目：{question}\n作文：{essay[:5000]}\n"
        )
        prompt += (
            "评分反馈 JSON："
            + json.dumps(scored_feedback, ensure_ascii=False, separators=(",", ":"))
            + "\n可引用范文 JSON："
            + json.dumps(sample_payload, ensure_ascii=False, separators=(",", ":"))
        )
        try:
            raw = self.pipeline.model.generate(
                prompt, response_format=ImprovementPlan.model_json_schema()
            )
            plan = ImprovementPlan.model_validate_json(raw)
            require_chinese_feedback(
                [
                    plan.summary,
                    *(
                        text
                        for item in plan.actions
                        for text in (item.problem, item.action)
                    ),
                    *(
                        text
                        for item in plan.sample_lessons
                        for text in (item.lesson, item.how_to_apply)
                    ),
                ]
            )
            allowed_ids = set(sample_texts)
            for lesson in plan.sample_lessons:
                if lesson.sample_id not in allowed_ids:
                    raise ValueError("学习建议引用了未检索到的范文")
                normalized_sample = " ".join(sample_texts[lesson.sample_id].split())
                normalized_quote = " ".join(lesson.sample_quote.split())
                if normalized_quote not in normalized_sample:
                    raise ValueError("范文学习点的引用不是范文原文")
            for action in plan.actions:
                if not set(action.sample_ids).issubset(allowed_ids):
                    raise ValueError("改进动作引用了未检索到的范文")
            return plan
        except Exception:
            # Scoring is the core deliverable; a lesson-generation failure must
            # not invalidate a complete, already-validated score report.
            return None

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
        if not request.question:
            raise ValueError("评分前必须得到题目文字")
        if request.task_type == "task1" and not chart_context:
            chart_context = (
                "This RAG practice item does not include the original chart image "
                "or structured chart data. Judge overview, selection, comparisons, "
                "and language, but mark exact data accuracy as not_verifiable."
            )
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
            "chart_image_url",
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
