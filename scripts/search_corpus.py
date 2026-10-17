"""Search the IELTS Academic essay collections from the command line."""

from __future__ import annotations

import argparse
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


def main() -> int:
    parser = argparse.ArgumentParser(description="检索相似的 IELTS Academic 范文")
    parser.add_argument("--task", choices=("task1", "task2"), required=True)
    parser.add_argument("--query", required=True, help="题目或作文主题")
    parser.add_argument("--question-type", help="题目类型过滤")
    parser.add_argument("--chart-type", help="Task 1 图表类型过滤")
    parser.add_argument("--top-k", type=int, help="返回结果数量")
    args = parser.parse_args()
    settings = get_settings()
    try:
        store = ChromaVectorStore(settings=settings)
        with OllamaClient(settings=settings) as client:
            retriever = AcademicRetriever(client, store, settings=settings)
            results = retriever.search(
                args.query,
                args.task,
                question_type=args.question_type,
                chart_type=args.chart_type,
                top_k=args.top_k,
            )
    except (RuntimeError, ValueError, FileNotFoundError) as exc:
        print(f"检索失败: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(results, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
