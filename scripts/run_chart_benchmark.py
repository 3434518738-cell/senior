"""Run the local Qwen chart reader against the 10-chart fixture set."""

from __future__ import annotations

import base64
import argparse
import json
import re
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.ollama_client import OllamaClient  # noqa: E402
from app.scoring.pipeline import ScoringPipeline  # noqa: E402


FIXTURES = ROOT / "tests" / "fixtures" / "chart_benchmark"
RESULTS = FIXTURES / "results"


def norm(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value).casefold())


def series_match(expected: str, actual: str) -> bool:
    e = norm(expected.split("(", 1)[0])
    a = norm(actual.split("(", 1)[0])
    return bool(e and a and (e == a or e in a or a in e))


def category_match(expected: str, actual: str) -> bool:
    return norm(expected) == norm(actual)


def value_for_label(series: Any, expected_label: str) -> Any | None:
    for point in series.points:
        if category_match(expected_label, point.label):
            return point
    return None


def direction(values: list[float]) -> str:
    if values[-1] > values[0]:
        return "rising"
    if values[-1] < values[0]:
        return "falling"
    return "stable"


def evaluate(case: dict[str, Any], understanding: Any) -> dict[str, Any]:
    expected = case["expected"]
    actual_series = understanding.series
    series_hits = sum(
        any(series_match(expected_name, actual.name) for actual in actual_series)
        for expected_name in expected["series_names"]
    )
    actual_categories = understanding.axes_or_categories
    category_hits = sum(
        any(category_match(category, actual) for actual in actual_categories)
        for category in expected["categories"]
    )
    value_total = 0
    value_available = 0
    value_correct = 0
    precision_hits = 0
    categories_are_time = bool(expected["categories"]) and all(
        re.fullmatch(r"\d{4}", str(category).strip())
        for category in expected["categories"]
    )
    trend_total = 0
    trend_hits = 0
    series_details: list[dict[str, Any]] = []
    tolerance = float(expected["tolerance"])
    for expected_name, values in expected["series"].items():
        actual = next(
            (item for item in actual_series if series_match(expected_name, item.name)),
            None,
        )
        expected_direction = direction([float(value) for value in values])
        actual_direction = "unknown"
        if actual and actual.trend:
            trend_text = actual.trend.casefold()
            for candidate in ("rising", "falling", "stable"):
                if candidate in trend_text:
                    actual_direction = candidate
                    break
        if categories_are_time:
            trend_total += 1
            trend_hits += int(actual_direction == expected_direction)
        expected_values = [float(value) for value in values]
        series_value_available = 0
        series_value_correct = 0
        series_precision_hits = 0
        if actual:
            for label, expected_value in zip(expected["categories"], expected_values):
                point = value_for_label(actual, label)
                value_total += 1
                if point is not None:
                    value_available += 1
                    series_value_available += 1
                    if abs(float(point.value) - expected_value) <= tolerance:
                        value_correct += 1
                        series_value_correct += 1
                    expected_precision = expected["precision"]
                    if point.precision == expected_precision or (
                        expected_precision == "estimated"
                        and point.precision == "estimated"
                    ):
                        precision_hits += 1
                        series_precision_hits += 1
        series_details.append(
            {
                "expected": expected_name,
                "actual": actual.name if actual else None,
                "expected_direction": expected_direction,
                "actual_direction": actual_direction,
                "values_expected": len(expected_values),
                "values_available": series_value_available,
                "values_correct": series_value_correct,
                "precision_hits": series_precision_hits,
            }
        )
    estimated_points = [
        point
        for series in actual_series
        for point in series.points
        if point.precision == "estimated"
    ]
    uncertainty_ok = (
        bool(understanding.uncertain_or_unreadable) or bool(estimated_points)
        if expected.get("expected_uncertainty")
        else not estimated_points
    )
    return {
        "id": case["id"],
        "chart_type_expected": expected["chart_type"],
        "chart_type_actual": understanding.chart_type,
        "chart_type_correct": norm(expected["chart_type"]).replace("graph", "")
        in norm(understanding.chart_type).replace("graph", "")
        or norm(understanding.chart_type).replace("graph", "")
        in norm(expected["chart_type"]).replace("graph", ""),
        "series_expected": len(
            expected["series_names"],
        ),
        "series_hits": series_hits,
        "categories_expected": len(expected["categories"]),
        "category_hits": category_hits,
        "value_total": value_total,
        "value_available": value_available,
        "value_correct": value_correct,
        "precision_hits": precision_hits,
        "trend_total": trend_total,
        "trend_hits": trend_hits,
        "uncertainty_expected": bool(expected.get("expected_uncertainty")),
        "uncertainty_ok": uncertainty_ok,
        "series_details": series_details,
        "uncertain_or_unreadable": understanding.uncertain_or_unreadable,
        "chart_summary": understanding.chart_summary,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="验收本地 Qwen 的图表读取结果")
    parser.add_argument(
        "--evaluate-only",
        action="store_true",
        help="不调用模型，只基于已有逐张结果重新计算统计口径",
    )
    parser.add_argument("--case", help="只运行指定样本 ID，多个 ID 用逗号分隔")
    args = parser.parse_args()
    RESULTS.mkdir(parents=True, exist_ok=True)
    cases = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted(FIXTURES.glob("chart_*.json"))
    ]
    if args.case:
        selected_ids = {item.strip() for item in args.case.split(",") if item.strip()}
        cases = [case for case in cases if case["id"] in selected_ids]
        if not cases:
            parser.error(f"找不到基准样本: {args.case}")
    results: list[dict[str, Any]] = []
    started = time.perf_counter()
    if args.evaluate_only:
        for case in cases:
            path = RESULTS / f"{case['id']}.json"
            stored = json.loads(path.read_text(encoding="utf-8"))
            if stored.get("status") == "ok":
                from app.scoring.schemas import ChartUnderstanding
                from app.scoring.schemas import ChartStructure

                understanding = ChartUnderstanding.model_validate(
                    stored["understanding"]
                )
                structure = ChartStructure(
                    chart_type=case["expected"]["chart_type"],
                    categories=case["expected"]["categories"],
                    series_names=case["expected"]["series_names"],
                    has_explicit_data_labels=case["expected"]["precision"]
                    == "explicit",
                )
                understanding = ScoringPipeline._summarize_chart(
                    understanding, structure
                )
                result = evaluate(case, understanding)
                result["status"] = "ok"
                result["understanding"] = stored["understanding"]
            else:
                result = stored
            results.append(result)
    else:
        with OllamaClient() as client:
            pipeline = ScoringPipeline(client, None)  # type: ignore[arg-type]
            for index, case in enumerate(cases, start=1):
                image_path = FIXTURES / "images" / f"{case['id']}.png"
                image = base64.b64encode(image_path.read_bytes()).decode("ascii")
                print(f"[{index}/{len(cases)}] {case['id']} ...", flush=True)
                try:
                    understanding = pipeline._understand_chart_image(image)
                    result = evaluate(case, understanding)
                    result["status"] = "ok"
                    result["understanding"] = understanding.model_dump()
                except Exception as exc:  # keep the batch running and record failures
                    result = {"id": case["id"], "status": "error", "error": str(exc)}
                (RESULTS / f"{case['id']}.json").write_text(
                    json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
                )
                results.append(result)
                print(
                    json.dumps(
                        {
                            key: result.get(key)
                            for key in (
                                "status",
                                "chart_type_correct",
                                "series_hits",
                                "category_hits",
                                "value_correct",
                                "value_available",
                                "trend_hits",
                                "uncertainty_ok",
                            )
                        },
                        ensure_ascii=False,
                    ),
                    flush=True,
                )
    successful = [item for item in results if item.get("status") == "ok"]
    previous_elapsed = 0.0
    summary_path = RESULTS / "summary.json"
    if args.evaluate_only and summary_path.exists():
        try:
            previous_elapsed = float(
                json.loads(summary_path.read_text(encoding="utf-8")).get(
                    "elapsed_seconds", 0.0
                )
            )
        except (OSError, TypeError, ValueError):
            previous_elapsed = 0.0
    aggregate = {
        "cases": len(results),
        "successful_cases": len(successful),
        "chart_type_accuracy": (
            sum(bool(item.get("chart_type_correct")) for item in successful)
            / len(successful)
            if successful
            else 0
        ),
        "series_accuracy": (
            sum(item.get("series_hits", 0) for item in successful)
            / sum(item.get("series_expected", 0) for item in successful)
            if successful
            else 0
        ),
        "category_accuracy": (
            sum(item.get("category_hits", 0) for item in successful)
            / sum(item.get("categories_expected", 0) for item in successful)
            if successful
            else 0
        ),
        "trend_accuracy": (
            sum(item.get("trend_hits", 0) for item in successful)
            / sum(item.get("trend_total", 0) for item in successful)
            if successful and sum(item.get("trend_total", 0) for item in successful)
            else None
        ),
        "value_accuracy_when_available": (
            sum(item.get("value_correct", 0) for item in successful)
            / sum(item.get("value_available", 0) for item in successful)
            if successful
            else 0
        ),
        "value_coverage": (
            sum(item.get("value_available", 0) for item in successful)
            / sum(item.get("value_total", 0) for item in successful)
            if successful
            else 0
        ),
        "precision_accuracy_when_available": (
            sum(item.get("precision_hits", 0) for item in successful)
            / sum(item.get("value_available", 0) for item in successful)
            if successful
            else 0
        ),
        "uncertainty_accuracy": (
            sum(bool(item.get("uncertainty_ok")) for item in successful)
            / len(successful)
            if successful
            else 0
        ),
        "elapsed_seconds": (
            previous_elapsed
            if args.evaluate_only
            else round(time.perf_counter() - started, 2)
        ),
        "cases_detail": results,
    }
    (RESULTS / "summary.json").write_text(
        json.dumps(aggregate, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(aggregate, ensure_ascii=False, indent=2))
    return 0 if len(successful) == len(cases) else 1


if __name__ == "__main__":
    raise SystemExit(main())
