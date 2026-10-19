"""Evaluate local Qwen reading of controlled Task 1 process/map images."""

from __future__ import annotations

import argparse
import base64
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
from app.scoring.schemas import ChartUnderstanding  # noqa: E402

FIXTURES = ROOT / "tests" / "fixtures" / "task1_visual_benchmark"
RESULTS = FIXTURES / "results"


def norm(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value).casefold())


def score_case(case: dict[str, Any], result: ChartUnderstanding) -> dict[str, Any]:
    expected = case["expected"]
    kind = case["visual_type"]
    type_correct = result.visual_type == kind
    if kind == "process":
        expected_stages = expected["stages"]
        actual_stages = sorted(result.process_stages, key=lambda stage: stage.order)
        actual_labels = [norm(stage.label) for stage in actual_stages]
        label_hits = sum(norm(label) in actual_labels for label in expected_stages)
        order_correct = [norm(label) for label in expected_stages] == actual_labels
        expected_edges = {
            (norm(source), norm(target)) for source, target in expected["edges"]
        }
        actual_edges = {
            (norm(stage.label), norm(target))
            for stage in actual_stages
            for target in stage.next_steps
        }
        edge_hits = len(expected_edges & actual_edges)
        return {
            "id": case["id"],
            "visual_type_correct": type_correct,
            "labels_expected": len(expected_stages),
            "labels_found": label_hits,
            "stage_order_correct": order_correct,
            "edges_expected": len(expected_edges),
            "edges_found": edge_hits,
            "summary": result.chart_summary,
            "uncertain_or_unreadable": result.uncertain_or_unreadable,
        }

    expected_changes = expected["changes"]
    actual_features = result.map_features
    feature_hits = 0
    field_total = 0
    field_hits = 0
    details = []
    for change in expected_changes:
        actual = next(
            (
                item
                for item in actual_features
                if norm(item.location) == norm(change["location"])
            ),
            None,
        )
        correct = bool(actual)
        checks = {}
        for field in ("before", "after"):
            field_total += 1
            match = bool(actual and norm(getattr(actual, field)) == norm(change[field]))
            checks[field] = match
            field_hits += int(match)
            correct = correct and match
        feature_hits += int(correct)
        details.append(
            {
                "location_expected": change["location"],
                "location_found": actual.location if actual else None,
                "fields_correct": checks,
            }
        )
    return {
        "id": case["id"],
        "visual_type_correct": type_correct,
        "changes_expected": len(expected_changes),
        "changes_correct": feature_hits,
        "change_fields_expected": field_total,
        "change_fields_correct": field_hits,
        "change_details": details,
        "summary": result.chart_summary,
        "uncertain_or_unreadable": result.uncertain_or_unreadable,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="验收本地 Qwen 的流程图和地图识别")
    parser.add_argument(
        "--evaluate-only", action="store_true", help="仅重新统计已保存结果"
    )
    parser.add_argument("--case", help="只运行指定样本 ID")
    args = parser.parse_args()
    RESULTS.mkdir(parents=True, exist_ok=True)
    cases = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted(FIXTURES.glob("process_*.json"))
    ]
    cases += [
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted(FIXTURES.glob("map_*.json"))
    ]
    if args.case:
        cases = [case for case in cases if case["id"] == args.case]
        if not cases:
            parser.error(f"找不到基准样本: {args.case}")
    started = time.perf_counter()
    results: list[dict[str, Any]] = []
    if args.evaluate_only:
        for case in cases:
            stored = json.loads(
                (RESULTS / f"{case['id']}.json").read_text(encoding="utf-8")
            )
            if stored.get("status") == "ok":
                understanding = ChartUnderstanding.model_validate(
                    stored["understanding"]
                )
                result = score_case(case, understanding)
                result["status"] = "ok"
                result["understanding"] = stored["understanding"]
            else:
                result = stored
            results.append(result)
    else:
        with OllamaClient() as client:
            pipeline = ScoringPipeline(client, None)  # type: ignore[arg-type]
            for index, case in enumerate(cases, start=1):
                path = FIXTURES / "images" / f"{case['id']}.png"
                image = base64.b64encode(path.read_bytes()).decode("ascii")
                print(f"[{index}/{len(cases)}] {case['id']} ...", flush=True)
                try:
                    understanding = pipeline._understand_chart_image(image)
                    result = score_case(case, understanding)
                    result["status"] = "ok"
                    result["understanding"] = understanding.model_dump()
                except Exception as exc:
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
                                "visual_type_correct",
                                "labels_found",
                                "stage_order_correct",
                                "edges_found",
                                "changes_correct",
                                "change_fields_correct",
                            )
                        },
                        ensure_ascii=False,
                    ),
                    flush=True,
                )
    successful = [item for item in results if item.get("status") == "ok"]
    process = [item for item in successful if item["id"].startswith("process_")]
    maps = [item for item in successful if item["id"].startswith("map_")]
    summary = {
        "cases": len(results),
        "successful_cases": len(successful),
        "visual_type_accuracy": (
            sum(bool(item.get("visual_type_correct")) for item in successful)
            / len(successful)
            if successful
            else 0
        ),
        "process_stage_label_accuracy": (
            sum(item.get("labels_found", 0) for item in process)
            / sum(item.get("labels_expected", 0) for item in process)
            if process
            else None
        ),
        "process_order_accuracy": (
            sum(bool(item.get("stage_order_correct")) for item in process)
            / len(process)
            if process
            else None
        ),
        "process_edge_accuracy": (
            sum(item.get("edges_found", 0) for item in process)
            / sum(item.get("edges_expected", 0) for item in process)
            if process
            else None
        ),
        "map_change_accuracy": (
            sum(item.get("changes_correct", 0) for item in maps)
            / sum(item.get("changes_expected", 0) for item in maps)
            if maps
            else None
        ),
        "map_before_after_field_accuracy": (
            sum(item.get("change_fields_correct", 0) for item in maps)
            / sum(item.get("change_fields_expected", 0) for item in maps)
            if maps
            else None
        ),
        "elapsed_seconds": (
            round(time.perf_counter() - started, 2) if not args.evaluate_only else None
        ),
        "cases_detail": results,
    }
    (RESULTS / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if len(successful) == len(cases) else 1


if __name__ == "__main__":
    raise SystemExit(main())
