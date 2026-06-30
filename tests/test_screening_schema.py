import unittest

from review_extraction.screening_schema import SCREENING_CRITERIA, screening_prompt


class ScreeningSchemaTests(unittest.TestCase):
    def test_screening_criteria_match_full_paper_grid(self) -> None:
        criteria = {criterion.id: criterion for criterion in SCREENING_CRITERIA}

        self.assertEqual(set(criteria), {"population", "outcome", "study_design", "language"})
        self.assertIn("human", criteria["population"].include.lower())
        self.assertIn("animal", criteria["population"].exclude.lower())
        self.assertIn("shoulder", criteria["outcome"].include.lower())
        self.assertIn("reviews", criteria["study_design"].exclude.lower())
        self.assertIn("english", criteria["language"].include.lower())

    def test_screening_prompt_contains_overall_decision_rules(self) -> None:
        prompt = screening_prompt()

        self.assertIn("overall_decision='exclude'", prompt)
        self.assertIn("overall_decision='include'", prompt)
        self.assertIn("overall_decision='uncertain'", prompt)


if __name__ == "__main__":
    unittest.main()
