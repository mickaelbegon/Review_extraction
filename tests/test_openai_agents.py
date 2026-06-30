import json
import unittest
from types import SimpleNamespace

from review_extraction.openai_agents import DualAgentExtractor, OpenAIConfig, OpenAIQuotaError


class FakeResponses:
    def __init__(self) -> None:
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        schema_name = kwargs["text"]["format"]["name"]
        if schema_name == "screening_result":
            payload = {
                "article_id": "paper",
                "overall_decision": "include",
                "criteria": [
                    {
                        "criterion_id": "population",
                        "decision": "include",
                        "confidence": 0.9,
                        "evidence": [
                            {
                                "page": 1,
                                "quote": "Participants were adults.",
                                "relevance": "Human population.",
                            }
                        ],
                        "rationale_short": "Human participants are described.",
                    }
                ],
            }
        elif schema_name == "screening_validation_result":
            payload = {
                "article_id": "paper",
                "overall_status": "agree",
                "corrected_overall_decision": None,
                "decisions": [
                    {
                        "criterion_id": "population",
                        "status": "agree",
                        "corrected_decision": None,
                        "confidence": 0.9,
                        "evidence": [],
                        "critique": "Supported.",
                    }
                ],
            }
        elif schema_name == "extraction_result":
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


class FakeQuotaError(Exception):
    body = {
        "message": "You exceeded your current quota, please check your plan and billing details.",
        "code": "insufficient_quota",
    }


class QuotaResponses:
    def create(self, **kwargs):
        raise FakeQuotaError("quota")


class QuotaClient:
    def __init__(self) -> None:
        self.responses = QuotaResponses()


class OpenAIAgentTests(unittest.TestCase):
    def test_extract_and_validate_use_strict_json_schema(self) -> None:
        client = FakeClient()
        agents = DualAgentExtractor(client=client, config=OpenAIConfig(model="extract-model", validator_model="validate-model"))

        screening = agents.screen("paper", "[PAGE 1]\nParticipants were adults.")
        screening_validation = agents.validate_screening("paper", "[PAGE 1]\nParticipants were adults.", screening)
        extraction = agents.extract("paper", "[PAGE 1]\nThorax markers were used.")
        validation = agents.validate("paper", "[PAGE 1]\nThorax markers were used.", extraction)

        self.assertEqual(screening.overall_decision, "include")
        self.assertEqual(screening_validation.overall_status, "agree")
        self.assertEqual(extraction.article_id, "paper")
        self.assertEqual(extraction.answers[0].item_id, "thorax_used")
        self.assertEqual(validation.decisions[0].status, "agree")
        self.assertEqual(client.responses.calls[0]["model"], "extract-model")
        self.assertEqual(client.responses.calls[1]["model"], "validate-model")
        self.assertEqual(client.responses.calls[2]["model"], "extract-model")
        self.assertEqual(client.responses.calls[3]["model"], "validate-model")
        self.assertTrue(all(call["text"]["format"]["strict"] for call in client.responses.calls))
        self.assertIn("Paper text follows", client.responses.calls[0]["input"][1]["content"])
        self.assertIn("Screener output to audit", client.responses.calls[1]["input"][1]["content"])
        self.assertIn("Extractor output to audit", client.responses.calls[3]["input"][1]["content"])

    def test_insufficient_quota_raises_user_facing_error(self) -> None:
        agents = DualAgentExtractor(client=QuotaClient(), config=OpenAIConfig())

        with self.assertRaises(OpenAIQuotaError) as context:
            agents.screen("paper", "[PAGE 1]\nText")

        self.assertIn("quota exceeded", str(context.exception).lower())
        self.assertIn("rerun the same command", str(context.exception).lower())


if __name__ == "__main__":
    unittest.main()
