from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, confloat


def openai_strict_schema(schema: dict) -> dict:
    """Normalize a Pydantic schema for OpenAI strict structured outputs."""
    normalized = dict(schema)
    _require_all_object_properties(normalized)
    return normalized


def _require_all_object_properties(node: object) -> None:
    if isinstance(node, dict):
        node.pop("default", None)
        properties = node.get("properties")
        if isinstance(properties, dict):
            node["required"] = list(properties.keys())
            node["additionalProperties"] = False
        for value in node.values():
            _require_all_object_properties(value)
    elif isinstance(node, list):
        for value in node:
            _require_all_object_properties(value)


class Evidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    page: int | None = Field(default=None, description="1-based page number when known.")
    quote: str = Field(description="Short exact quote supporting the decision.")
    relevance: str = Field(description="Why this quote supports or contradicts the answer.")


class ExtractedAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid")

    item_id: str
    answer: str | list[str]
    confidence: confloat(ge=0, le=1)
    evidence: list[Evidence] = Field(default_factory=list)
    rationale_short: str
    needs_human_review: bool = False


class ExtractionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    article_id: str
    answers: list[ExtractedAnswer]


ScreeningDecisionValue = Literal["include", "exclude", "unclear"]
ScreeningOverallDecision = Literal["include", "exclude", "uncertain"]


class ScreeningCriterionAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid")

    criterion_id: str
    decision: ScreeningDecisionValue
    confidence: confloat(ge=0, le=1)
    evidence: list[Evidence] = Field(default_factory=list)
    rationale_short: str


class ScreeningResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    article_id: str
    overall_decision: ScreeningOverallDecision
    criteria: list[ScreeningCriterionAnswer]


class ScreeningValidationDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    criterion_id: str
    status: Literal["agree", "partial", "disagree", "insufficient_evidence"]
    corrected_decision: ScreeningDecisionValue | None = None
    confidence: confloat(ge=0, le=1)
    evidence: list[Evidence] = Field(default_factory=list)
    critique: str


class ScreeningValidationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    article_id: str
    overall_status: Literal["agree", "partial", "disagree", "insufficient_evidence"]
    corrected_overall_decision: ScreeningOverallDecision | None = None
    decisions: list[ScreeningValidationDecision]


class ValidationDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    item_id: str
    status: Literal["agree", "partial", "disagree", "insufficient_evidence"]
    corrected_answer: str | list[str] | None = None
    confidence: confloat(ge=0, le=1)
    evidence: list[Evidence] = Field(default_factory=list)
    critique: str


class ValidationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    article_id: str
    decisions: list[ValidationDecision]


class TokenUsage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    step: str
    model: str
    elapsed_seconds: float | None = None
    input_tokens: int = 0
    cached_input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    input_cost_per_million: float | None = None
    cached_input_cost_per_million: float | None = None
    output_cost_per_million: float | None = None
    estimated_cost_usd: float | None = None


class FinalAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid")

    item_id: str
    final_answer: str | list[str]
    extractor_answer: str | list[str]
    validator_status: str
    validator_answer: str | list[str] | None = None
    extractor_confidence: confloat(ge=0, le=1)
    validator_confidence: confloat(ge=0, le=1)
    final_confidence: confloat(ge=0, le=1)
    evidence: list[Evidence] = Field(default_factory=list)
    rationale_short: str
    review_required: bool


class FinalScreeningCriterion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    criterion_id: str
    final_decision: ScreeningDecisionValue
    screener_decision: ScreeningDecisionValue
    validator_status: str
    validator_decision: ScreeningDecisionValue | None = None
    screener_confidence: confloat(ge=0, le=1)
    validator_confidence: confloat(ge=0, le=1)
    final_confidence: confloat(ge=0, le=1)
    evidence: list[Evidence] = Field(default_factory=list)
    rationale_short: str
    review_required: bool


class FinalScreeningResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    article_id: str
    overall_decision: ScreeningOverallDecision
    final_confidence: confloat(ge=0, le=1)
    review_required: bool
    extraction_allowed: bool
    criteria: list[FinalScreeningCriterion]


class ArticleResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    article_id: str
    source_pdf: str
    screening: FinalScreeningResult | None = None
    answers: list[FinalAnswer]
    usage: list[TokenUsage] = Field(default_factory=list)
    processing_seconds: float | None = None


SCREENING_JSON_SCHEMA = openai_strict_schema(ScreeningResult.model_json_schema())
SCREENING_VALIDATION_JSON_SCHEMA = openai_strict_schema(ScreeningValidationResult.model_json_schema())
EXTRACTION_JSON_SCHEMA = openai_strict_schema(ExtractionResult.model_json_schema())
VALIDATION_JSON_SCHEMA = openai_strict_schema(ValidationResult.model_json_schema())
