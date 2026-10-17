"""Build the local IELTS Academic sample vector indexes."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.rag.indexing import build_default_index  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(
        description="建立 IELTS Academic Task 1 / Task 2 范文向量索引"
    )
    parser.add_argument(
        "--rebuild",
        action="store_true",
        help="先清空两个 Academic 范文集合，再重新建库",
    )
    args = parser.parse_args()
    try:
        for result in build_default_index(rebuild=args.rebuild):
            print(
                f"{result.task_type}: indexed={result.indexed_count}, "
                f"excluded={result.excluded_count}, "
                f"collection={result.collection_name}"
            )
    except (RuntimeError, ValueError, FileNotFoundError) as exc:
        print(f"索引构建失败: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
