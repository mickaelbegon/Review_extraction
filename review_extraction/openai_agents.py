from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any

from .form_schema import extraction_form_prompt
from .models import (
    EXTRACTION_JSON_SCHEMA,
    SCREENING_JSON_SCHEMA,
    SCREENING_VALIDATION_JSON_SCHEMA,
    VALIDATION_JSON_SCHEMA,
    ExtractionResult,
    ScreeningResult,
    ScreeningValidationResult,
    TokenUsage,
    ValidationResult,
)
from .pricing import pricing_for_model, tax_rate_from_env
from .screening_schema import screening_prompt


EXTRACTOR_SYSTEM_PROMPT = """You are a systematic-review extraction agent for shoulder kinematics methodology.
Extract only information supported by the paper text. Prefer uncertainty over inference.
Return concise evidence quotes with page numbers. Do not fabricate citations."""

VALIDATOR_SYSTEM_PROMPT = """You are an independent validation agent.
Audit the extractor's answers against the paper text. Your job is to find unsupported answers, overconfident claims, missing evidence, and better alternatives.
Be strict: global statements such as 'ISB recommendations were followed' are not always enough for segment-specific reproducibility."""

SCREENING_SYSTEM_PROMPT = """You are a systematic-review full-paper screening agent.
Apply the inclusion and exclusion criteria strictly from the full paper text. Return evidence for each criterion.
Prefer uncertainty over guessing when the full paper does not clearly support inclusion or exclusion."""

SCREENING_VALIDATOR_SYSTEM_PROMPT = """You are an independent full-paper screening validator.
Audit the screener's inclusion/exclusion decisions against the full paper text. Be strict about unsupported inclusion.
If a clear exclusion criterion is present, correct the decision to exclude."""


class OpenAIRequestError(RuntimeError):
    """User-facing OpenAI API failure."""


class OpenAIQuotaError(OpenAIRequestError):
    """OpenAI quota or billing failure."""


@dataclass
class OpenAIConfig:
    model: str = "gpt-5.5"
    validator_model: str = "gpt-5.5"
    input_cost_per_million: float | None = None
    cached_input_cost_per_million: float | None = None
    output_cost_per_million: float | None = None
    validator_input_cost_per_million: float | None = None
    validator_cached_input_cost_per_million: float | None = None
    validator_output_cost_per_million: float | None = None
    tax_rate: float = 0.14975

    @classmethod
    def from_env(cls) -> "OpenAIConfig":
        tax_rate = tax_rate_from_env()
        input_cost = _optional_float("OPENAI_INPUT_COST_PER_1M")
        cached_input_cost = _optional_float("OPENAI_CACHED_INPUT_COST_PER_1M")
        output_cost = _optional_float("OPENAI_OUTPUT_COST_PER_1M")
        config = cls(
            model=os.getenv("OPENAI_MODEL", "gpt-5.5"),
            validator_model=os.getenv("OPENAI_VALIDATOR_MODEL", os.getenv("OPENAI_MODEL", "gpt-5.5")),
            input_cost_per_million=input_cost,
            cached_input_cost_per_million=cached_input_cost,
            output_cost_per_million=output_cost,
            validator_input_cost_per_million=_optional_float("OPENAI_VALIDATOR_INPUT_COST_PER_1M", input_cost),
            validator_cached_input_cost_per_million=_optional_float("OPENAI_VALIDATOR_CACHED_INPUT_COST_PER_1M", cached_input_cost),
            validator_output_cost_per_million=_optional_float("OPENAI_VALIDATOR_OUTPUT_COST_PER_1M", output_cost),
            tax_rate=tax_rate,
        )
        return config

    def apply_model_pricing(self) -> None:
        model_pricing = pricing_for_model(self.model, tax_rate=self.tax_rate)
        if model_pricing is not None:
            if self.input_cost_per_million is None:
                self.input_cost_per_million = model_pricing.input_with_tax
            if self.cached_input_cost_per_million is None:
                self.cached_input_cost_per_million = model_pricing.cached_input_with_tax
            if self.output_cost_per_million is None:
                self.output_cost_per_million = model_pricing.output_with_tax

        validator_pricing = pricing_for_model(self.validator_model, tax_rate=self.tax_rate)
        if validator_pricing is not None:
            if self.validator_input_cost_per_million is None:
                self.validator_input_cost_per_million = validator_pricing.input_with_tax
            if self.validator_cached_input_cost_per_million is None:
                self.validator_cached_input_cost_per_million = validator_pricing.cached_input_with_tax
            if self.validator_output_cost_per_million is None:
                self.validator_output_cost_per_million = validator_pricing.output_with_tax


class DualAgentExtractor:
    def __init__(self, client: Any | None = None, config: OpenAIConfig | None = None) -> None:
        if client is None:
            try:
                from openai import OpenAI
            except ImportError as exc:
                raise RuntimeError(
                    "The OpenAI SDK is required to run extraction. Install dependencies with: "
                    'pip install -e ".[dev,api]"'
                ) from exc
            client = OpenAI()
        self.client = client
        self.config = config or OpenAIConfig.from_env()
        self.config.apply_model_pricing()
        self.usage_events: list[TokenUsage] = []

    def screen(self, article_id: str, paper_context: str) -> ScreeningResult:
        prompt = "\n\n".join(
            [
                screening_prompt(),
                "Paper text follows. Page markers are authoritative.",
                paper_context,
            ]
        )
        response = _create_response(
            self.client,
            model=self.config.model,
            input=[
                {"role": "system", "content": SCREENING_SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            text={
                "format": {
                    "type": "json_schema",
                    "name": "screening_result",
                    "schema": SCREENING_JSON_SCHEMA,
                    "strict": True,
                }
            },
        )
        data = _response_json(response)
        data["article_id"] = data.get("article_id") or article_id
        self._record_usage(
            response,
            step="screening",
            model=self.config.model,
            input_cost_per_million=self.config.input_cost_per_million,
            cached_input_cost_per_million=self.config.cached_input_cost_per_million,
            output_cost_per_million=self.config.output_cost_per_million,
        )
        return ScreeningResult.model_validate(data)

    def validate_screening(
        self,
        article_id: str,
        paper_context: str,
        screening: ScreeningResult,
    ) -> ScreeningValidationResult:
        prompt = "\n\n".join(
            [
                screening_prompt(),
                "Screener output to audit:",
                screening.model_dump_json(indent=2),
                "Paper text follows. Page markers are authoritative.",
                paper_context,
            ]
        )
        response = _create_response(
            self.client,
            model=self.config.validator_model,
            input=[
                {"role": "system", "content": SCREENING_VALIDATOR_SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            text={
                "format": {
                    "type": "json_schema",
                    "name": "screening_validation_result",
                    "schema": SCREENING_VALIDATION_JSON_SCHEMA,
                    "strict": True,
                }
            },
        )
        data = _response_json(response)
        data["article_id"] = data.get("article_id") or article_id
        self._record_usage(
            response,
            step="screening_validation",
            model=self.config.validator_model,
            input_cost_per_million=self.config.validator_input_cost_per_million,
            cached_input_cost_per_million=self.config.validator_cached_input_cost_per_million,
            output_cost_per_million=self.config.validator_output_cost_per_million,
        )
        return ScreeningValidationResult.model_validate(data)

    def extract(self, article_id: str, paper_context: str) -> ExtractionResult:
        prompt = "\n\n".join(
            [
                extraction_form_prompt(),
                "Paper text follows. Page markers are authoritative.",
                paper_context,
            ]
        )
        response = _create_response(
            self.client,
            model=self.config.model,
            input=[
                {"role": "system", "content": EXTRACTOR_SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            text={
                "format": {
                    "type": "json_schema",
                    "name": "extraction_result",
                    "schema": EXTRACTION_JSON_SCHEMA,
                    "strict": True,
                }
            },
        )
        data = _response_json(response)
        data["article_id"] = data.get("article_id") or article_id
        self._record_usage(
            response,
            step="extraction",
            model=self.config.model,
            input_cost_per_million=self.config.input_cost_per_million,
            cached_input_cost_per_million=self.config.cached_input_cost_per_million,
            output_cost_per_million=self.config.output_cost_per_million,
        )
        return ExtractionResult.model_validate(data)

    def validate(self, article_id: str, paper_context: str, extraction: ExtractionResult) -> ValidationResult:
        prompt = "\n\n".join(
            [
                extraction_form_prompt(),
                "Extractor output to audit:",
                extraction.model_dump_json(indent=2),
                "Paper text follows. Page markers are authoritative.",
                paper_context,
            ]
        )
        response = _create_response(
            self.client,
            model=self.config.validator_model,
            input=[
                {"role": "system", "content": VALIDATOR_SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            text={
                "format": {
                    "type": "json_schema",
                    "name": "validation_result",
                    "schema": VALIDATION_JSON_SCHEMA,
                    "strict": True,
                }
            },
        )
        data = _response_json(response)
        data["article_id"] = data.get("article_id") or article_id
        self._record_usage(
            response,
            step="extraction_validation",
            model=self.config.validator_model,
            input_cost_per_million=self.config.validator_input_cost_per_million,
            cached_input_cost_per_million=self.config.validator_cached_input_cost_per_million,
            output_cost_per_million=self.config.validator_output_cost_per_million,
        )
        return ValidationResult.model_validate(data)

    def _record_usage(
        self,
        response: object,
        *,
        step: str,
        model: str,
        input_cost_per_million: float | None,
        cached_input_cost_per_million: float | None,
        output_cost_per_million: float | None,
    ) -> None:
        usage = _response_usage(
            response,
            step=step,
            model=model,
            input_cost_per_million=input_cost_per_million,
            cached_input_cost_per_million=cached_input_cost_per_million,
            output_cost_per_million=output_cost_per_million,
        )
        if usage is not None:
            self.usage_events.append(usage)


def _create_response(client: Any, **kwargs: Any) -> object:
    try:
        return client.responses.create(**kwargs)
    except Exception as exc:
        if _is_insufficient_quota_error(exc):
            raise OpenAIQuotaError(
                "OpenAI quota exceeded for the configured API key. "
                "Check billing/usage or switch to a key with available quota, then rerun the same command. "
                "Existing JSON outputs will be reused automatically."
            ) from exc
        if exc.__class__.__name__ == "RateLimitError":
            raise OpenAIRequestError(
                "OpenAI rate limit reached. Wait a bit, then rerun the same command. "
                "Existing JSON outputs will be reused automatically."
            ) from exc
        raise


def _is_insufficient_quota_error(exc: Exception) -> bool:
    body = getattr(exc, "body", None)
    code = None
    message = str(exc)
    if isinstance(body, dict):
        code = body.get("code")
        message = str(body.get("message") or message)
    code = code or getattr(exc, "code", None)
    return code == "insufficient_quota" or "exceeded your current quota" in message.lower()


def _response_json(response: object) -> dict:
    output_text = getattr(response, "output_text", None)
    if not output_text:
        try:
            output_text = response.output[0].content[0].text
        except Exception as exc:  # pragma: no cover - defensive SDK compatibility path
            raise RuntimeError("Could not read OpenAI response text.") from exc
    return json.loads(output_text)


def _response_usage(
    response: object,
    *,
    step: str,
    model: str,
    input_cost_per_million: float | None,
    cached_input_cost_per_million: float | None,
    output_cost_per_million: float | None,
) -> TokenUsage | None:
    usage = getattr(response, "usage", None)
    if usage is None:
        return None
    input_tokens = _usage_int(usage, "input_tokens", "prompt_tokens")
    cached_input_tokens = _cached_input_tokens(usage)
    output_tokens = _usage_int(usage, "output_tokens", "completion_tokens")
    total_tokens = _usage_int(usage, "total_tokens") or input_tokens + output_tokens
    estimated_cost = None
    if input_cost_per_million is not None and output_cost_per_million is not None:
        uncached_input_tokens = max(0, input_tokens - cached_input_tokens)
        cached_rate = cached_input_cost_per_million if cached_input_cost_per_million is not None else input_cost_per_million
        estimated_cost = round(
            (uncached_input_tokens / 1_000_000 * input_cost_per_million)
            + (cached_input_tokens / 1_000_000 * cached_rate)
            + (output_tokens / 1_000_000 * output_cost_per_million),
            6,
        )
    return TokenUsage(
        step=step,
        model=model,
        input_tokens=input_tokens,
        cached_input_tokens=cached_input_tokens,
        output_tokens=output_tokens,
        total_tokens=total_tokens,
        input_cost_per_million=input_cost_per_million,
        cached_input_cost_per_million=cached_input_cost_per_million,
        output_cost_per_million=output_cost_per_million,
        estimated_cost_usd=estimated_cost,
    )


def _usage_int(usage: object, *names: str) -> int:
    for name in names:
        value = usage.get(name) if isinstance(usage, dict) else getattr(usage, name, None)
        if value is not None:
            return int(value)
    return 0


def _cached_input_tokens(usage: object) -> int:
    details = usage.get("input_tokens_details") if isinstance(usage, dict) else getattr(usage, "input_tokens_details", None)
    if details is None:
        details = usage.get("prompt_tokens_details") if isinstance(usage, dict) else getattr(usage, "prompt_tokens_details", None)
    if details is None:
        return 0
    if isinstance(details, dict):
        value = details.get("cached_tokens")
    else:
        value = getattr(details, "cached_tokens", None)
    return int(value or 0)


def _optional_float(env_name: str, default: float | None = None) -> float | None:
    raw = os.getenv(env_name)
    if raw is None or not raw.strip():
        return default
    return float(raw)
