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

    def test_coding_rules_and_dont_know_option_are_in_the_form(self) -> None:
        prompt = extraction_form_prompt()

        self.assertIn("is an applicable explicit ISB claim", prompt)
        self.assertIn("typographical error is NOT a methodological departure", prompt)
        self.assertIn("ONLY when an alternative is directly described", prompt)
        self.assertIn("only once an axis (coordinate) system is constructed", prompt)
        origin = next(i for i in EXTRACTION_ITEMS if i.id == "scapula_scs_origin")
        self.assertIn("i_dont_know", origin.allowed_answers)
        rotations = next(i for i in EXTRACTION_ITEMS if i.id == "humerus_scapula_rotations")
        self.assertIn("i_dont_know", rotations.allowed_answers)
        self.assertIn("not_assessed", rotations.allowed_answers)

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


class ConsistencyRulesTests(unittest.TestCase):
    def _base(self):
        from review_extraction.form_schema import DETAIL_PARENTS, JOINTS

        answers = {detail: "not_applicable" for detail in DETAIL_PARENTS}
        answers.update({parent: "isb_explicit_no_method" for parent in DETAIL_PARENTS.values()})
        answers.update({f"{j}_reported": "yes" for j in JOINTS})
        answers.update({"humerus_axes_construction": "isb_explicit_no_method", "humerus_axes_construction_isb_option": "not_applicable"})
        return answers

    def test_consistent_answers_pass(self) -> None:
        from review_extraction.form_schema import consistency_errors

        self.assertEqual(consistency_errors(self._base()), [])

    def test_details_require_a_described_departure(self) -> None:
        from review_extraction.form_schema import consistency_errors

        answers = self._base()
        answers["scapula_axes_construction_details"] = ["anatomical_landmarks"]
        self.assertTrue(any("must be not_applicable" in e for e in consistency_errors(answers)))
        answers["scapula_axes_construction"] = "isb_not_followed_alternative_described"
        self.assertEqual(consistency_errors(answers), [])
        answers["scapula_axes_construction_details"] = "not_applicable"
        self.assertTrue(any("tick the applicable details" in e for e in consistency_errors(answers)))

    def test_humerus_option_live_condition(self) -> None:
        from review_extraction.form_schema import consistency_errors

        answers = self._base()
        answers["humerus_axes_construction_isb_option"] = "isb_option_1"
        self.assertTrue(any("humerus_axes_construction_isb_option" in e for e in consistency_errors(answers)))

    def test_unreported_joint_is_not_assessed(self) -> None:
        from review_extraction.form_schema import consistency_errors

        answers = self._base()
        answers["humerus_thorax_reported"] = "no"
        errors = consistency_errors(answers)
        self.assertIn("humerus_thorax_rotations: must be not_assessed because humerus_thorax_reported = no", errors)
