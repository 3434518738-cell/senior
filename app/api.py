"""FastAPI application exposing the IELTS Academic scoring workflow."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI, HTTPException

from app.config import get_settings
from app.ollama_client import OllamaClient
from app.rag.retrieval import AcademicRetriever
from app.rag.vector_store import ChromaVectorStore
from app.rubric.indexing import RubricVectorStore
from app.scoring.pipeline import ScoringPipeline, ScoringPipelineError
from app.scoring.schemas import ScoreReport, ScoreRequest
from app.scoring.workflow import ScoringWorkflow


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


def create_app(workflow: ScoringWorkflow | None = None) -> FastAPI:
    """Create the API app; inject a workflow in tests or build local services."""

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        if workflow is not None:
            application.state.scoring_workflow = workflow
        else:
            scoring_workflow, ollama_client = _build_workflow()
            application.state.scoring_workflow = scoring_workflow
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

    return application


app = create_app()
