import json
import unittest
from types import SimpleNamespace

from review_extraction.openai_agents import DualAgentExtractor, OpenAIConfig


class FakeResponses:
    def __init__(self) -> None:
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        schema_name = kwargs["text"]["format"]["name"]
        if schema_name == "extraction_result":
            payload = {
                "article_id": "paper",
                "answers": [
                    {
                        "item_id": "thorax_used",
                        "answer": "yes",
                        "confidence": 0.8,
                        "evidence": [
                            {
                                "page": 1,
                                "quote": "Thorax markers were used.",
                                "relevance": "Shows thorax segment use.",
                            }
                        ],
                        "rationale_short": "The thorax is explicitly tracked.",
                        "needs_human_review": False,
                    }
                ],
            }
        elif schema_name == "validation_result":
            payload = {
                "article_id": "paper",
                "decisions": [
                    {
                        "item_id": "thorax_used",
                        "status": "agree",
                        "corrected_answer": None,
                        "confidence": 0.9,
                        "evidence": [],
                        "critique": "Supported by the provided quote.",
                    }
                ],
            }
        else:
            raise AssertionError(f"Unexpected schema: {schema_name}")
        return SimpleNamespace(output_text=json.dumps(payload))


class FakeClient:
    def __init__(self) -> None:
        self.responses = FakeResponses()


class OpenAIAgentTests(unittest.TestCase):
    def test_extract_and_validate_use_strict_json_schema(self) -> None:
        client = FakeClient()
        agents = DualAgentExtractor(client=client, config=OpenAIConfig(model="extract-model", validator_model="validate-model"))

        extraction = agents.extract("paper", "[PAGE 1]\nThorax markers were used.")
        validation = agents.validate("paper", "[PAGE 1]\nThorax markers were used.", extraction)

        self.assertEqual(extraction.article_id, "paper")
        self.assertEqual(extraction.answers[0].item_id, "thorax_used")
        self.assertEqual(validation.decisions[0].status, "agree")
        self.assertEqual(client.responses.calls[0]["model"], "extract-model")
        self.assertEqual(client.responses.calls[1]["model"], "validate-model")
        self.assertTrue(client.responses.calls[0]["text"]["format"]["strict"])
        self.assertTrue(client.responses.calls[1]["text"]["format"]["strict"])
        self.assertIn("Paper text follows", client.responses.calls[0]["input"][1]["content"])
        self.assertIn("Extractor output to audit", client.responses.calls[1]["input"][1]["content"])


if __name__ == "__main__":
    unittest.main()
