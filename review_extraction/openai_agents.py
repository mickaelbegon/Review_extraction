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
    ValidationResult,
)
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


@dataclass
class OpenAIConfig:
    model: str = "gpt-5.5"
    validator_model: str = "gpt-5.5"

    @classmethod
    def from_env(cls) -> "OpenAIConfig":
        return cls(
            model=os.getenv("OPENAI_MODEL", "gpt-5.5"),
            validator_model=os.getenv("OPENAI_VALIDATOR_MODEL", os.getenv("OPENAI_MODEL", "gpt-5.5")),
        )


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

    def screen(self, article_id: str, paper_context: str) -> ScreeningResult:
        prompt = "\n\n".join(
            [
                screening_prompt(),
                "Paper text follows. Page markers are authoritative.",
                paper_context,
            ]
        )
        response = self.client.responses.create(
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
        response = self.client.responses.create(
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
        return ScreeningValidationResult.model_validate(data)

    def extract(self, article_id: str, paper_context: str) -> ExtractionResult:
        prompt = "\n\n".join(
            [
                extraction_form_prompt(),
                "Paper text follows. Page markers are authoritative.",
                paper_context,
            ]
        )
        response = self.client.responses.create(
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
        response = self.client.responses.create(
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
        return ValidationResult.model_validate(data)


def _response_json(response: object) -> dict:
    output_text = getattr(response, "output_text", None)
    if not output_text:
        try:
            output_text = response.output[0].content[0].text
        except Exception as exc:  # pragma: no cover - defensive SDK compatibility path
            raise RuntimeError("Could not read OpenAI response text.") from exc
    return json.loads(output_text)
