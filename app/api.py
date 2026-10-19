"""FastAPI application exposing the IELTS Academic scoring workflow."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI, HTTPException

from app.config import get_settings
from app.practice.repository import QuestionBankRepository
from app.practice.schemas import (
    PracticeSessionCreateRequest,
    PracticeSessionResponse,
    PracticeSessionSubmissionResponse,
    PracticeSessionSubmitRequest,
    QuestionListResponse,
    QuestionSummary,
)
from app.rag.corpus_loader import TaskType
from app.ollama_client import OllamaClient
from app.rag.retrieval import AcademicRetriever
from app.rag.vector_store import ChromaVectorStore
from app.rubric.indexing import RubricVectorStore
from app.scoring.pipeline import ScoringPipeline, ScoringPipelineError
from app.scoring.schemas import (
    ChartUnderstanding,
    ScoreReport,
    ScoreRequest,
    UnifiedPracticeRequest,
    UnifiedPracticeResponse,
    VisualInspectionRequest,
)
from app.scoring.workflow import ScoringWorkflow
from app.services.practice import PracticeService, PracticeServiceError


def _build_workflow() -> tuple[ScoringWorkflow, OllamaClient]:
    """Construct application services while keeping the Ollama client open."""

    settings = get_settings()
    client = OllamaClient(settings=settings)
    try:
        sample_store = ChromaVectorStore(settings=settings)
        rubric_store = RubricVectorStore(settings=settings)
        searcher = AcademicRetriever(client, sample_store, settings=settings)
        pipeline = ScoringPipeline(client, rubric_store, searcher)
        return ScoringWorkflow(pipeline), client
    except Exception:
        client.close()
        raise


def create_app(
    workflow: ScoringWorkflow | None = None,
    practice_service: PracticeService | None = None,
) -> FastAPI:
    """Create the API app; inject a workflow in tests or build local services."""

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        if workflow is not None:
            application.state.scoring_workflow = workflow
            application.state.practice_service = practice_service or PracticeService(
                workflow.pipeline,
                workflow,
                QuestionBankRepository(
                    get_settings().practice_db_path, get_settings().corpus_dir
                ),
            )
        else:
            scoring_workflow, ollama_client = _build_workflow()
            application.state.scoring_workflow = scoring_workflow
            application.state.practice_service = practice_service or PracticeService(
                scoring_workflow.pipeline,
                scoring_workflow,
                QuestionBankRepository(
                    get_settings().practice_db_path, get_settings().corpus_dir
                ),
            )
            application.state.ollama_client = ollama_client
        try:
            yield
        finally:
            active_client = getattr(application.state, "ollama_client", None)
            if active_client is not None:
                active_client.close()

    application = FastAPI(
        title="IELTS Academic Writing Assistant",
        description="本地 Academic 写作评分接口，使用 LangGraph 和 Ollama。",
        version="0.1.0",
        lifespan=lifespan,
    )

    @application.get("/health", tags=["system"])
    def health() -> dict[str, str]:
        return {"status": "ok", "exam_type": "academic"}

    @application.post(
        "/api/v1/score",
        response_model=ScoreReport,
        tags=["scoring"],
        summary="评分一篇 IELTS Academic 作文",
    )
    def score_essay(request: ScoreRequest) -> ScoreReport:
        scoring_workflow: ScoringWorkflow | None = getattr(
            application.state, "scoring_workflow", None
        )
        if scoring_workflow is None:
            raise HTTPException(status_code=503, detail="评分服务尚未就绪")
        try:
            return scoring_workflow.score(request)
        except ScoringPipelineError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        except (RuntimeError, ValueError) as exc:
            raise HTTPException(status_code=502, detail=f"评分服务失败: {exc}") from exc

    @application.post(
        "/api/v1/task1/inspect",
        response_model=ChartUnderstanding,
        tags=["vision"],
        summary="识别 Academic Task 1 图片，返回可核对的视觉事实",
    )
    def inspect_task1_image(request: VisualInspectionRequest) -> ChartUnderstanding:
        service: PracticeService | None = getattr(
            application.state, "practice_service", None
        )
        if service is None:
            raise HTTPException(status_code=503, detail="统一练习服务尚未就绪")
        try:
            return service.inspect_task1_image(request)
        except PracticeServiceError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

    @application.post(
        "/api/v1/practice/score",
        response_model=UnifiedPracticeResponse,
        tags=["practice"],
        summary="统一提交每日一练、题库练习或用户上传作文",
    )
    def score_practice(request: UnifiedPracticeRequest) -> UnifiedPracticeResponse:
        service: PracticeService | None = getattr(
            application.state, "practice_service", None
        )
        if service is None:
            raise HTTPException(status_code=503, detail="统一练习服务尚未就绪")
        try:
            return service.score(request)
        except PracticeServiceError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @application.get(
        "/api/v1/question-bank",
        response_model=QuestionListResponse,
        tags=["question-bank"],
        summary="浏览 Academic 题库",
    )
    def list_question_bank(
        task_type: TaskType | None = None,
        question_type: str | None = None,
        chart_type: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> QuestionListResponse:
        service: PracticeService | None = getattr(
            application.state, "practice_service", None
        )
        if service is None:
            raise HTTPException(status_code=503, detail="题库服务尚未就绪")
        try:
            return service.list_questions(
                task_type=task_type,
                question_type=question_type,
                chart_type=chart_type,
                limit=limit,
                offset=offset,
            )
        except PracticeServiceError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @application.get(
        "/api/v1/question-bank/{question_id}",
        response_model=QuestionSummary,
        tags=["question-bank"],
        summary="查看一个 Academic 题目",
    )
    def get_question_bank_item(question_id: str) -> QuestionSummary:
        service: PracticeService | None = getattr(
            application.state, "practice_service", None
        )
        if service is None:
            raise HTTPException(status_code=503, detail="题库服务尚未就绪")
        try:
            return service.get_question(question_id)
        except PracticeServiceError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @application.post(
        "/api/v1/practice/sessions",
        response_model=PracticeSessionResponse,
        tags=["practice"],
        summary="创建每日一练或题库专项练习",
    )
    def create_practice_session(
        request: PracticeSessionCreateRequest,
    ) -> PracticeSessionResponse:
        service: PracticeService | None = getattr(
            application.state, "practice_service", None
        )
        if service is None:
            raise HTTPException(status_code=503, detail="练习服务尚未就绪")
        try:
            return service.start_session(request)
        except PracticeServiceError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @application.get(
        "/api/v1/practice/sessions/{session_id}",
        response_model=PracticeSessionResponse,
        tags=["practice"],
        summary="查看练习会话和提交记录",
    )
    def get_practice_session(session_id: str) -> PracticeSessionResponse:
        service: PracticeService | None = getattr(
            application.state, "practice_service", None
        )
        if service is None:
            raise HTTPException(status_code=503, detail="练习服务尚未就绪")
        try:
            return service.get_session(session_id)
        except PracticeServiceError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @application.post(
        "/api/v1/practice/sessions/{session_id}/submit",
        response_model=PracticeSessionSubmissionResponse,
        tags=["practice"],
        summary="提交会话中的一篇作文并保存评分报告",
    )
    def submit_practice_session(
        session_id: str,
        request: PracticeSessionSubmitRequest,
    ) -> PracticeSessionSubmissionResponse:
        service: PracticeService | None = getattr(
            application.state, "practice_service", None
        )
        if service is None:
            raise HTTPException(status_code=503, detail="练习服务尚未就绪")
        try:
            return service.submit_session_item(session_id, request)
        except PracticeServiceError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    return application


app = create_app()
