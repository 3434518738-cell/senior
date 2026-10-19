"""Generate controlled Task 1 process and map images with answer keys."""

from __future__ import annotations

import html
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "tests" / "fixtures" / "task1_visual_benchmark"

PROCESSES: list[dict[str, object]] = [
    {
        "id": "process_01_paper_recycling",
        "title": "Paper recycling process",
        "stages": [
            "Used paper is collected",
            "Paper is sorted",
            "Paper is pulped",
            "New paper is produced",
        ],
        "edges": [
            ["Used paper is collected", "Paper is sorted"],
            ["Paper is sorted", "Paper is pulped"],
            ["Paper is pulped", "New paper is produced"],
        ],
    },
    {
        "id": "process_02_water_treatment",
        "title": "Water treatment process",
        "stages": [
            "Raw water enters the plant",
            "Large debris is screened out",
            "Water is filtered",
            "Water is disinfected",
            "Treated water is stored",
        ],
        "edges": [
            ["Raw water enters the plant", "Large debris is screened out"],
            ["Large debris is screened out", "Water is filtered"],
            ["Water is filtered", "Water is disinfected"],
            ["Water is disinfected", "Treated water is stored"],
        ],
    },
    {
        "id": "process_03_bottle_reuse",
        "title": "Plastic bottle recycling with a branch",
        "stages": [
            "Bottles are collected",
            "Bottles are sorted",
            "Bottles are washed",
            "Plastic is crushed",
            "Plastic is recycled",
            "Unsuitable bottles are discarded",
        ],
        "edges": [
            ["Bottles are collected", "Bottles are sorted"],
            ["Bottles are sorted", "Bottles are washed"],
            ["Bottles are sorted", "Unsuitable bottles are discarded"],
            ["Bottles are washed", "Plastic is crushed"],
            ["Plastic is crushed", "Plastic is recycled"],
        ],
    },
]

MAPS: list[dict[str, object]] = [
    {
        "id": "map_01_riverside_village",
        "title": "Riverside village: 1990 and today",
        "before": {
            "north-west": "Farmland",
            "north-east": "Woodland",
            "south-west": "Village houses",
            "south-east": "Open field",
        },
        "after": {
            "north-west": "Housing estate",
            "north-east": "Car park",
            "south-west": "Village houses",
            "south-east": "Sports centre",
        },
    },
    {
        "id": "map_02_coastal_site",
        "title": "Coastal site: 1985 and present day",
        "before": {
            "north-west": "Beach",
            "north-east": "Fishing port",
            "south-west": "Cliff path",
            "south-east": "Grassland",
        },
        "after": {
            "north-west": "Beach",
            "north-east": "Marina",
            "south-west": "Coastal road",
            "south-east": "Holiday apartments",
        },
    },
    {
        "id": "map_03_campus",
        "title": "College campus: 2000 and now",
        "before": {
            "north-west": "Library",
            "north-east": "Car park",
            "south-west": "Science block",
            "south-east": "Playing field",
        },
        "after": {
            "north-west": "Library extension",
            "north-east": "Student accommodation",
            "south-west": "Science block",
            "south-east": "Sports hall",
        },
    },
]


def esc(value: str) -> str:
    return html.escape(value, quote=True)


def label(x: int, y: int, value: str, size: int = 25, weight: str = "400") -> str:
    return (
        f'<text x="{x}" y="{y}" text-anchor="middle" '
        f'font-family="Arial,sans-serif" font-size="{size}" '
        f'font-weight="{weight}" fill="#172033">{esc(value)}</text>'
    )


def process_svg(case: dict[str, object]) -> str:
    stages = case["stages"]
    assert isinstance(stages, list)
    height = max(800, 180 + len(stages) * 115)
    body = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="1400" '
        f'height="{height}" viewBox="0 0 1400 {height}">',
        '<rect width="100%" height="100%" fill="white"/>',
        label(700, 55, str(case["title"]), 32, "700"),
    ]
    positions = [(700, 145 + index * 105) for index in range(len(stages))]
    branch = case["id"] == "process_03_bottle_reuse"
    for index, (stage, (x, y)) in enumerate(zip(stages, positions)):
        body.append(
            f'<rect x="{x - 250}" y="{y - 38}" width="500" '
            'height="68" rx="10" fill="#f8fafc" stroke="#334155" '
            'stroke-width="3"/>'
        )
        body.append(label(x, y + 6, stage, 23))
        if index < len(stages) - 1 and not (branch and index == len(stages) - 2):
            body.append(
                f'<line x1="{x}" y1="{y + 31}" x2="{x}" '
                f'y2="{y + 65}" stroke="#334155" stroke-width="3" '
                'marker-end="url(#arrow)"/>'
            )
    if branch:
        x, y = positions[1]
        dest_x, dest_y = positions[5]
        body.append(
            f'<path d="M {x + 250} {y - 4} H 1120 V {dest_y - 4} '
            f'H {dest_x + 252}" fill="none" stroke="#334155" '
            'stroke-width="3" marker-end="url(#arrow)"/>'
        )
    body.insert(
        2,
        '<defs><marker id="arrow" markerWidth="10" markerHeight="10" '
        'refX="8" refY="3" orient="auto"><path d="M0,0 L0,6 L9,3 z" '
        'fill="#334155"/></marker></defs>',
    )
    body.append("</svg>")
    return "\n".join(body)


def map_svg(case: dict[str, object]) -> str:
    before = case["before"]
    after = case["after"]
    assert isinstance(before, dict) and isinstance(after, dict)
    body = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="1400" '
        'height="900" viewBox="0 0 1400 900">',
        '<rect width="100%" height="100%" fill="white"/>',
        label(700, 55, str(case["title"]), 32, "700"),
    ]
    locations = ["north-west", "north-east", "south-west", "south-east"]
    for panel_index, (heading, values) in enumerate(
        (("Before", before), ("After", after))
    ):
        x0 = 100 + panel_index * 680
        body.append(label(x0 + 270, 130, heading, 28, "700"))
        body.append(
            f'<text x="{x0 + 540}" y="190" font-family="Arial,sans-serif" '
            'font-size="22" font-weight="700">N ↑</text>'
        )
        for cell_index, location in enumerate(locations):
            row, col = divmod(cell_index, 2)
            x, y = x0 + col * 270, 230 + row * 270
            body.append(
                f'<rect x="{x}" y="{y}" width="250" height="245" '
                'fill="#f1f5f9" stroke="#475569" stroke-width="3"/>'
            )
            body.append(
                label(x + 125, y + 95, location.replace("-", " ").title(), 20, "700")
            )
            body.append(label(x + 125, y + 150, str(values[location]), 21))
        if panel_index == 0:
            body.append(
                '<path d="M 650 470 H 735" stroke="#64748b" '
                'stroke-width="4" marker-end="url(#arrow)"/>'
            )
    body.insert(
        2,
        '<defs><marker id="arrow" markerWidth="12" markerHeight="12" '
        'refX="9" refY="4" orient="auto"><path d="M0,0 L0,8 L10,4 z" '
        'fill="#64748b"/></marker></defs>',
    )
    body.append("</svg>")
    return "\n".join(body)


def main() -> None:
    for folder in (OUT / "svg", OUT / "images"):
        folder.mkdir(parents=True, exist_ok=True)
    manifest: list[dict[str, object]] = []
    for kind, cases in (("process", PROCESSES), ("map", MAPS)):
        for case in cases:
            case_id = str(case["id"])
            svg = process_svg(case) if kind == "process" else map_svg(case)
            (OUT / "svg" / f"{case_id}.svg").write_text(svg, encoding="utf-8")
            expected: dict[str, object]
            if kind == "process":
                expected = {"stages": case["stages"], "edges": case["edges"]}
            else:
                before = case["before"]
                after = case["after"]
                assert isinstance(before, dict) and isinstance(after, dict)
                changes = []
                for location in before:
                    if before[location] != after[location]:
                        changes.append(
                            {
                                "location": location,
                                "before": before[location],
                                "after": after[location],
                            }
                        )
                expected = {"locations": list(before), "changes": changes}
            sidecar = {
                "id": case_id,
                "visual_type": kind,
                "title": case["title"],
                "source_type": "synthetic_controlled_visual",
                "source": (
                    "Generated in-project for repeatable model vision evaluation; "
                    "not an IELTS question or past paper."
                ),
                "expected": expected,
            }
            (OUT / f"{case_id}.json").write_text(
                json.dumps(sidecar, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            manifest.append(
                {
                    "id": case_id,
                    "visual_type": kind,
                    "source_type": sidecar["source_type"],
                }
            )
    (OUT / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"Generated {len(manifest)} controlled process/map cases under {OUT}")


if __name__ == "__main__":
    main()
