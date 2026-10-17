"""Validate the checked-in IELTS Academic rubric JSON."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.rubric.loader import load_academic_rubric  # noqa: E402


def main() -> int:
    """Parse the rubric path, validate it, and print a compact summary."""

    parser = argparse.ArgumentParser(description="校验 IELTS Academic 评分标准")
    parser.add_argument(
        "--path",
        type=Path,
        default=Path("docs/rubrics/academic_writing_rubric.json"),
    )
    args = parser.parse_args()
    rubric = load_academic_rubric(args.path)
    print(
        f"rubric OK: {len(rubric.descriptors)} descriptors, "
        f"{len(rubric.guidance)} guidance items, version={rubric.source_version}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
