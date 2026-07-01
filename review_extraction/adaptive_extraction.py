from __future__ import annotations

from .form_schema import EXTRACTION_ITEMS, JOINTS, SEGMENTS
from .models import Evidence, ExtractionPlanResult, FinalAnswer


MEASUREMENT_THEME = "measurement_methods"
PLAN_EXTRACT_STATUSES = {"present", "unclear"}


def item_ids_for_plan(plan: ExtractionPlanResult) -> list[str]:
    statuses = _theme_statuses(plan)
    selected = {MEASUREMENT_THEME}

    for segment in SEGMENTS:
        theme_id = f"segment.{segment}"
        if statuses.get(theme_id, "unclear") in PLAN_EXTRACT_STATUSES:
            selected.update(_segment_item_ids(segment))

    for joint_id in JOINTS:
        theme_id = f"joint.{joint_id}"
        if statuses.get(theme_id, "unclear") in PLAN_EXTRACT_STATUSES:
            selected.update(_joint_item_ids(joint_id))

    return [item.id for item in EXTRACTION_ITEMS if item.id in selected]


def automatic_absent_answers(plan: ExtractionPlanResult) -> list[FinalAnswer]:
    statuses = _theme_statuses(plan)
    decisions = {decision.theme_id: decision for decision in plan.themes}
    answers: list[FinalAnswer] = []

    for segment in SEGMENTS:
        theme_id = f"segment.{segment}"
        if statuses.get(theme_id) == "absent":
            decision = decisions[theme_id]
            answers.extend(
                [
                    _automatic_answer(
                        item_id=f"{segment}_used",
                        answer="no",
                        decision_confidence=decision.confidence,
                        evidence=decision.evidence,
                        rationale=f"{segment} segment was not selected for detailed extraction: {decision.rationale_short}",
                    ),
                    _automatic_answer(
                        item_id=f"{segment}_axes_orientation",
                        answer="no_method_or_reference",
                        decision_confidence=decision.confidence,
                        evidence=decision.evidence,
                        rationale=f"{segment} axes orientation was not assessed because the segment appears absent.",
                    ),
                    _automatic_answer(
                        item_id=f"{segment}_axes_construction",
                        answer="no_method_or_reference",
                        decision_confidence=decision.confidence,
                        evidence=decision.evidence,
                        rationale=f"{segment} axes construction was not assessed because the segment appears absent.",
                    ),
                    _automatic_answer(
                        item_id=f"{segment}_scs_origin",
                        answer="no_method_or_reference",
                        decision_confidence=decision.confidence,
                        evidence=decision.evidence,
                        rationale=f"{segment} SCS origin was not assessed because the segment appears absent.",
                    ),
                ]
            )

    for joint_id in JOINTS:
        theme_id = f"joint.{joint_id}"
        if statuses.get(theme_id) == "absent":
            decision = decisions[theme_id]
            answers.extend(
                [
                    _automatic_answer(
                        item_id=f"{joint_id}_reported",
                        answer="no",
                        decision_confidence=decision.confidence,
                        evidence=decision.evidence,
                        rationale=f"{joint_id} kinematics were not selected for detailed extraction: {decision.rationale_short}",
                    ),
                    _automatic_answer(
                        item_id=f"{joint_id}_rotations",
                        answer="not_assessed",
                        decision_confidence=decision.confidence,
                        evidence=decision.evidence,
                        rationale=f"{joint_id} rotations were not assessed because the joint relationship appears absent.",
                    ),
                    _automatic_answer(
                        item_id=f"{joint_id}_translations",
                        answer="not_assessed",
                        decision_confidence=decision.confidence,
                        evidence=decision.evidence,
                        rationale=f"{joint_id} translations were not assessed because the joint relationship appears absent.",
                    ),
                ]
            )

    return _sort_final_answers(answers)


def merge_adaptive_answers(extracted: list[FinalAnswer], automatic: list[FinalAnswer]) -> list[FinalAnswer]:
    by_id = {answer.item_id: answer for answer in automatic}
    by_id.update({answer.item_id: answer for answer in extracted})
    return [by_id[item.id] for item in EXTRACTION_ITEMS if item.id in by_id]


def _theme_statuses(plan: ExtractionPlanResult) -> dict[str, str]:
    return {decision.theme_id: decision.status for decision in plan.themes}


def _segment_item_ids(segment: str) -> set[str]:
    return {
        f"{segment}_used",
        f"{segment}_axes_orientation",
        f"{segment}_axes_construction",
        f"{segment}_scs_origin",
    }


def _joint_item_ids(joint_id: str) -> set[str]:
    return {
        f"{joint_id}_reported",
        f"{joint_id}_rotations",
        f"{joint_id}_translations",
    }


def _automatic_answer(
    *,
    item_id: str,
    answer: str,
    decision_confidence: float,
    evidence: list[Evidence],
    rationale: str,
) -> FinalAnswer:
    confidence = round(min(0.9, max(0.6, decision_confidence)), 3)
    return FinalAnswer(
        item_id=item_id,
        final_answer=answer,
        extractor_answer=answer,
        validator_status="auto_absent",
        validator_answer=None,
        extractor_confidence=confidence,
        validator_confidence=confidence,
        final_confidence=confidence,
        evidence=evidence[:3],
        rationale_short=rationale,
        review_required=decision_confidence < 0.75,
    )


def _sort_final_answers(answers: list[FinalAnswer]) -> list[FinalAnswer]:
    order = {item.id: index for index, item in enumerate(EXTRACTION_ITEMS)}
    return sorted(answers, key=lambda answer: order.get(answer.item_id, len(order)))
