"""Prompt construction for one strict JSON criterion assessment."""

from __future__ import annotations

import json
import re
from typing import Any

from app.scoring.schemas import Criterion, ScoreRequest


def _explicit_chart_entries(chart_context: str) -> list[dict[str, Any]]:
    """Extract simple named-series percentage points from a chart description."""

    entries: list[dict[str, Any]] = []
    series_pattern = re.compile(
        r"([A-Za-z][A-Za-z -]*?):\s*((?:\d+(?:\.\d+)?%\s+in\s+\d{4}" r"(?:,\s*)?)+)",
        flags=re.IGNORECASE,
    )
    point_pattern = re.compile(r"(\d+(?:\.\d+)?)%\s+in\s+(\d{4})")
    for match in series_pattern.finditer(chart_context):
        series = match.group(1).strip()
        for value, year in point_pattern.findall(match.group(2)):
            entries.append(
                {"series": series, "year": int(year), "percent": float(value)}
            )
    return entries


def build_criterion_prompt(
    request: ScoreRequest,
    cleaned_essay: str,
    criterion: Criterion,
    rubric_context: dict[str, list[dict[str, Any]]],
    sample_context: list[dict[str, Any]],
    *,
    word_count: int | None = None,
) -> str:
    """Build a grounded prompt that asks Qwen for one criterion only."""

    rubric_json = json.dumps(rubric_context, ensure_ascii=False, indent=2)
    examples = "\n\n".join(
        f"Sample {index}: {row.get('text', '')[:1200]}"
        for index, row in enumerate(sample_context[:3], start=1)
    )
    chart = ""
    if request.task_type == "task1":
        entries = _explicit_chart_entries(request.chart_context or "")
        parsed_entries = (
            "Parsed explicit series/year/value entries (derived only from the "
            f"user's chart description): {json.dumps(entries, ensure_ascii=False)}\n"
            if entries
            else ""
        )
        chart = (
            f"\nChart type: {request.chart_type}\n"
            "The complete chart facts supplied by the user are delimited below. "
            "Treat these facts as the sole source of truth; do not assume an image "
            "is missing, infer typical patterns, or replace them with outside knowledge.\n"
            f"<CHART_CONTEXT>\n{request.chart_context}\n</CHART_CONTEXT>\n"
            f"{parsed_entries}"
        )
    minimum_words = 150 if request.task_type == "task1" else 250
    measured_word_count = (
        word_count if word_count is not None else len(cleaned_essay.split())
    )
    length_boundary = (
        "The essay is below the required minimum length. Treat all criterion "
        "bands as provisional diagnostics only: do not infer missing development, "
        "and do not award a high band merely because the task is mentioned."
        if measured_word_count < minimum_words
        else (
            "The essay meets the minimum word-count gate; still judge task "
            "fulfilment from substantive evidence."
        )
    )
    task_review_instruction = ""
    if criterion == "task_achievement":
        visual_guidance = ""
        chart_context = request.chart_context or ""
        if '"visual_type": "process"' in chart_context:
            visual_guidance = """
The supplied visual is a process diagram. Judge whether the response gives an
accurate overview, selects the main stages, preserves their order and any
branches/cycles, and avoids inventing stages or links. Do not expect numerical
data, axes, or comparisons that the process diagram does not show. Treat the
structured process_stages and next_steps as visual facts, subject to uncertainty.
"""
        elif '"visual_type": "map"' in chart_context:
            visual_guidance = """
The supplied visual is a map or map comparison. Judge whether the response
gives an accurate overview of the main spatial changes, locates salient
features correctly, and distinguishes unchanged, added, removed, replaced, or
expanded features only when supplied map facts support those claims. Do not
expect numerical data or chart trends. Treat structured map_features and their
before/after fields as visual facts, subject to uncertainty.
"""
        task_review_instruction = (
            """
Task Achievement checklist: include exactly these task_review check keys:
overview, key_feature_selection, data_accuracy, comparisons, visual_scope.
Judge an overview for the main trends/stages, select the salient features rather
than list every data point, check reported figures against the supplied chart
context, identify meaningful comparisons where the visual supports them, and
flag claims that go beyond the visual. Do not invent missing chart facts. Mark
each check and explain the evidence or omission.
Academic Task 1 does not require a conclusion paragraph. Never lower Task
Achievement or claim the response is unfinished merely because it lacks one;
judge its overview, feature selection, accuracy, comparisons, and coverage.
For data accuracy, report a mismatch only when a specific value or trend in the
essay conflicts with a specific value or trend stated inside <CHART_CONTEXT>.
Quote the exact essay wording and name the conflicting chart fact. Interpret
"rose from X to Y" as a start value of X and an end value of Y. Never attribute
a value to the wrong series or year. Do not infer unstated values, typical chart
patterns, or contradictions; if you cannot point to both conflicting statements,
mark the result met or not_verifiable rather than missing.
If chart context does not provide enough information to verify a check, mark it
not_verifiable instead of guessing.
"""
            + visual_guidance
            + """
When chart context contains image-derived values with precision "estimated", do
not treat small differences from those approximate readings as factual errors.
Use them to discuss broad trends only; mark exact-value accuracy not_verifiable
unless the visual provides a clearly readable, explicit value.
Keep each check explanation to one concise sentence (under 200 characters).
Use no more than two short evidence quotes, each under 120 characters.
"""
        )
    elif criterion == "task_response":
        task_review_instruction = """
Task Response checklist: include exactly these task_review check keys:
prompt_coverage, position, idea_development, support, relevance.
Break down every part of the question and judge whether the response actually
answers it; identify the writer's position where the prompt calls for one; assess
whether main ideas are explained and supported with relevant reasons or examples;
and flag repetition, unsupported assertions, or ideas that drift from the task.
Do not treat an essay roadmap (for example, saying what will be discussed) as
proof that the argument has been made. Judge only what the essay actually says.
Keep each check explanation to one concise sentence (under 200 characters).
Use no more than two short evidence quotes, each under 120 characters.
"""
    else:
        task_review_instruction = "Set task_review to null."
    completion_instruction = """
Submission assessment: assess only the response as submitted, following the
official criterion descriptors. Do not run a separate pre-submission check or
apply an extra truncation penalty. If the final text clearly ends mid-sentence,
with an unfinished clause, or in the middle of an undeveloped idea, explicitly
tell the user that the submitted essay appears unfinished and explain its actual
effect in the relevant criterion rationale/issues/improvements (for example,
grammar or coherence, or incomplete task development). A complete final
sentence with no conclusion paragraph is not by itself proof that the file was
cut off; Academic Task 1 does not require a conclusion paragraph. For Academic
Task 2, when a final clause is clearly unfinished and leaves an argument or
supporting idea incomplete, judge the resulting lack of development under Task
Response against the official descriptors, and reflect unfinished sentence
effects under Coherence and Cohesion or Grammar only where those descriptors
support it. Do not assign an otherwise fully developed Task Response assessment
without accounting for the missing development. Do not invent an unfinished
submission when the essay ends with a complete sentence. Do not conceal a clear
unfinished submission, and do not tell the user to resubmit; report the observed
issue as feedback.
"""
    return f"""You are an IELTS Academic Writing examiner.
Assess exactly one criterion: {criterion}.
Task type: Academic {request.task_type}.
Question: {request.question}{chart}

Official Academic rubric context (compare the essay against all supplied bands):
{rubric_json}

Retrieved Simon-style samples are examples of organisation and language only.
They are never part of the submitted essay and must never be quoted as essay
evidence. Do not use their reported scores as labels or as a scoring anchor:
{examples or "(no sample was retrieved)"}

Essay text begins (quote evidence only from inside these delimiters):
<ESSAY>
{cleaned_essay}
</ESSAY>

Length gate: {"below minimum" if measured_word_count < minimum_words else "minimum met"}.
Boundary instruction: {length_boundary}
{task_review_instruction}
{completion_instruction}

Return only valid JSON with exactly these fields:
{{"criterion":"{criterion}","band":7.0,"rationale":"...",
"evidence":[{{"quote":"exact text from essay or null","explanation":"..."}}],
"strengths":["..."],"issues":[{{"quote":"exact text from essay","explanation":"..."}}],
"improvements":["..."],"task_review":{{"checks":[
{{"key":"...","status":"met|partial|missing|not_verifiable",
"quote":"exact essay quote or null when absent","explanation":"..."}}
]}}}}
For non-task criteria task_review must be null. When task_review includes a quote,
it must be copied exactly from between <ESSAY> and </ESSAY>. Every evidence and
issue quote has the same restriction. If an exact quote cannot be verified, set
it to null and keep the explanation factual. Keep each quote to 3–10 consecutive words
copied character-for-character from the essay. Never paraphrase inside quotes.
Never quote question, rubric, examples, or
length instructions; use a null task-review quote if essay text does not support it.
Task-review status must be met, partial, missing, or not_verifiable; use
not_verifiable only when necessary task/chart information was not provided.
The band must be 0.0 to 9.0 in 0.5 increments. Do not add markdown or extra fields.
Keep rationale and each explanation concise. Return no more than two items in
evidence, issues, strengths, and improvements; quote only short exact excerpts.
"""
