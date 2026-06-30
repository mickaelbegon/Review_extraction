import unittest

from review_extraction.models import Evidence, ExtractedAnswer, ExtractionResult, ValidationDecision, ValidationResult
from review_extraction.reconcile import reconcile


class ReconcileTests(unittest.TestCase):
    def test_agreement_keeps_answer_and_raises_confidence(self) -> None:
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
        self.assertEqual(answer.final_answer, "yes")
        self.assertEqual(answer.final_confidence, 0.845)
        self.assertFalse(answer.review_required)

    def test_disagreement_uses_validator_correction_and_requires_review(self) -> None:
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
        self.assertEqual(answer.final_answer, "isb_explicit_no_method")
        self.assertEqual(answer.final_confidence, 0.52)
        self.assertTrue(answer.review_required)

    def test_missing_validation_forces_human_review(self) -> None:
        extraction = ExtractionResult(
            article_id="paper",
            answers=[
                ExtractedAnswer(
                    item_id="thorax_used",
                    answer="yes",
                    confidence=0.95,
                    evidence=[Evidence(page=1, quote="Thorax markers were placed.", relevance="segment used")],
                    rationale_short="Thorax markers are described.",
                )
            ],
        )
        validation = ValidationResult(article_id="paper", decisions=[])

        result = reconcile("paper.pdf", extraction, validation)

        answer = result.answers[0]
        self.assertEqual(answer.validator_status, "missing")
        self.assertLessEqual(answer.final_confidence, 0.5)
        self.assertTrue(answer.review_required)

    def test_no_evidence_forces_human_review_even_when_agents_agree(self) -> None:
        extraction = ExtractionResult(
            article_id="paper",
            answers=[
                ExtractedAnswer(
                    item_id="clavicle_used",
                    answer="yes",
                    confidence=0.9,
                    evidence=[],
                    rationale_short="Clavicle appears to be used.",
                )
            ],
        )
        validation = ValidationResult(
            article_id="paper",
            decisions=[
                ValidationDecision(
                    item_id="clavicle_used",
                    status="agree",
                    confidence=0.9,
                    evidence=[],
                    critique="Seems plausible.",
                )
            ],
        )

        result = reconcile("paper.pdf", extraction, validation)

        answer = result.answers[0]
        self.assertTrue(answer.review_required)


if __name__ == "__main__":
    unittest.main()
