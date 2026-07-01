import unittest

from review_extraction.models import (
    EXTRACTION_JSON_SCHEMA,
    SCREENING_JSON_SCHEMA,
    SCREENING_VALIDATION_JSON_SCHEMA,
    STUDY_METADATA_JSON_SCHEMA,
    VALIDATION_JSON_SCHEMA,
)


class OpenAISchemaTests(unittest.TestCase):
    def test_strict_schemas_require_every_declared_property(self) -> None:
        for schema in [
            SCREENING_JSON_SCHEMA,
            SCREENING_VALIDATION_JSON_SCHEMA,
            STUDY_METADATA_JSON_SCHEMA,
            EXTRACTION_JSON_SCHEMA,
            VALIDATION_JSON_SCHEMA,
        ]:
            with self.subTest(schema=schema["title"]):
                self._assert_required_matches_properties(schema)
                self._assert_no_defaults(schema)

    def test_evidence_page_is_required_but_nullable(self) -> None:
        evidence_schema = SCREENING_JSON_SCHEMA["$defs"]["Evidence"]

        self.assertIn("page", evidence_schema["required"])
        self.assertEqual(evidence_schema["properties"]["page"]["anyOf"][1]["type"], "null")

    def _assert_required_matches_properties(self, node: object) -> None:
        if isinstance(node, dict):
            properties = node.get("properties")
            if isinstance(properties, dict):
                self.assertEqual(set(node.get("required", [])), set(properties))
                self.assertFalse(node.get("additionalProperties"))
            for value in node.values():
                self._assert_required_matches_properties(value)
        elif isinstance(node, list):
            for value in node:
                self._assert_required_matches_properties(value)

    def _assert_no_defaults(self, node: object) -> None:
        if isinstance(node, dict):
            self.assertNotIn("default", node)
            for value in node.values():
                self._assert_no_defaults(value)
        elif isinstance(node, list):
            for value in node:
                self._assert_no_defaults(value)


if __name__ == "__main__":
    unittest.main()
