"""Extract the official PDF tables into an Academic-only rubric JSON file.

The source PDFs intentionally contain both Academic and General Training
wording. This script keeps the Academic Task 1 text, the shared Task 2 text,
and the shared assessment guidance while removing General Training Task 1
letter descriptors.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

import pdfplumber  # type: ignore[import-not-found]

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

_BAND_SOURCE = "ielts-writing-band-descriptors.pdf"
_CRITERIA_SOURCE = "ielts-writing-key-assessment-criteria.pdf"
_SHARED_CRITERIA = (
    "task_achievement",
    "coherence_and_cohesion",
    "lexical_resource",
    "grammatical_range_and_accuracy",
)
_TASK_CRITERIA = {
    "task1": _SHARED_CRITERIA,
    "task2": (
        "task_response",
        "coherence_and_cohesion",
        "lexical_resource",
        "grammatical_range_and_accuracy",
    ),
}


def _normalize_cell(value: str) -> str:
    """Join PDF line wraps and repair known extraction-only word joins."""

    text = re.sub(r"\s+", " ", value).strip()
    replacements = {
        "Organisationis": "Organisation is",
        "theappropriacy": "the appropriacy",
        "orunrelated": "or unrelated",
        "e.g.memorisedphrases": "e.g. memorised phrases",
        "mayimpede": "may impede",
        "memorisedlanguage": "memorised language",
        "skilfullymanaged": "skilfully managed",
        "skilfuluse": "skilful use",
        "inappropriaciesoccur": "inappropriacies occur",
        "over-generaliseor": "over-generalise or",
        "recognisablestrings": "recognisable strings",
        "organisationalfeatures": "organisational features",
        "beconfused": "be confused",
        " –there": " – there",
        ".There": ". There",
        ".The": ". The",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    return text


def _academic_task1_achievement(text: str, band: int) -> str:
    """Remove General Training Task 1 wording from one descriptor cell."""

    text = _normalize_cell(text)
    if band == 8:
        text = re.sub(
            r"\(General Training\) All bullet points are clearly presented, "
            r"and appropriately illustrated or extended\. ",
            "",
            text,
        )
    elif band == 7:
        text = re.sub(
            r" \(General Training\) All bullet points are covered.*$", "", text
        )
    elif band == 6:
        text = re.sub(
            r" \(General Training\) All bullet points are covered and adequately "
            r"highlighted\. The purpose is generally clear\. There may be minor "
            r"inconsistencies in tone\. ",
            " ",
            text,
        )
    elif band == 5:
        text = re.sub(
            r" \(General Training\) All bullet points are presented but one or more "
            r"may not be adequately covered\. The purpose may be unclear at times\. "
            r"The tone may be variable and sometimes inappropriate\. ",
            " ",
            text,
        )
    elif band == 4:
        text = re.sub(
            r" \(General Training\).*?The tone may be inappropriate\. ",
            " ",
            text,
        )
    text = text.replace("(Academic) ", "")
    text = text.replace("Key features/bullet points", "Key features")
    if "General Training" in text or "bullet points" in text or "letter" in text:
        raise ValueError(f"Task 1 Band {band} 仍包含 General Training 文字: {text}")
    return text


def _table_rows(pdf: Any, pages: range) -> list[tuple[int, int, list[str | None]]]:
    """Read descriptor rows and return (page, band, cells)."""

    rows: list[tuple[int, int, list[str | None]]] = []
    for page_index in pages:
        page = pdf.pages[page_index]
        tables = page.extract_tables()
        if not tables:
            continue
        for row in tables[0][1:]:
            if not row or not row[0] or not str(row[0]).strip().isdigit():
                continue
            rows.append((page_index + 1, int(str(row[0]).strip()), row[1:]))
    return rows


def _descriptor_records(band_pdf: Path) -> list[dict[str, Any]]:
    """Extract and clean all 80 Academic criterion descriptors."""

    descriptors: list[dict[str, Any]] = []
    with pdfplumber.open(band_pdf) as pdf:
        task_rows = {
            "task1": _table_rows(pdf, range(2, 5)),
            "task2": _table_rows(pdf, range(6, 9)),
        }
        for task_type, rows in task_rows.items():
            for source_page, band, cells in rows:
                if band == 0:
                    cells = [cells[0], cells[0], cells[0], cells[0]]
                for index, criterion in enumerate(_TASK_CRITERIA[task_type]):
                    cell = cells[index]
                    if not cell:
                        raise ValueError(f"{task_type} Band {band} 缺少 {criterion}")
                    text = (
                        _academic_task1_achievement(cell, band)
                        if task_type == "task1" and criterion == "task_achievement"
                        else _normalize_cell(cell)
                    )
                    descriptors.append(
                        {
                            "id": f"academic_{task_type}_{criterion}_band_{band}",
                            "task_type": task_type,
                            "criterion": criterion,
                            "band": band,
                            "text": text,
                            "source_file": _BAND_SOURCE,
                            "source_page": source_page,
                        }
                    )
    return descriptors


def _guidance_records() -> list[dict[str, Any]]:
    """Return operational criteria from the official key-criteria PDF."""

    source = _CRITERIA_SOURCE
    return [
        {
            "id": "academic_task1_task_achievement_guidance",
            "scope": "academic_task1",
            "task_type": "task1",
            "criterion": "task_achievement",
            "points": [
                "Academic Task 1 is an information-transfer task based on a diagram, graph, "
                "table, chart, map or other visual input.",
                "Select the key features of the information.",
                "Provide sufficient detail to illustrate the key features.",
                "Report information, figures and trends accurately.",
                "Compare or contrast identifiable trends, principal changes or differences "
                "instead of mechanically listing details.",
                "Use an appropriate response format.",
            ],
            "source_file": source,
            "source_page": 2,
        },
        {
            "id": "academic_task2_task_response_guidance",
            "scope": "academic_task2",
            "task_type": "task2",
            "criterion": "task_response",
            "points": [
                "Formulate and develop a position in relation to the given question or statement.",
                "Use at least 250 words.",
                "Support ideas with evidence; examples may come from the candidate's own "
                "experience.",
                "Respond fully and relevantly to the task.",
                "Extend and support the main ideas adequately.",
                "Open the discourse, establish a position and formulate conclusions clearly.",
                "Use an appropriate response format.",
            ],
            "source_file": source,
            "source_page": 2,
        },
        {
            "id": "academic_task1_word_count_guidance",
            "scope": "academic_task1",
            "task_type": "task1",
            "criterion": "task_achievement",
            "points": ["Use a minimum of 150 words for Writing Task 1."],
            "source_file": source,
            "source_page": 1,
        },
        {
            "id": "academic_task2_weight_guidance",
            "scope": "academic_task2",
            "task_type": "task2",
            "criterion": "task_response",
            "points": ["Task 2 carries more weight in marking than Task 1."],
            "source_file": source,
            "source_page": 1,
        },
        {
            "id": "academic_shared_coherence_and_cohesion_guidance",
            "scope": "academic_shared",
            "task_type": None,
            "criterion": "coherence_and_cohesion",
            "points": [
                "Organise information and ideas logically or develop the argument logically.",
                "Use paragraphing appropriately for topic organisation and presentation.",
                "Sequence ideas and information logically within and across paragraphs.",
                "Use reference and substitution flexibly.",
                "Use discourse markers to show stages and relationships between ideas or "
                "information.",
            ],
            "source_file": source,
            "source_page": 3,
        },
        {
            "id": "academic_shared_lexical_resource_guidance",
            "scope": "academic_shared",
            "task_type": None,
            "criterion": "lexical_resource",
            "points": [
                "Use a range of general words and synonyms to avoid repetition.",
                "Use adequate and appropriate topic-specific vocabulary and indicators of "
                "attitude.",
                "Choose words and expressions precisely.",
                "Control collocations, idiomatic expressions and sophisticated phrasing.",
                "Consider the density and communicative effect of spelling and word-formation "
                "errors.",
            ],
            "source_file": source,
            "source_page": 4,
        },
        {
            "id": "academic_shared_grammar_guidance",
            "scope": "academic_shared",
            "task_type": None,
            "criterion": "grammatical_range_and_accuracy",
            "points": [
                "Use an appropriate range of simple, compound and complex structures.",
                "Use simple, compound and complex sentences accurately.",
                "Consider the density and communicative effect of grammatical errors.",
                "Use punctuation accurately and appropriately.",
            ],
            "source_file": source,
            "source_page": 4,
        },
        {
            "id": "academic_shared_response_integrity_guidance",
            "scope": "academic_shared",
            "task_type": None,
            "criterion": None,
            "points": [
                "Each task is assessed independently.",
                "Scripts may be penalised if partly or wholly plagiarised.",
                "Scripts should be written as full, connected text rather than bullet points "
                "or note form.",
            ],
            "source_file": source,
            "source_page": 1,
        },
    ]


def extract(band_pdf: Path, criteria_pdf: Path, output: Path) -> None:
    """Extract, filter and write the checked-in Academic rubric JSON."""

    # Open the criteria PDF here so a missing or unreadable source fails before
    # the output file is replaced. Guidance is curated from its official pages.
    with pdfplumber.open(criteria_pdf) as pdf:
        if len(pdf.pages) < 4:
            raise ValueError("评分关键标准 PDF 页数不足，无法确认来源")
    payload = {
        "schema_version": "1.0",
        "exam_type": "academic",
        "source_version": "Updated May 2023",
        "sources": [
            {
                "file": _BAND_SOURCE,
                "scope": (
                    "Task 1 and Task 2 Band 0-9 descriptors; mixed Academic and "
                    "General Training source"
                ),
            },
            {
                "file": _CRITERIA_SOURCE,
                "scope": "Key assessment criteria; mixed Academic and General Training source",
            },
        ],
        "policy": {
            "task1_minimum_words": 150,
            "task2_minimum_words": 250,
            "task2_weight": "higher_than_task1",
            "task1_criterion": "task_achievement",
            "task2_criterion": "task_response",
            "shared_criteria": [
                "coherence_and_cohesion",
                "lexical_resource",
                "grammatical_range_and_accuracy",
            ],
            "academic_task1_only": True,
            "general_training_task1_included": False,
        },
        "descriptors": _descriptor_records(band_pdf),
        "guidance": _guidance_records(),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def main() -> int:
    """Parse paths and generate the Academic rubric JSON."""

    parser = argparse.ArgumentParser(description="提取 IELTS Academic 评分标准")
    parser.add_argument("--band-descriptors", type=Path, required=True)
    parser.add_argument("--key-criteria", type=Path, required=True)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("docs/rubrics/academic_writing_rubric.json"),
    )
    args = parser.parse_args()
    extract(args.band_descriptors, args.key_criteria, args.output)
    print(f"已生成 Academic rubric: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
