"""Score one IELTS Academic essay with the local Qwen3.5/BGE-M3 pipeline."""

from __future__ import annotations

import argparse
import base64
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.config import get_settings  # noqa: E402
from app.ollama_client import OllamaClient  # noqa: E402
from app.rag.retrieval import AcademicRetriever  # noqa: E402
from app.rag.vector_store import ChromaVectorStore  # noqa: E402
from app.rubric.indexing import RubricVectorStore  # noqa: E402
from app.scoring.pipeline import ScoringPipeline, ScoringPipelineError  # noqa: E402
from app.scoring.schemas import ScoreRequest  # noqa: E402
from app.scoring.workflow import ScoringWorkflow  # noqa: E402


def main() -> int:
    """Read one essay file, call the local models, and print a JSON report."""

    parser = argparse.ArgumentParser(description="评分一篇 IELTS Academic 作文")
    parser.add_argument("--task", choices=("task1", "task2"), required=True)
    parser.add_argument("--question", required=True, help="完整 Academic 题目")
    parser.add_argument("--essay-file", type=Path, required=True)
    parser.add_argument("--chart-type", help="Task 1 图表类型，例如 line_graph")
    parser.add_argument("--chart-context", help="Task 1 图表数据或文字描述")
    parser.add_argument(
        "--chart-image", type=Path, help="Task 1 图表图片（PNG/JPEG/GIF/WebP）"
    )
    parser.add_argument(
        "--workflow",
        action="store_true",
        help="使用 LangGraph 编排评分；默认使用同一评分核心的串行入口",
    )
    args = parser.parse_args()

    try:
        essay = args.essay_file.read_text(encoding="utf-8")
        request = ScoreRequest(
            task_type=args.task,
            question=args.question,
            essay=essay,
            chart_type=args.chart_type,
            chart_context=args.chart_context,
            chart_image_base64=(
                base64.b64encode(args.chart_image.read_bytes()).decode("ascii")
                if args.chart_image
                else None
            ),
        )
        settings = get_settings()
        sample_store = ChromaVectorStore(settings=settings)
        rubric_store = RubricVectorStore(settings=settings)
        with OllamaClient(settings=settings) as client:
            sample_searcher = AcademicRetriever(client, sample_store, settings=settings)
            pipeline = ScoringPipeline(client, rubric_store, sample_searcher)
            report = (
                ScoringWorkflow(pipeline).score(request)
                if args.workflow
                else pipeline.score(request)
            )
    except (OSError, RuntimeError, ValueError, ScoringPipelineError) as exc:
        print(f"作文评分失败: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(report.model_dump(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
