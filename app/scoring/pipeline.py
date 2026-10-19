"""Pure Python scoring pipeline ready to be placed inside a LangGraph."""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Callable, Protocol

from pydantic import ValidationError

from app.rag.corpus_loader import TaskType
from app.rubric.indexing import RubricVectorStore, retrieve_rubric_context
from app.scoring.prompts import build_criterion_prompt
from app.scoring.schemas import (
    Criterion,
    CriterionResult,
    ScoreReport,
    ScoreRequest,
    EstimateStatus,
    ChartStructure,
    ChartSeries,
    ChartUnderstanding,
    ChartValueExtraction,
    QuestionImageUnderstanding,
    expected_criteria,
)


class ScoringPipelineError(RuntimeError):
    """Raised when a complete, trustworthy report cannot be produced."""


@dataclass(frozen=True)
class ScoringPreparation:
    """Validated essay input and retrieval context shared by workflow nodes."""

    request: ScoreRequest
    cleaned_essay: str
    word_count: int
    minimum_word_count: int
    chart_understanding: ChartUnderstanding | None
    warnings: list[str]
    samples: list[dict[str, Any]]
    contexts: dict[Criterion, dict[str, list[dict[str, Any]]]]


class JsonGeneratingModel(Protocol):
    """Model interface supporting Ollama's JSON response format."""

    def generate(
        self,
        prompt: str,
        *,
        response_format: str | dict[str, Any] | None = None,
        images: list[str] | None = None,
    ) -> str:
        """Generate text and optionally request JSON from the local model."""


class SampleSearcher(Protocol):
    """Subset of the existing AcademicRetriever used by scoring."""

    def search(
        self,
        query: str,
        task_type: TaskType,
        *,
        chart_type: str | None = None,
        top_k: int | None = None,
    ) -> list[dict[str, Any]]:
        """Return same-task Academic examples."""


def count_words(text: str) -> int:
    """Count English words in a stable way for IELTS minimum-word warnings."""

    return len(re.findall(r"\b[A-Za-z]+(?:['’-][A-Za-z]+)*\b", text))


def round_to_half_band(value: float) -> float:
    """Round to the nearest 0.5 using IELTS-style half-up tie handling."""

    rounded = (Decimal(str(value)) * 2).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return float(rounded / Decimal("2"))


class ScoringPipeline:
    """Run four serial, structured criterion assessments with no partial report."""

    def __init__(
        self,
        model: JsonGeneratingModel,
        rubric_store: RubricVectorStore,
        sample_searcher: SampleSearcher | None = None,
        *,
        rubric_version: str = "Updated May 2023",
    ) -> None:
        self.model = model
        self.rubric_store = rubric_store
        self.sample_searcher = sample_searcher
        self.rubric_version = rubric_version

    def score(self, request: ScoreRequest | dict[str, Any]) -> ScoreReport:
        """Validate input, score all criteria, and return a complete report."""
        start = time.perf_counter()
        preparation = self.prepare(request)
        results: list[CriterionResult] = []
        for criterion in expected_criteria(preparation.request.task_type):
            results.append(self.score_criterion(preparation, criterion))
        return self.build_report(preparation, results, start_time=start)

    def prepare(self, request: ScoreRequest | dict[str, Any]) -> ScoringPreparation:
        """Validate input and retrieve all context needed by criterion nodes."""

        try:
            validated_request = (
                request
                if isinstance(request, ScoreRequest)
                else ScoreRequest.model_validate(request)
            )
        except ValidationError as exc:
            raise ScoringPipelineError(f"评分输入无效: {exc}") from exc

        cleaned_essay = re.sub(r"\s+", " ", validated_request.essay).strip()
        word_count = count_words(cleaned_essay)
        warnings = self._word_count_warnings(validated_request.task_type, word_count)
        chart_understanding = None
        if validated_request.chart_image_base64:
            chart_understanding = self._understand_chart_image(
                validated_request.chart_image_base64
            )
            chart_facts = chart_understanding.model_dump_json(indent=2)
            chart_context = (
                "Structured visual reading from the uploaded Task 1 image. "
                "Uncertain values are listed separately and must not be treated "
                "as established facts:\n" + chart_facts
            )
            if validated_request.chart_context:
                chart_context += (
                    "\nAdditional user-provided chart description:\n"
                    + validated_request.chart_context
                )
            validated_request = validated_request.model_copy(
                update={"chart_context": chart_context}
            )
            estimated_points = [
                f"{series.name}/{point.label}"
                for series in chart_understanding.series
                for point in series.points
                if point.precision == "estimated"
            ]
            if chart_understanding.uncertain_or_unreadable or estimated_points:
                warnings.append(
                    "题目图片中有无法可靠辨认的信息；请先核对报告的 "
                    "chart_understanding，估读值或模糊内容不得作为精确事实。"
                )
        query = " ".join(
            part
            for part in (
                validated_request.question,
                validated_request.chart_context,
                cleaned_essay,
            )
            if part
        )
        samples = self._retrieve_samples(validated_request, query)
        contexts = {
            criterion: retrieve_rubric_context(
                self.rubric_store, validated_request.task_type, criterion
            )
            for criterion in expected_criteria(validated_request.task_type)
        }
        return ScoringPreparation(
            request=validated_request,
            cleaned_essay=cleaned_essay,
            word_count=word_count,
            minimum_word_count=(150 if validated_request.task_type == "task1" else 250),
            chart_understanding=chart_understanding,
            warnings=warnings,
            samples=samples,
            contexts=contexts,
        )

    def score_criterion(
        self, preparation: ScoringPreparation, criterion: Criterion
    ) -> CriterionResult:
        """Score one criterion using already prepared retrieval context."""

        if criterion not in expected_criteria(preparation.request.task_type):
            raise ScoringPipelineError(
                f"{preparation.request.task_type} 不支持评分维度: {criterion}"
            )
        return self._score_criterion(
            preparation.request,
            preparation.cleaned_essay,
            criterion,
            preparation.contexts[criterion],
            preparation.samples,
        )

    def build_report(
        self,
        preparation: ScoringPreparation,
        results: list[CriterionResult],
        *,
        start_time: float,
    ) -> ScoreReport:
        """Aggregate four validated criterion results into one complete report."""

        estimate = (
            round_to_half_band(sum(result.band for result in results) / len(results))
            if preparation.word_count >= preparation.minimum_word_count
            else None
        )
        estimate_status: EstimateStatus = (
            "reliable"
            if preparation.word_count >= preparation.minimum_word_count
            else "unreliable_under_minimum_words"
        )
        elapsed_ms = int((time.perf_counter() - start_time) * 1000)
        try:
            return ScoreReport(
                task_type=preparation.request.task_type,
                task_criterion=(
                    "task_achievement"
                    if preparation.request.task_type == "task1"
                    else "task_response"
                ),
                word_count=preparation.word_count,
                minimum_word_count=preparation.minimum_word_count,
                criterion_results=results,
                essay_band_estimate=estimate,
                estimate_status=estimate_status,
                warnings=preparation.warnings,
                chart_understanding=preparation.chart_understanding,
                processing_time_ms=elapsed_ms,
                rubric_version=self.rubric_version,
            )
        except ValidationError as exc:
            raise ScoringPipelineError(f"评分结果汇总失败: {exc}") from exc

    def _retrieve_samples(
        self, request: ScoreRequest, query: str
    ) -> list[dict[str, Any]]:
        if self.sample_searcher is None:
            return []
        return self.sample_searcher.search(
            query,
            request.task_type,
            chart_type=request.chart_type if request.task_type == "task1" else None,
            top_k=3,
        )

    def _understand_chart_image(self, image_base64: str) -> ChartUnderstanding:
        """Classify Task 1 visuals, then extract chart, process, or map facts."""

        structure_prompt = """Inspect this IELTS Academic Writing Task 1 image in a
structure-only pass. Classify visual_type as exactly chart, process, or map.
Return chart_type, title, x_axis, y_axis, categories, series_names,
has_explicit_data_labels, process_stages, and map_features. For charts, identify
the labels and series but do not read plotted values. Set
has_explicit_data_labels true only when numeric values are printed beside marks,
not when numbers appear only as axis ticks. Read all legend entries. For a
process diagram, list every visible stage in the direction indicated by arrows;
use order starting at 0 and put the exact destination labels in next_steps,
including branches and loops. For a map, list salient locations and changes;
record before/after use where shown, compass direction only when supported by a
compass or clear map orientation, and classify additions/removals/moves where
possible. Do not infer unstated changes. Do not invent unreadable text; report
uncertain items only if the schema permits. Return JSON matching the schema."""
        structure_schema = ChartStructure.model_json_schema()
        try:
            structure = self._generate_chart_response(
                structure_prompt,
                structure_schema,
                image_base64,
                ChartStructure.model_validate_json,
            )
            # Qwen may follow the richer output fields but omit the classifier
            # label. Recover only from unambiguous process/map fields or a
            # clearly named visual type; otherwise leave it as a chart.
            chart_type_label = structure.chart_type.casefold()
            if any(token in chart_type_label for token in ("process", "flowchart")):
                structure.visual_type = "process"
            elif any(token in chart_type_label for token in ("map", "layout")):
                structure.visual_type = "map"
            elif structure.process_stages and not structure.map_features:
                structure.visual_type = "process"
            elif structure.map_features and not structure.process_stages:
                structure.visual_type = "map"
            if structure.visual_type == "process":
                stages = sorted(structure.process_stages, key=lambda item: item.order)
                missing = not stages
                return ChartUnderstanding(
                    visual_type="process",
                    chart_type=structure.chart_type,
                    chart_summary=(
                        f"Process diagram showing {len(stages)} identified stages."
                    ),
                    process_stages=stages,
                    uncertain_or_unreadable=(
                        ["No process stages could be read reliably."] if missing else []
                    ),
                )
            if structure.visual_type == "map":
                features = structure.map_features
                missing = not features
                return ChartUnderstanding(
                    visual_type="map",
                    chart_type=structure.chart_type,
                    chart_summary=(
                        f"Map comparison with {len(features)} identified locations or changes."
                    ),
                    map_features=features,
                    uncertain_or_unreadable=(
                        ["No map locations or changes could be read reliably."]
                        if missing
                        else []
                    ),
                )
            if not structure.series_names and any(
                token in chart_type_label for token in ("process", "flowchart")
            ):
                raise ValueError("流程图类型已识别，但未能提取步骤顺序")
            if not structure.series_names:
                raise ValueError("未能识别图表图例中的数据系列")

            structure_facts = structure.model_dump_json(indent=2)
            value_prompt = f"""Read this IELTS Academic Task 1 chart image and
return the supplied ChartUnderstanding JSON schema. The chart structure was
already transcribed in a separate pass; use it as the label key:
{structure_facts}

Preserve every series name from series_names exactly once. Do not add another
series. Put the visible category/year labels in axes_or_categories. A point
label must match one of the structure categories exactly; do not create
intermediate years. For line charts, read up to six useful labeled categories
per series (include the first and last, plus major turning points or
crossovers). Values printed on the chart are precision "explicit"; values
estimated from a plotted position are precision "estimated". The structure
pass says data labels are explicitly printed:
{structure.has_explicit_data_labels}. If false, every plotted numeric value
must be marked "estimated", even when it lies on an axis tick. Do not leave all
line-chart point lists empty when plotted values are visible. For stacked bars,
estimate segment values only when segment boundaries can be associated with
the value axis; otherwise leave points empty and clearly state that segment
values are not reliably readable. Put all numeric readings only in points,
never in chart_summary. Keep chart_summary to one short, number-free sentence
describing the visual and overall trend. Add estimated readings to
uncertain_or_unreadable as estimates, not facts. Omit doubtful points and
describe the uncertainty. Return JSON only."""
            understanding = self._generate_chart_response(
                value_prompt,
                ChartUnderstanding.model_json_schema(),
                image_base64,
                ChartUnderstanding.model_validate_json,
            )
            understanding = self._fill_missing_line_values(
                understanding, structure, image_base64
            )
            if not structure.has_explicit_data_labels:
                for series in understanding.series:
                    for point in series.points:
                        point.precision = "estimated"
        except Exception as exc:
            raise ScoringPipelineError(
                f"本地 Qwen 无法读取 Task 1 图表图片: {exc}"
            ) from exc
        reconciled = self._reconcile_chart_structure(understanding, structure)
        return self._summarize_chart(reconciled, structure)

    def _understand_question_image(
        self, image_base64: str, task_type: TaskType
    ) -> QuestionImageUnderstanding:
        """Read the complete IELTS prompt from a photographed question sheet."""

        prompt = f"""Read the IELTS Academic Writing {task_type} question in this image.
Transcribe the complete question text exactly enough for an essay scorer to use it.
Include all instructions, bullet points, labels, years, units, and answer
requirements that are visible. Do not answer the question and do not describe
the picture. If any words are blurred or cut off, list them in
uncertain_or_unreadable and do not invent replacements. Return JSON only using
the QuestionImageUnderstanding schema."""
        try:
            return self._generate_chart_response(
                prompt,
                QuestionImageUnderstanding.model_json_schema(),
                image_base64,
                QuestionImageUnderstanding.model_validate_json,
            )
        except Exception as exc:
            raise ScoringPipelineError(
                f"本地 Qwen 无法读取 Academic {task_type} 题目图片: {exc}"
            ) from exc

    def _generate_chart_response(
        self,
        prompt: str,
        response_format: dict[str, Any],
        image_base64: str,
        validator: Callable[[str], Any],
    ) -> Any:
        """Generate and validate chart JSON, retrying once with a compact request."""

        last_error: Exception | None = None
        for attempt in range(2):
            retry_suffix = ""
            if attempt:
                retry_suffix = (
                    "\nThe previous JSON was invalid or truncated. "
                    "Return compact valid JSON now. "
                    "Keep required fields, limit uncertainty items to 8, and add no commentary."
                )
            try:
                raw = self.model.generate(
                    prompt + retry_suffix,
                    response_format=response_format,
                    images=[image_base64],
                )
                if "```" in raw:
                    raise ValueError("读图结果包含 Markdown 代码块")
                return validator(raw)
            except Exception as exc:  # retry once; the caller adds the final context
                last_error = exc
        raise ValueError(f"结构化读图 JSON 无法解析: {last_error}") from last_error

    def _fill_missing_line_values(
        self,
        understanding: ChartUnderstanding,
        structure: ChartStructure,
        image_base64: str,
    ) -> ChartUnderstanding:
        """Make one compact retry when a line-series has no extracted points."""

        if "line" not in structure.chart_type.casefold():
            return understanding
        missing = [series.name for series in understanding.series if not series.points]
        if not missing:
            return understanding
        prompt = f"""Read the plotted values from this chart image for these
line-series only: {json.dumps(missing)}. The valid category labels are
{json.dumps(structure.categories)}. Return compact JSON matching the schema:
include the first and last visible labeled category for every named series,
and include a midpoint only if it is a clear turning point or crossover. Do
not invent categories or values. If no values are printed beside the data,
mark every plotted reading as estimated and say so in
uncertain_or_unreadable. Return no chart summary."""
        try:
            raw = self.model.generate(
                prompt,
                response_format=ChartValueExtraction.model_json_schema(),
                images=[image_base64],
            )
            if "```" in raw:
                return understanding
            extracted = ChartValueExtraction.model_validate_json(raw)
        except Exception:
            return understanding
        points_by_name = {
            series.name.casefold().strip(): series.points for series in extracted.series
        }
        for series in understanding.series:
            if not series.points:
                series.points = points_by_name.get(series.name.casefold().strip(), [])
        understanding.uncertain_or_unreadable.extend(extracted.uncertain_or_unreadable)
        return understanding

    @staticmethod
    def _reconcile_chart_structure(
        understanding: ChartUnderstanding, structure: ChartStructure
    ) -> ChartUnderstanding:
        """Keep value extraction aligned with the independently read legend."""

        uncertainty = list(understanding.uncertain_or_unreadable)
        categories = structure.categories or understanding.axes_or_categories
        allowed_categories = {item.casefold().strip() for item in categories}
        series_by_name = {
            series.name.casefold().strip(): series for series in understanding.series
        }
        reconciled = []
        for name in structure.series_names:
            series = series_by_name.get(name.casefold().strip())
            if series is None:
                series = next(
                    (
                        candidate
                        for key, candidate in series_by_name.items()
                        if key in name.casefold() or name.casefold() in key
                    ),
                    None,
                )
            if series is None:
                reconciled.append(ChartSeries(name=name, points=[]))
                uncertainty.append(f"图例可识别到“{name}”，但无法可靠读取其数据点。")
                continue
            series.name = name
            if allowed_categories:
                invalid_points = [
                    point.label
                    for point in series.points
                    if point.label.casefold().strip() not in allowed_categories
                ]
                if invalid_points:
                    series.points = [
                        point
                        for point in series.points
                        if point.label.casefold().strip() in allowed_categories
                    ]
                    uncertainty.append(
                        f"已忽略不匹配图表类别标签的数据点：{', '.join(invalid_points)}。"
                    )
                category_order = {
                    category.casefold().strip(): index
                    for index, category in enumerate(categories)
                }
                series.points.sort(
                    key=lambda point: category_order[point.label.casefold().strip()]
                )
            reconciled.append(series)

        unexpected = [
            series.name
            for series in understanding.series
            if not any(
                series.name.casefold().strip() == expected.casefold().strip()
                or series.name.casefold().strip() in expected.casefold()
                or expected.casefold() in series.name.casefold().strip()
                for expected in structure.series_names
            )
        ]
        if unexpected:
            uncertainty.append(
                f"模型额外输出了无法与图例核对的数据系列，已移除：{', '.join(unexpected)}。"
            )
        return understanding.model_copy(
            update={
                "axes_or_categories": categories,
                "series": reconciled,
                "uncertain_or_unreadable": list(dict.fromkeys(uncertainty))[:20],
            }
        )

    @staticmethod
    def _summarize_chart(
        understanding: ChartUnderstanding, structure: ChartStructure
    ) -> ChartUnderstanding:
        """Build a short summary from reconciled labels and point direction."""

        trends: list[str] = []
        categories_are_time = bool(structure.categories) and all(
            re.fullmatch(r"\d{4}", category.strip())
            for category in structure.categories
        )
        if categories_are_time:
            for series in understanding.series:
                if not series.points:
                    continue
                first = series.points[0]
                last = series.points[-1]
                if first.value < last.value:
                    direction = "rising overall"
                elif first.value > last.value:
                    direction = "falling overall"
                else:
                    direction = "remaining broadly stable"
                series.trend = f"{direction} (estimated)"
                trends.append(f"{series.name} {direction}")

        chart_type = structure.chart_type.replace("_", " ")
        safe_model_sentence = next(
            (
                sentence.strip()
                for sentence in re.split(r"(?<=[.!?])\s+", understanding.chart_summary)
                if sentence.strip()
                and not re.search(r"\d", sentence)
                and not re.search(
                    r"\b(rising|falling|stable|increase|decrease|trend|estimate)\b",
                    sentence,
                    re.IGNORECASE,
                )
            ),
            "",
        )
        if trends:
            summary = f"{chart_type.title()} with {len(understanding.series)} series."
            if safe_model_sentence:
                summary += f" {safe_model_sentence}"
            summary += f" Visual estimates suggest {'; '.join(trends)}."
            if any(
                point.precision == "estimated"
                for series in understanding.series
                for point in series.points
            ):
                uncertainty = list(understanding.uncertain_or_unreadable)
                uncertainty.append(
                    "All listed plotted values are visual estimates, not printed data labels."
                )
                understanding.uncertain_or_unreadable = list(
                    dict.fromkeys(uncertainty)
                )[:20]
        else:
            has_points = any(series.points for series in understanding.series)
            if safe_model_sentence:
                summary = safe_model_sentence
            elif "pie" in chart_type.casefold() and has_points:
                summary = (
                    "Pie chart showing proportions across "
                    f"{len(understanding.axes_or_categories)} categories."
                )
            elif has_points:
                summary = (
                    f"{chart_type.title()} comparing "
                    f"{len(understanding.axes_or_categories)} categories across "
                    f"{len(understanding.series)} series; values were transcribed."
                )
            else:
                summary = (
                    f"{chart_type.title()} comparing "
                    f"{len(understanding.axes_or_categories)} categories across "
                    f"{len(understanding.series)} series; plotted values "
                    "were not reliably transcribed."
                )
        understanding.chart_summary = summary[:400]
        return understanding.model_copy(update={"chart_type": structure.chart_type})

    def _score_criterion(
        self,
        request: ScoreRequest,
        cleaned_essay: str,
        criterion: Criterion,
        context: dict[str, list[dict[str, Any]]],
        samples: list[dict[str, Any]],
    ) -> CriterionResult:
        prompt = build_criterion_prompt(
            request,
            cleaned_essay,
            criterion,
            context,
            # Keep retrieved exemplars out of the scoring prompt until the
            # response schema can represent them as separately attributed
            # references. Otherwise the model can mistake sample text for
            # candidate evidence and the strict evidence check rightly fails.
            [],
            word_count=count_words(cleaned_essay),
        )
        try:
            response_schema = self._response_schema(criterion)
            first_response = self.model.generate(
                prompt, response_format=response_schema
            )
        except Exception as exc:
            raise ScoringPipelineError(
                f"{criterion} 调用本地评分模型失败；未生成部分报告: {exc}"
            ) from exc
        try:
            return self._parse_result(first_response, criterion, cleaned_essay)
        except (ValidationError, ValueError, TypeError) as first_error:
            repair_prompt = (
                "Repair the following invalid JSON into this exact schema for "
                f"criterion {criterion}. Return JSON only, no markdown. "
                "Use quote and explanation objects for both evidence and issues; "
                "never use a text field.\n"
                '{"criterion":"...","band":7.0,"rationale":"...",'
                '"evidence":[{"quote":"exact essay text or null",'
                '"explanation":"..."}],"strengths":["..."],'
                '"issues":[{"quote":"exact essay text or null",'
                '"explanation":"..."}],"improvements":["..."],'
                '"task_review":null or {"checks":[...]} }\n'
                "For task_review, preserve the task-specific checklist and use only "
                "the required keys. Every non-null task_review quote must be an "
                "exact substring of the essay text below; if you cannot quote the "
                "essay itself, set quote to null. Never quote the question, rubric, "
                "word-count note, or other prompt instructions. For evidence and "
                "issues, quote only 3-10 consecutive words copied exactly from "
                "the essay; never paraphrase a quote.\n"
                f"Essay text:\n{cleaned_essay}\n"
                "Do not include empty strings in strengths or improvements.\n"
                f"Validation error: {first_error}\nInvalid output:\n{first_response}"
            )
            try:
                repaired_response = self.model.generate(
                    repair_prompt, response_format=response_schema
                )
            except Exception as exc:
                raise ScoringPipelineError(
                    f"{criterion} JSON 修复请求失败；未生成部分报告: {exc}"
                ) from exc
            try:
                return self._parse_result(repaired_response, criterion, cleaned_essay)
            except (ValidationError, ValueError, TypeError) as second_error:
                raise ScoringPipelineError(
                    f"{criterion} 评分结果无法通过严格 JSON 校验；未生成部分报告: "
                    f"{second_error}"
                ) from second_error

    @staticmethod
    def _response_schema(criterion: Criterion) -> dict[str, Any]:
        """Return an Ollama JSON Schema locked to the requested criterion."""

        schema = CriterionResult.model_json_schema()
        properties = schema.get("properties", {})
        criterion_schema = properties.get("criterion")
        if isinstance(criterion_schema, dict):
            criterion_schema.pop("enum", None)
            criterion_schema["const"] = criterion
        return schema

    @staticmethod
    def _parse_result(raw: str, criterion: Criterion, essay: str) -> CriterionResult:
        if "```" in raw:
            raise ValueError("评分模型返回了 Markdown 代码块")
        payload = json.loads(raw)
        if criterion not in {"task_achievement", "task_response"} and isinstance(
            payload, dict
        ):
            # Small local models may ignore the null-only JSON Schema field and
            # emit an irrelevant task checklist for CC/LR/GRA. Discard that
            # inapplicable field; it must never leak into the public report.
            payload["task_review"] = None
        result = CriterionResult.model_validate(payload)
        if result.criterion != criterion:
            raise ValueError(f"评分维度错误：预期 {criterion}，实际 {result.criterion}")
        normalized_essay = " ".join(essay.split())
        for evidence in [*result.evidence, *result.issues]:
            evidence.quote = ScoringPipeline._normalize_quote(
                evidence.quote, normalized_essay
            )
        if result.task_review is not None:
            for check in result.task_review.checks:
                check.quote = ScoringPipeline._normalize_quote(
                    check.quote, normalized_essay
                )
        return result

    @staticmethod
    def _normalize_quote(quote: str | None, normalized_essay: str) -> str | None:
        """Return an exact essay excerpt, or None for unsupported model text."""

        if quote is None:
            return None
        normalized_quote = " ".join(quote.split())
        if normalized_quote in normalized_essay:
            return normalized_quote
        # Expand ellipses only when every cited part appears in order.
        parts = [
            part.strip()
            for part in re.split(r"(?:\.{2,}|…)+", normalized_quote)
            if part.strip()
        ]
        positions: list[tuple[int, int]] = []
        search_from = 0
        for part in parts:
            position = normalized_essay.find(part, search_from)
            if position < 0:
                break
            positions.append((position, position + len(part)))
            search_from = position + len(part)
        if positions and len(positions) == len(parts):
            return normalized_essay[positions[0][0] : positions[-1][1]]
        return None

    @staticmethod
    def _word_count_warnings(task_type: TaskType, word_count: int) -> list[str]:
        minimum = 150 if task_type == "task1" else 250
        if word_count < minimum:
            return [
                f"作文约 {word_count} 词，低于 Academic {task_type} 最低 {minimum} 词；"
                "仍可分析已有语言，但不能生成可靠 Band 估分。"
            ]
        return []
