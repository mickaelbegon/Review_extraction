from review_extraction.models import Evidence, ExtractedAnswer, ExtractionResult, ValidationDecision, ValidationResult
from review_extraction.reconcile import reconcile


def test_reconcile_agreement_keeps_answer_and_raises_confidence():
    extraction = ExtractionResult(
        article_id="paper",
        answers=[
            ExtractedAnswer(
                item_id="scapula_used",
                answer="yes",
                confidence=0.8,
                evidence=[Evidence(page=2, quote="The scapula was tracked.", relevance="segment used")],
                rationale_short="Scapula tracking is described.",
            )
        ],
    )
    validation = ValidationResult(
        article_id="paper",
        decisions=[
            ValidationDecision(
                item_id="scapula_used",
                status="agree",
                confidence=0.9,
                evidence=[Evidence(page=2, quote="The scapula was tracked.", relevance="confirms use")],
                critique="Supported.",
            )
        ],
    )

    result = reconcile("paper.pdf", extraction, validation)

    answer = result.answers[0]
    assert answer.final_answer == "yes"
    assert answer.final_confidence == 0.845
    assert answer.review_required is False


def test_reconcile_disagreement_uses_validator_correction_and_requires_review():
    extraction = ExtractionResult(
        article_id="paper",
        answers=[
            ExtractedAnswer(
                item_id="humerus_rotations",
                answer="isb_explicit_method_aligned",
                confidence=0.92,
                evidence=[Evidence(page=5, quote="ISB recommendations were followed.", relevance="global claim")],
                rationale_short="ISB is mentioned.",
            )
        ],
    )
    validation = ValidationResult(
        article_id="paper",
        decisions=[
            ValidationDecision(
                item_id="humerus_rotations",
                status="disagree",
                corrected_answer="isb_explicit_no_method",
                confidence=0.8,
                evidence=[Evidence(page=5, quote="ISB recommendations were followed.", relevance="no Euler sequence given")],
                critique="The method is not described segment by segment.",
            )
        ],
    )

    result = reconcile("paper.pdf", extraction, validation)

    answer = result.answers[0]
    assert answer.final_answer == "isb_explicit_no_method"
    assert answer.final_confidence == 0.52
    assert answer.review_required is True
