from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, confloat


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


class ArticleResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    article_id: str
    source_pdf: str
    answers: list[FinalAnswer]


EXTRACTION_JSON_SCHEMA = ExtractionResult.model_json_schema()
VALIDATION_JSON_SCHEMA = ValidationResult.model_json_schema()
