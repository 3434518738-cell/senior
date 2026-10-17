"""Inspect official Academic rubric context for one task criterion."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.config import get_settings  # noqa: E402
from app.rubric.indexing import RubricVectorStore, retrieve_rubric_context  # noqa: E402


def main() -> int:
    """Print all official band descriptors and guidance for a criterion."""

    parser = argparse.ArgumentParser(description="查看 Academic 评分标准检索上下文")
    parser.add_argument("--task", choices=("task1", "task2"), required=True)
    parser.add_argument(
        "--criterion",
        choices=(
            "task_achievement",
            "task_response",
            "coherence_and_cohesion",
            "lexical_resource",
            "grammatical_range_and_accuracy",
        ),
        required=True,
    )
    args = parser.parse_args()
    try:
        context = retrieve_rubric_context(
            RubricVectorStore(settings=get_settings()), args.task, args.criterion
        )
    except (RuntimeError, ValueError) as exc:
        print(f"评分标准检索失败: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(context, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
