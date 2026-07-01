import unittest

from review_extraction.adaptive_extraction import automatic_absent_answers, item_ids_for_plan, merge_adaptive_answers
from review_extraction.models import Evidence, ExtractionPlanResult, ExtractionThemeDecision, FinalAnswer


class AdaptiveExtractionTests(unittest.TestCase):
    def test_plan_selects_unclear_blocks_and_auto_fills_absent_blocks(self) -> None:
        plan = ExtractionPlanResult(
            article_id="paper",
            themes=[
                ExtractionThemeDecision(
                    theme_id="measurement_methods",
                    status="present",
                    confidence=0.9,
                    evidence=[],
                    rationale_short="Measurement is reported.",
                ),
                ExtractionThemeDecision(
                    theme_id="segment.thorax",
                    status="unclear",
                    confidence=0.6,
                    evidence=[],
                    rationale_short="Thorax may be reported.",
                ),
                ExtractionThemeDecision(
                    theme_id="segment.clavicle",
                    status="absent",
                    confidence=0.86,
                    evidence=[Evidence(page=2, quote="No clavicle model was used.", relevance="absence")],
                    rationale_short="Clavicle is absent.",
                ),
                ExtractionThemeDecision(
                    theme_id="joint.humerus_scapula",
                    status="absent",
                    confidence=0.88,
                    evidence=[],
                    rationale_short="Glenohumeral joint kinematics are absent.",
                ),
            ],
        )

        item_ids = item_ids_for_plan(plan)
        automatic = automatic_absent_answers(plan)

        self.assertIn("measurement_methods", item_ids)
        self.assertIn("thorax_used", item_ids)
        self.assertNotIn("clavicle_used", item_ids)
        self.assertTrue(any(answer.item_id == "clavicle_used" and answer.final_answer == "no" for answer in automatic))
        self.assertTrue(any(answer.item_id == "humerus_scapula_rotations" and answer.final_answer == "not_assessed" for answer in automatic))

    def test_extracted_answers_override_automatic_answers(self) -> None:
        automatic = [
            FinalAnswer(
                item_id="thorax_used",
                final_answer="no",
                extractor_answer="no",
                validator_status="auto_absent",
                extractor_confidence=0.8,
                validator_confidence=0.8,
                final_confidence=0.8,
                evidence=[],
                rationale_short="Automatic.",
                review_required=False,
            )
        ]
        extracted = [
            FinalAnswer(
                item_id="thorax_used",
                final_answer="yes",
                extractor_answer="yes",
                validator_status="agree",
                extractor_confidence=0.9,
                validator_confidence=0.9,
                final_confidence=0.9,
                evidence=[],
                rationale_short="Extracted.",
                review_required=False,
            )
        ]

        merged = merge_adaptive_answers(extracted, automatic)

        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0].final_answer, "yes")


if __name__ == "__main__":
    unittest.main()
