import unittest

from review_extraction.form_schema import EXPECTED_EULER, EXTRACTION_ITEMS, extraction_form_prompt, extraction_plan_prompt


class FormSchemaTests(unittest.TestCase):
    def test_form_contains_expected_number_of_items(self) -> None:
        self.assertEqual(len(EXTRACTION_ITEMS), 53)

    def test_all_item_ids_are_unique(self) -> None:
        item_ids = [item.id for item in EXTRACTION_ITEMS]
        self.assertEqual(len(item_ids), len(set(item_ids)))

    def test_expected_euler_sequences_are_encoded(self) -> None:
        self.assertEqual(EXPECTED_EULER["thorax_global"], "Z-X-Y")
        self.assertEqual(EXPECTED_EULER["clavicle_thorax"], "Y-X-Z")
        self.assertEqual(EXPECTED_EULER["scapula_thorax"], "Y-X-Z")
        self.assertEqual(EXPECTED_EULER["humerus_scapula"], "Y-X-Y")

    def test_prompt_includes_allowed_answers_and_uncertainty_guidance(self) -> None:
        prompt = extraction_form_prompt()

        self.assertIn("Use only allowed answer identifiers", prompt)
        self.assertIn("measurement_methods", prompt)
        self.assertIn("humerus_thorax_translations", prompt)
        self.assertIn("humerus_thorax_translation_details", prompt)
        self.assertIn("thorax_axes_orientation_details", prompt)
        self.assertIn("no_method_or_reference", prompt)
        self.assertIn("not_assessed", prompt)

    def test_prompt_can_be_limited_to_selected_items(self) -> None:
        prompt = extraction_form_prompt(item_ids={"thorax_used"})

        self.assertIn("thorax_used", prompt)
        self.assertNotIn("humerus_thorax_translations", prompt)

    def test_extraction_plan_prompt_lists_themes(self) -> None:
        prompt = extraction_plan_prompt()

        self.assertIn("segment.thorax", prompt)
        self.assertIn("joint.humerus_scapula", prompt)
        self.assertIn("present", prompt)
        self.assertIn("unclear", prompt)


if __name__ == "__main__":
    unittest.main()
