import unittest

from review_extraction.models import (
    Evidence,
    ScreeningCriterionAnswer,
    ScreeningResult,
    ScreeningValidationDecision,
    ScreeningValidationResult,
)
from review_extraction.screening_reconcile import reconcile_screening


class ScreeningReconcileTests(unittest.TestCase):
    def test_included_screening_allows_extraction_when_validated(self) -> None:
        screening = ScreeningResult(
            article_id="paper",
            overall_decision="include",
            criteria=[
                ScreeningCriterionAnswer(
                    criterion_id="population",
                    decision="include",
                    confidence=0.9,
                    evidence=[Evidence(page=1, quote="Participants were adults.", relevance="human population")],
                    rationale_short="Human participants are described.",
                )
            ],
        )
        validation = ScreeningValidationResult(
            article_id="paper",
            overall_status="agree",
            corrected_overall_decision=None,
            decisions=[
                ScreeningValidationDecision(
                    criterion_id="population",
                    status="agree",
                    corrected_decision=None,
                    confidence=0.9,
                    evidence=[],
                    critique="Supported.",
                )
            ],
        )

        result = reconcile_screening(screening, validation)

        self.assertEqual(result.overall_decision, "include")
        self.assertFalse(result.review_required)
        self.assertTrue(result.extraction_allowed)

    def test_exclusion_blocks_downstream_extraction(self) -> None:
        screening = ScreeningResult(
            article_id="paper",
            overall_decision="include",
            criteria=[
                ScreeningCriterionAnswer(
                    criterion_id="population",
                    decision="include",
                    confidence=0.8,
                    evidence=[Evidence(page=1, quote="Rat shoulders were examined.", relevance="animal study")],
                    rationale_short="Initially misclassified.",
                )
            ],
        )
        validation = ScreeningValidationResult(
            article_id="paper",
            overall_status="disagree",
            corrected_overall_decision="exclude",
            decisions=[
                ScreeningValidationDecision(
                    criterion_id="population",
                    status="disagree",
                    corrected_decision="exclude",
                    confidence=0.95,
                    evidence=[Evidence(page=1, quote="Rat shoulders were examined.", relevance="animal exclusion")],
                    critique="Animal study should be excluded.",
                )
            ],
        )

        result = reconcile_screening(screening, validation)

        self.assertEqual(result.overall_decision, "exclude")
        self.assertTrue(result.review_required)
        self.assertFalse(result.extraction_allowed)


if __name__ == "__main__":
    unittest.main()
