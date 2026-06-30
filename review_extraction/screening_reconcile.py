from __future__ import annotations

from .models import (
    Evidence,
    FinalScreeningCriterion,
    FinalScreeningResult,
    ScreeningCriterionAnswer,
    ScreeningResult,
    ScreeningValidationDecision,
    ScreeningValidationResult,
)


SCREENING_REVIEW_THRESHOLD = 0.8


def reconcile_screening(screening: ScreeningResult, validation: ScreeningValidationResult) -> FinalScreeningResult:
    decisions = {decision.criterion_id: decision for decision in validation.decisions}
    final_criteria: list[FinalScreeningCriterion] = []

    for criterion in screening.criteria:
        validation_decision = decisions.get(criterion.criterion_id)
        if validation_decision is None:
            final_criteria.append(_without_validation(criterion))
            continue

        final_decision = criterion.decision
        if validation_decision.corrected_decision is not None and validation_decision.status != "agree":
            final_decision = validation_decision.corrected_decision

        final_confidence = _combine_confidence(criterion.confidence, validation_decision.confidence, validation_decision.status)
        review_required = (
            validation_decision.status != "agree"
            or final_confidence < SCREENING_REVIEW_THRESHOLD
            or not _has_evidence(criterion, validation_decision)
        )

        final_criteria.append(
            FinalScreeningCriterion(
                criterion_id=criterion.criterion_id,
                final_decision=final_decision,
                screener_decision=criterion.decision,
                validator_status=validation_decision.status,
                validator_decision=validation_decision.corrected_decision,
                screener_confidence=criterion.confidence,
                validator_confidence=validation_decision.confidence,
                final_confidence=final_confidence,
                evidence=_merge_evidence(criterion.evidence, validation_decision.evidence),
                rationale_short=_rationale(criterion, validation_decision),
                review_required=review_required,
            )
        )

    overall_decision = _overall_decision(final_criteria)
    if validation.corrected_overall_decision is not None and validation.overall_status != "agree":
        overall_decision = validation.corrected_overall_decision

    final_confidence = _overall_confidence(final_criteria, validation.overall_status)
    review_required = (
        validation.overall_status != "agree"
        or any(criterion.review_required for criterion in final_criteria)
        or final_confidence < SCREENING_REVIEW_THRESHOLD
    )
    extraction_allowed = overall_decision == "include" and not review_required

    return FinalScreeningResult(
        article_id=screening.article_id,
        overall_decision=overall_decision,
        final_confidence=final_confidence,
        review_required=review_required,
        extraction_allowed=extraction_allowed,
        criteria=final_criteria,
    )


def _without_validation(criterion: ScreeningCriterionAnswer) -> FinalScreeningCriterion:
    return FinalScreeningCriterion(
        criterion_id=criterion.criterion_id,
        final_decision=criterion.decision,
        screener_decision=criterion.decision,
        validator_status="missing",
        validator_decision=None,
        screener_confidence=criterion.confidence,
        validator_confidence=0,
        final_confidence=min(criterion.confidence, 0.5),
        evidence=criterion.evidence,
        rationale_short=f"{criterion.rationale_short} Validation result missing.",
        review_required=True,
    )


def _combine_confidence(screener_confidence: float, validator_confidence: float, status: str) -> float:
    if status == "agree":
        confidence = (screener_confidence * 0.5) + (validator_confidence * 0.5)
    elif status == "partial":
        confidence = min(screener_confidence, validator_confidence) * 0.85
    elif status == "disagree":
        confidence = min(screener_confidence, validator_confidence) * 0.65
    else:
        confidence = min(screener_confidence, validator_confidence) * 0.5
    return round(max(0.0, min(1.0, confidence)), 3)


def _overall_decision(criteria: list[FinalScreeningCriterion]) -> str:
    if any(criterion.final_decision == "exclude" for criterion in criteria):
        return "exclude"
    if criteria and all(criterion.final_decision == "include" for criterion in criteria):
        return "include"
    return "uncertain"


def _overall_confidence(criteria: list[FinalScreeningCriterion], overall_status: str) -> float:
    if not criteria:
        return 0
    confidence = min(criterion.final_confidence for criterion in criteria)
    if overall_status == "agree":
        return confidence
    if overall_status == "partial":
        return round(confidence * 0.9, 3)
    if overall_status == "disagree":
        return round(confidence * 0.75, 3)
    return round(confidence * 0.5, 3)


def _has_evidence(criterion: ScreeningCriterionAnswer, decision: ScreeningValidationDecision) -> bool:
    return any(evidence.quote.strip() for evidence in [*criterion.evidence, *decision.evidence])


def _merge_evidence(first: list[Evidence], second: list[Evidence]) -> list[Evidence]:
    seen: set[tuple[int | None, str]] = set()
    merged: list[Evidence] = []
    for evidence in [*first, *second]:
        key = (evidence.page, evidence.quote.strip().lower())
        if evidence.quote.strip() and key not in seen:
            seen.add(key)
            merged.append(evidence)
    return merged[:6]


def _rationale(criterion: ScreeningCriterionAnswer, decision: ScreeningValidationDecision) -> str:
    if decision.status == "agree":
        return criterion.rationale_short
    return f"{criterion.rationale_short} Validator: {decision.critique}"
