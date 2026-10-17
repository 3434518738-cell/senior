"""Build the separate IELTS Academic assessment rubric vector collection."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.rubric.indexing import build_default_rubric_index  # noqa: E402


def main() -> int:
    """Parse options and build the rubric index using local BGE-M3."""

    parser = argparse.ArgumentParser(description="建立 Academic 评分标准向量索引")
    parser.add_argument(
        "--path",
        type=Path,
        default=Path("docs/rubrics/academic_writing_rubric.json"),
        help="已校验的 Academic rubric JSON 文件",
    )
    parser.add_argument(
        "--update",
        action="store_true",
        help="保留集合并执行 upsert；默认完整重建",
    )
    args = parser.parse_args()
    try:
        result = build_default_rubric_index(args.path, rebuild=not args.update)
    except (RuntimeError, ValueError, FileNotFoundError) as exc:
        print(f"评分标准索引构建失败: {exc}", file=sys.stderr)
        return 1
    print(
        f"rubric index OK: descriptors={result.descriptor_count}, "
        f"guidance={result.guidance_count}, collection={result.collection_name}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
