"""Generate deterministic IELTS Academic Task 1 chart fixtures.

The fixtures are rendered as SVG first and converted to PNG by the local
browser in the shell command documented in the benchmark README.  Every image
has a JSON sidecar containing its source, exact benchmark data, expected
structure, and tolerances.
"""

from __future__ import annotations

import json
import math
import html
from pathlib import Path
from typing import Any, cast


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "tests" / "fixtures" / "chart_benchmark"
SVG_DIR = OUT / "svg"
IMAGE_DIR = OUT / "images"


def esc(value: object) -> str:
    return html.escape(str(value), quote=True)


def text(
    x: float,
    y: float,
    value: object,
    size: int = 24,
    *,
    anchor: str = "start",
    weight: str = "400",
    fill: str = "#1f2937",
) -> str:
    return f'<text x="{x:.1f}" y="{y:.1f}" font-family="Arial, sans-serif" font-size="{size}px" text-anchor="{anchor}" font-weight="{weight}" fill="{fill}">{esc(value)}</text>'


def base(title: str, subtitle: str = "") -> list[str]:
    body = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="1400" height="900" viewBox="0 0 1400 900">',
        '<rect width="1400" height="900" fill="white"/>',
        text(700, 55, title, 32, anchor="middle", weight="700"),
    ]
    if subtitle:
        body.append(text(700, 88, subtitle, 20, anchor="middle", fill="#4b5563"))
    return body


def finish(body: list[str]) -> str:
    body.append("</svg>")
    return "\n".join(body)


def axes(
    body: list[str],
    *,
    y_max: float,
    y_step: float,
    y_label: str,
    categories: list[str],
    left: float = 150,
    top: float = 150,
    width: float = 1120,
    height: float = 570,
) -> tuple[float, float, float, float]:
    right = left + width
    bottom = top + height
    body.extend(
        [
            text(42, top + height / 2, y_label, 22, anchor="middle"),
            f'<line x1="{left}" y1="{top}" x2="{left}" y2="{bottom}" stroke="#111827" stroke-width="3"/>',
            f'<line x1="{left}" y1="{bottom}" x2="{right}" y2="{bottom}" stroke="#111827" stroke-width="3"/>',
        ]
    )
    tick = 0.0
    while tick <= y_max + 1e-9:
        y = bottom - tick / y_max * height
        body.append(
            f'<line x1="{left}" y1="{y:.1f}" x2="{right}" y2="{y:.1f}" stroke="#d1d5db" stroke-width="1"/>'
        )
        body.append(text(left - 18, y + 7, f"{tick:g}", 18, anchor="end"))
        tick += y_step
    if categories:
        step = width / max(1, len(categories) - 1)
        for i, category in enumerate(categories):
            x = left + i * step
            body.append(text(x, bottom + 38, category, 18, anchor="middle"))
    return left, top, width, height


def point_xy(
    left: float,
    top: float,
    width: float,
    height: float,
    y_max: float,
    index: int,
    count: int,
    value: float,
) -> tuple[float, float]:
    x = left + (width * index / max(1, count - 1))
    y = top + height - value / y_max * height
    return x, y


def line_chart(
    title: str,
    categories: list[str],
    series: dict[str, list[float]],
    y_max: float,
    y_step: float,
    y_label: str,
    *,
    source_note: str,
) -> str:
    body = base(title, source_note)
    left, top, width, height = axes(
        body, y_max=y_max, y_step=y_step, y_label=y_label, categories=categories
    )
    colors = ["#2563eb", "#dc2626", "#059669", "#9333ea"]
    for sidx, (name, values) in enumerate(series.items()):
        color = colors[sidx % len(colors)]
        points = [
            point_xy(left, top, width, height, y_max, i, len(categories), value)
            for i, value in enumerate(values)
        ]
        body.append(
            '<polyline fill="none" stroke="%s" stroke-width="5" points="%s"/>'
            % (color, " ".join(f"{x:.1f},{y:.1f}" for x, y in points))
        )
        for x, y in points:
            body.append(
                f'<circle cx="{x:.1f}" cy="{y:.1f}" r="7" fill="white" stroke="{color}" stroke-width="4"/>'
            )
        lx = 220 + sidx * 300
        body.extend(
            [
                f'<line x1="{lx}" y1="790" x2="{lx + 38}" y2="790" stroke="{color}" stroke-width="5"/>',
                text(lx + 50, 798, name, 20),
            ]
        )
    return finish(body)


def bar_chart(
    title: str,
    categories: list[str],
    series: dict[str, list[float]],
    y_max: float,
    y_step: float,
    y_label: str,
    *,
    source_note: str,
    stacked: bool = False,
) -> str:
    body = base(title, source_note)
    left, top, width, height = axes(
        body, y_max=y_max, y_step=y_step, y_label=y_label, categories=categories
    )
    colors = ["#2563eb", "#dc2626", "#f59e0b", "#059669"]
    n = len(categories)
    names = list(series)
    group_width = width / n
    bar_width = group_width * (0.65 if stacked else 0.78 / max(1, len(names)))
    for i, category in enumerate(categories):
        if stacked:
            cumulative = 0.0
            for sidx, name in enumerate(names):
                value = series[name][i]
                y0 = top + height - cumulative / y_max * height
                y1 = top + height - (cumulative + value) / y_max * height
                x = left + (i + 0.5) * group_width - bar_width / 2
                body.append(
                    f'<rect x="{x:.1f}" y="{y1:.1f}" width="{bar_width:.1f}" height="{y0 - y1:.1f}" fill="{colors[sidx]}" stroke="white" stroke-width="2"/>'
                )
                if value and y0 - y1 >= 24:
                    body.append(
                        text(
                            x + bar_width / 2,
                            (y0 + y1) / 2 + 6,
                            f"{value:g}",
                            16,
                            anchor="middle",
                            weight="700",
                            fill="white",
                        )
                    )
                cumulative += value
        else:
            for sidx, name in enumerate(names):
                value = series[name][i]
                x = left + i * group_width + group_width * 0.11 + sidx * bar_width
                y = top + height - value / y_max * height
                body.append(
                    f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar_width - 4:.1f}" height="{top + height - y:.1f}" fill="{colors[sidx]}"/>'
                )
                body.append(
                    text(
                        x + (bar_width - 4) / 2,
                        y - 8,
                        f"{value:g}",
                        16,
                        anchor="middle",
                    )
                )
    for sidx, name in enumerate(names):
        lx = 220 + sidx * 300
        body.extend(
            [
                f'<rect x="{lx}" y="780" width="30" height="22" fill="{colors[sidx]}"/>',
                text(lx + 42, 798, name, 20),
            ]
        )
    return finish(body)


def pie_chart(
    title: str,
    categories: list[str],
    values: list[float],
    y_label: str,
    *,
    source_note: str,
) -> str:
    body = base(title, source_note)
    cx, cy, radius = 470, 470, 240
    colors = ["#2563eb", "#dc2626", "#f59e0b", "#059669", "#9333ea", "#0891b2"]
    total = sum(values)
    angle = -math.pi / 2
    for i, value in enumerate(values):
        next_angle = angle + 2 * math.pi * value / total
        x1, y1 = cx + radius * math.cos(angle), cy + radius * math.sin(angle)
        x2, y2 = cx + radius * math.cos(next_angle), cy + radius * math.sin(next_angle)
        large = 1 if next_angle - angle > math.pi else 0
        path = f"M {cx} {cy} L {x1:.1f} {y1:.1f} A {radius} {radius} 0 {large} 1 {x2:.1f} {y2:.1f} Z"
        body.append(
            f'<path d="{path}" fill="{colors[i % len(colors)]}" stroke="white" stroke-width="3"/>'
        )
        angle = next_angle
    for i, (category, value) in enumerate(zip(categories, values)):
        y = 220 + i * 58
        body.extend(
            [
                f'<rect x="850" y="{y - 20}" width="28" height="28" fill="{colors[i % len(colors)]}"/>',
                text(895, y + 4, f"{category}: {value:g}{y_label}", 22),
            ]
        )
    return finish(body)


def table_chart(
    title: str,
    categories: list[str],
    series: dict[str, list[float]],
    y_label: str,
    *,
    source_note: str,
) -> str:
    body = base(title, source_note)
    x0, y0 = 140, 220
    col_w = 220
    row_h = 72
    body.append(text(150, 155, y_label, 22, weight="700"))
    headers = ["Category", *series.keys()]
    for j, header in enumerate(headers):
        x = x0 + j * col_w
        body.append(
            f'<rect x="{x}" y="{y0}" width="{col_w}" height="{row_h}" fill="#dbeafe" stroke="#1f2937" stroke-width="2"/>'
        )
        body.append(
            text(x + col_w / 2, y0 + 45, header, 22, anchor="middle", weight="700")
        )
    for i, category in enumerate(categories):
        y = y0 + (i + 1) * row_h
        for j, value in enumerate([category, *[series[name][i] for name in series]]):
            x = x0 + j * col_w
            body.append(
                f'<rect x="{x}" y="{y}" width="{col_w}" height="{row_h}" fill="white" stroke="#1f2937" stroke-width="2"/>'
            )
            body.append(text(x + col_w / 2, y + 45, value, 22, anchor="middle"))
    return finish(body)


CASES: list[dict[str, object]] = [
    {
        "id": "chart_01_population_line",
        "title": "Population of three countries, 2000–2020",
        "kind": "line_graph",
        "categories": ["2000", "2005", "2010", "2015", "2020"],
        "series": {
            "China (millions)": [1263, 1304, 1338, 1380, 1411],
            "India (millions)": [1058, 1155, 1243, 1328, 1403],
            "USA (millions)": [282, 296, 309, 322, 332],
        },
        "y_max": 1500,
        "y_step": 300,
        "y_label": "Population (millions)",
        "precision": "estimated",
        "source_type": "world_bank_data_rounded",
        "source": "World Bank indicator SP.POP.TOTL; selected values rounded to nearest million for a controlled benchmark.",
        "source_url": "https://api.worldbank.org/v2/country/CHN;IND;USA/indicator/SP.POP.TOTL?date=2000:2020&format=json",
        "raw_source_data": {
            "China (persons)": [
                1262645000,
                1303720000,
                1337705000,
                1379860000,
                1411100000,
            ],
            "India (persons)": [
                1057922733,
                1154676322,
                1243481564,
                1328024498,
                1402617695,
            ],
            "USA (persons)": [282162411, 295516599, 309378227, 321815121, 331578104],
        },
        "tolerance": 35,
    },
    {
        "id": "chart_02_life_expectancy_line",
        "title": "Life expectancy at birth, 1990–2020",
        "kind": "line_graph",
        "categories": ["1990", "2000", "2010", "2020"],
        "series": {
            "Japan (years)": [79, 81, 83, 85],
            "Brazil (years)": [66, 70, 74, 75],
            "South Africa (years)": [63, 58, 59, 65],
        },
        "y_max": 90,
        "y_step": 15,
        "y_label": "Years",
        "precision": "estimated",
        "source_type": "world_bank_data_rounded",
        "source": "World Bank indicator SP.DYN.LE00.IN; values rounded to whole years for a controlled benchmark.",
        "source_url": "https://api.worldbank.org/v2/country/JPN;BRA;ZAF/indicator/SP.DYN.LE00.IN?date=1990:2020&format=json",
        "raw_source_data": {
            "Japan (years)": [
                78.8370731707317,
                81.0760975609756,
                82.8426829268293,
                84.56,
            ],
            "Brazil (years)": [65.862, 69.584, 73.779, 74.506],
            "South Africa (years)": [62.942, 58.368, 58.886, 65.15],
        },
        "tolerance": 2,
    },
    {
        "id": "chart_03_internet_bar",
        "title": "Individuals using the Internet in 2020",
        "kind": "bar_chart",
        "categories": ["Canada", "Germany", "India", "Japan", "Brazil"],
        "series": {"Internet users (%)": [92, 90, 43, 90, 81]},
        "y_max": 100,
        "y_step": 20,
        "y_label": "Percent",
        "precision": "explicit",
        "source_type": "world_bank_data_rounded",
        "source": "World Bank indicator IT.NET.USER.ZS; displayed values rounded to whole percentages and printed on bars.",
        "source_url": "https://api.worldbank.org/v2/country/CAN;DEU;IND;JPN;BRA/indicator/IT.NET.USER.ZS?date=2020&format=json",
        "raw_source_data": {
            "Internet users (%)": [
                92.3,
                89.81294133,
                43.40544313,
                90.21945812,
                81.34269353,
            ]
        },
        "tolerance": 0,
    },
    {
        "id": "chart_04_gdp_bar",
        "title": "GDP per capita in selected countries, 2022",
        "kind": "bar_chart",
        "categories": ["Norway", "UK", "Mexico", "China", "Nigeria"],
        "series": {"GDP per capita (US$ thousands)": [113, 47, 11, 13, 3]},
        "y_max": 120,
        "y_step": 20,
        "y_label": "US$ thousands",
        "precision": "explicit",
        "source_type": "world_bank_data_rounded",
        "source": "World Bank indicator NY.GDP.PCAP.CD; rounded to the nearest thousand US dollars and printed on bars.",
        "source_url": "https://api.worldbank.org/v2/country/NOR;GBR;MEX;CHN;NGA/indicator/NY.GDP.PCAP.CD?date=2022&format=json",
        "raw_source_data": {
            "GDP per capita (US$)": [
                113122.130765691,
                47034.7795621476,
                11405.7940469896,
                12970.6056414327,
                2899.16047469267,
            ]
        },
        "tolerance": 1,
    },
    {
        "id": "chart_05_renewables_stacked",
        "title": "Electricity generation by source in 2021",
        "kind": "stacked_bar_chart",
        "categories": ["Canada", "Brazil", "Germany", "India"],
        "series": {
            "Hydro (%)": [45, 40, 20, 30],
            "Wind (%)": [25, 30, 30, 25],
            "Solar (%)": [15, 20, 25, 20],
            "Other (%)": [15, 10, 25, 25],
        },
        "y_max": 100,
        "y_step": 20,
        "y_label": "Share of generation (%)",
        "precision": "explicit",
        "source": "Controlled synthetic composition benchmark inspired by common energy-source categories; it is not a direct World Bank/IEA observation. Exact segment values are printed and sum to 100.",
        "source_url": "project://tests/fixtures/chart_benchmark (controlled fixture)",
        "source_type": "controlled_synthetic",
        "tolerance": 0,
    },
    {
        "id": "chart_06_transport_bar",
        "title": "Average daily travel by mode in 2019",
        "kind": "bar_chart",
        "categories": ["Car", "Bus", "Train", "Bicycle", "Walking"],
        "series": {"Minutes per day": [42, 18, 27, 12, 16]},
        "y_max": 50,
        "y_step": 10,
        "y_label": "Minutes",
        "precision": "explicit",
        "source_type": "controlled_synthetic",
        "source": "Controlled IELTS-style benchmark dataset created for repeatable vision testing; values are printed on bars.",
        "source_url": "project://tests/fixtures/chart_benchmark (controlled fixture)",
        "tolerance": 0,
    },
    {
        "id": "chart_07_household_pie",
        "title": "Household energy use by purpose in 2023",
        "kind": "pie_chart",
        "categories": ["Heating", "Water heating", "Appliances", "Lighting", "Cooling"],
        "series": {"Share (%)": [36, 21, 19, 9, 15]},
        "precision": "explicit",
        "source_type": "controlled_synthetic",
        "source": "Controlled IELTS-style benchmark dataset created for repeatable vision testing; exact percentages are printed in the legend.",
        "source_url": "project://tests/fixtures/chart_benchmark (controlled fixture)",
        "tolerance": 0,
    },
    {
        "id": "chart_08_exports_pie",
        "title": "Composition of manufactured exports in 2022",
        "kind": "pie_chart",
        "categories": ["Machinery", "Chemicals", "Textiles", "Food", "Other"],
        "series": {"Share (%)": [31, 24, 17, 13, 15]},
        "precision": "explicit",
        "source_type": "controlled_synthetic",
        "source": "Controlled IELTS-style benchmark dataset created for repeatable vision testing; exact percentages are printed in the legend.",
        "source_url": "project://tests/fixtures/chart_benchmark (controlled fixture)",
        "tolerance": 0,
    },
    {
        "id": "chart_09_water_table",
        "title": "Water consumption per person, 2010–2020",
        "kind": "table",
        "categories": ["2010", "2015", "2020"],
        "series": {
            "Urban (litres)": [180, 172, 165],
            "Rural (litres)": [130, 126, 121],
        },
        "precision": "explicit",
        "source_type": "controlled_synthetic",
        "source": "Controlled IELTS-style benchmark dataset created for repeatable vision testing; all table cells are explicit.",
        "source_url": "project://tests/fixtures/chart_benchmark (controlled fixture)",
        "tolerance": 0,
    },
    {
        "id": "chart_10_employment_line",
        "title": "Employment rate among adults, 2005–2025",
        "kind": "line_graph",
        "categories": ["2005", "2010", "2015", "2020", "2025"],
        "series": {
            "Country A (%)": [68, 71, 74, 70, 76],
            "Country B (%)": [62, 64, 67, 65, 69],
        },
        "y_max": 100,
        "y_step": 20,
        "y_label": "Employment rate (%)",
        "precision": "estimated",
        "source_type": "controlled_synthetic",
        "source": "Controlled IELTS-style benchmark dataset created for repeatable vision testing; plotted values are deliberately unlabeled to test uncertainty handling.",
        "source_url": "project://tests/fixtures/chart_benchmark (controlled fixture)",
        "tolerance": 4,
        "expected_uncertainty": True,
    },
]


def render(case: dict[str, Any]) -> str:
    kind = str(case["kind"])
    title = str(case["title"])
    categories = [str(value) for value in case["categories"]]  # type: ignore[index]
    raw_series = cast(dict[str, list[float]], case["series"])
    series = {str(k): [float(v) for v in values] for k, values in raw_series.items()}
    note = "Source: benchmark metadata; values are shown for controlled evaluation."
    if kind == "line_graph":
        return line_chart(
            title,
            categories,
            series,
            float(case["y_max"]),
            float(case["y_step"]),
            str(case["y_label"]),
            source_note=note,
        )
    if kind in {"bar_chart", "stacked_bar_chart"}:
        return bar_chart(
            title,
            categories,
            series,
            float(case["y_max"]),
            float(case["y_step"]),
            str(case["y_label"]),
            source_note=note,
            stacked=kind == "stacked_bar_chart",
        )
    if kind == "pie_chart":
        return pie_chart(
            title, categories, list(series.values())[0], "%", source_note=note
        )
    if kind == "table":
        return table_chart(title, categories, series, "Units", source_note=note)
    raise ValueError(f"unsupported chart kind: {kind}")


def main() -> None:
    SVG_DIR.mkdir(parents=True, exist_ok=True)
    IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    for case in CASES:
        case = cast(dict[str, Any], dict(case))
        case.setdefault("expected_uncertainty", case["precision"] == "estimated")
        series_data = cast(dict[str, object], case["series"])
        case["expected"] = {
            "chart_type": case["kind"],
            "categories": case["categories"],
            "series_names": list(series_data.keys()),
            "series": series_data,
            "precision": case["precision"],
            "tolerance": case["tolerance"],
            "expected_uncertainty": bool(case.get("expected_uncertainty")),
        }
        svg_path = SVG_DIR / f"{case['id']}.svg"
        svg_path.write_text(render(case), encoding="utf-8")
        (OUT / f"{case['id']}.json").write_text(
            json.dumps(case, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    manifest = {
        "name": "IELTS Academic Task 1 chart vision benchmark",
        "version": "1.0",
        "purpose": "Evaluate local Qwen chart structure, labels, trends, values and uncertainty handling.",
        "generated_by": "scripts/generate_chart_benchmark.py",
        "cases": [case["id"] for case in CASES],
    }
    (OUT / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )


if __name__ == "__main__":
    main()
