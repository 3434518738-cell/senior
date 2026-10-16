"""Run the application environment check from the project root."""

from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.main import run_check  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(run_check())
