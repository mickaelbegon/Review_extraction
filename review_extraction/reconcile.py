from __future__ import annotations

from .models import ArticleResult, Evidence, ExtractedAnswer, ExtractionResult, FinalAnswer, ValidationDecision, ValidationResult


REVIEW_THRESHOLD = 0.75


def reconcile(source_pdf: str, extraction: ExtractionResult, validation: ValidationResult) -> ArticleResult:
    decisions = {decision.item_id: decision for decision in validation.decisions}
    final_answers: list[FinalAnswer] = []

    for answer in extraction.answers:
        decision = decisions.get(answer.item_id)
        if decision is None:
            final_answers.append(_without_validation(answer))
            continue

        final_value = answer.answer
        if decision.corrected_answer is not None and decision.status in {"partial", "disagree", "insufficient_evidence"}:
            final_value = decision.corrected_answer

        final_confidence = _combine_confidence(answer, decision)
        review_required = (
            answer.needs_human_review
            or decision.status != "agree"
            or final_confidence < REVIEW_THRESHOLD
            or not _has_evidence(answer, decision)
        )

        final_answers.append(
            FinalAnswer(
                item_id=answer.item_id,
                final_answer=final_value,
                extractor_answer=answer.answer,
                validator_status=decision.status,
                validator_answer=decision.corrected_answer,
                extractor_confidence=answer.confidence,
                validator_confidence=decision.confidence,
                final_confidence=final_confidence,
                evidence=_merge_evidence(answer.evidence, decision.evidence),
                rationale_short=_rationale(answer, decision),
                review_required=review_required,
            )
        )

    return ArticleResult(article_id=extraction.article_id, source_pdf=source_pdf, answers=final_answers)


def _without_validation(answer: ExtractedAnswer) -> FinalAnswer:
    confidence = min(answer.confidence, 0.5)
    return FinalAnswer(
        item_id=answer.item_id,
        final_answer=answer.answer,
        extractor_answer=answer.answer,
        validator_status="missing",
        validator_answer=None,
        extractor_confidence=answer.confidence,
        validator_confidence=0,
        final_confidence=confidence,
        evidence=answer.evidence,
        rationale_short=f"{answer.rationale_short} Validation result missing.",
        review_required=True,
    )


def _combine_confidence(answer: ExtractedAnswer, decision: ValidationDecision) -> float:
    if decision.status == "agree":
        confidence = (answer.confidence * 0.55) + (decision.confidence * 0.45)
    elif decision.status == "partial":
        confidence = min(answer.confidence, decision.confidence) * 0.85
    elif decision.status == "disagree":
        confidence = min(answer.confidence, decision.confidence) * 0.65
    else:
        confidence = min(answer.confidence, decision.confidence) * 0.5
    return round(max(0.0, min(1.0, confidence)), 3)


def _has_evidence(answer: ExtractedAnswer, decision: ValidationDecision) -> bool:
    return any(e.quote.strip() for e in [*answer.evidence, *decision.evidence])


def _merge_evidence(first: list[Evidence], second: list[Evidence]) -> list[Evidence]:
    seen: set[tuple[int | None, str]] = set()
    merged: list[Evidence] = []
    for evidence in [*first, *second]:
        key = (evidence.page, evidence.quote.strip().lower())
        if evidence.quote.strip() and key not in seen:
            seen.add(key)
            merged.append(evidence)
    return merged[:6]


def _rationale(answer: ExtractedAnswer, decision: ValidationDecision) -> str:
    if decision.status == "agree":
        return answer.rationale_short
    return f"{answer.rationale_short} Validator: {decision.critique}"
