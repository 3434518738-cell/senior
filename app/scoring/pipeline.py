"""Pure Python scoring pipeline ready to be placed inside a LangGraph."""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Protocol

from pydantic import ValidationError

from app.rag.corpus_loader import TaskType
from app.rubric.indexing import RubricVectorStore, retrieve_rubric_context
from app.scoring.prompts import build_criterion_prompt
from app.scoring.schemas import (
    Criterion,
    CriterionResult,
    ScoreReport,
    ScoreRequest,
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
    warnings: list[str]
    samples: list[dict[str, Any]]
    contexts: dict[Criterion, dict[str, list[dict[str, Any]]]]


class JsonGeneratingModel(Protocol):
    """Model interface supporting Ollama's JSON response format."""

    def generate(
        self, prompt: str, *, response_format: str | dict[str, Any] | None = None
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

        estimate = round_to_half_band(
            sum(result.band for result in results) / len(results)
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
                criterion_results=results,
                essay_band_estimate=estimate,
                warnings=preparation.warnings,
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

    def _score_criterion(
        self,
        request: ScoreRequest,
        cleaned_essay: str,
        criterion: Criterion,
        context: dict[str, list[dict[str, Any]]],
        samples: list[dict[str, Any]],
    ) -> CriterionResult:
        prompt = build_criterion_prompt(
            request, cleaned_essay, criterion, context, samples
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
                '"evidence":[{"quote":"exact essay text",'
                '"explanation":"..."}],"strengths":["..."],'
                '"issues":[{"quote":"exact essay text",'
                '"explanation":"..."}],"improvements":["..."]}\n'
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
        result = CriterionResult.model_validate_json(raw)
        if result.criterion != criterion:
            raise ValueError(f"评分维度错误：预期 {criterion}，实际 {result.criterion}")
        normalized_essay = " ".join(essay.split())
        for evidence in [*result.evidence, *result.issues]:
            normalized_quote = " ".join(evidence.quote.split())
            if normalized_quote not in normalized_essay:
                raise ValueError(f"证据引文不在作文原文中: {evidence.quote}")
        return result

    @staticmethod
    def _word_count_warnings(task_type: TaskType, word_count: int) -> list[str]:
        minimum = 150 if task_type == "task1" else 250
        if word_count < minimum:
            return [
                f"作文约 {word_count} 词，低于 Academic {task_type} 建议最低 {minimum} 词。"
            ]
        return []
