import json
import unittest
from types import SimpleNamespace

from review_extraction.openai_agents import DualAgentExtractor, OpenAIConfig, OpenAIQuotaError


class FakeResponses:
    def __init__(self, cached_tokens: int = 0) -> None:
        self.calls = []
        self.cached_tokens = cached_tokens

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
        elif schema_name == "extraction_plan_result":
            payload = {
                "article_id": "paper",
                "themes": [
                    {
                        "theme_id": "measurement_methods",
                        "status": "present",
                        "confidence": 0.9,
                        "evidence": [
                            {
                                "page": 1,
                                "quote": "Thorax markers were used.",
                                "relevance": "Measurement method and thorax segment are described.",
                            }
                        ],
                        "rationale_short": "Measurement method is reported.",
                    },
                    {
                        "theme_id": "segment.thorax",
                        "status": "present",
                        "confidence": 0.9,
                        "evidence": [
                            {
                                "page": 1,
                                "quote": "Thorax markers were used.",
                                "relevance": "Thorax segment is described.",
                            }
                        ],
                        "rationale_short": "Thorax segment is reported.",
                    },
                ],
            }
        elif schema_name == "study_metadata_result":
            payload = {
                "article_id": "paper",
                "fields": [
                    {
                        "field_id": "study_id",
                        "value": "Example2024",
                        "confidence": 0.9,
                        "evidence": [
                            {
                                "page": 1,
                                "quote": "Example title.",
                                "relevance": "Title page.",
                            }
                        ],
                        "rationale_short": "Study ID from title page.",
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
        return SimpleNamespace(
            output_text=json.dumps(payload),
            usage=SimpleNamespace(
                input_tokens=1000,
                output_tokens=100,
                total_tokens=1100,
                input_tokens_details=SimpleNamespace(cached_tokens=self.cached_tokens),
            ),
        )


class FakeClient:
    def __init__(self, cached_tokens: int = 0) -> None:
        self.responses = FakeResponses(cached_tokens=cached_tokens)


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
        agents = DualAgentExtractor(
            client=client,
            config=OpenAIConfig(
                model="extract-model",
                validator_model="validate-model",
                input_cost_per_million=1.0,
                output_cost_per_million=2.0,
                validator_input_cost_per_million=3.0,
                validator_output_cost_per_million=4.0,
            ),
        )

        screening = agents.screen("paper", "[PAGE 1]\nParticipants were adults.")
        screening_validation = agents.validate_screening("paper", "[PAGE 1]\nParticipants were adults.", screening)
        metadata = agents.extract_study_metadata("paper", "[PAGE 1]\nExample title.")
        extraction_plan = agents.plan_extraction("paper", "[PAGE 1]\nThorax markers were used.")
        extraction = agents.extract("paper", "[PAGE 1]\nThorax markers were used.", item_ids=["thorax_used"])
        validation = agents.validate("paper", "[PAGE 1]\nThorax markers were used.", extraction, item_ids=["thorax_used"])

        self.assertEqual(screening.overall_decision, "include")
        self.assertEqual(screening_validation.overall_status, "agree")
        self.assertEqual(metadata.fields[0].field_id, "study_id")
        self.assertEqual(extraction_plan.themes[0].theme_id, "measurement_methods")
        self.assertEqual(extraction.article_id, "paper")
        self.assertEqual(extraction.answers[0].item_id, "thorax_used")
        self.assertEqual(validation.decisions[0].status, "agree")
        self.assertEqual(client.responses.calls[0]["model"], "extract-model")
        self.assertEqual(client.responses.calls[1]["model"], "validate-model")
        self.assertEqual(client.responses.calls[2]["model"], "extract-model")
        self.assertEqual(client.responses.calls[3]["model"], "extract-model")
        self.assertEqual(client.responses.calls[4]["model"], "extract-model")
        self.assertEqual(client.responses.calls[5]["model"], "validate-model")
        self.assertTrue(all(call["text"]["format"]["strict"] for call in client.responses.calls))
        self.assertIn("Paper text follows", client.responses.calls[0]["input"][1]["content"])
        self.assertIn("Screener output to audit", client.responses.calls[1]["input"][1]["content"])
        self.assertIn("Extractor output to audit", client.responses.calls[5]["input"][1]["content"])
        self.assertEqual(
            [event.step for event in agents.usage_events],
            ["screening", "screening_validation", "study_metadata", "extraction_planning", "extraction", "extraction_validation"],
        )
        self.assertEqual(agents.usage_events[0].input_tokens, 1000)
        self.assertEqual(agents.usage_events[0].output_tokens, 100)
        self.assertEqual(agents.usage_events[0].estimated_cost_usd, 0.0012)
        self.assertEqual(agents.usage_events[1].model, "validate-model")
        self.assertEqual(agents.usage_events[1].estimated_cost_usd, 0.0034)

    def test_builtin_pricing_is_selected_from_model_name(self) -> None:
        client = FakeClient(cached_tokens=100)
        agents = DualAgentExtractor(
            client=client,
            config=OpenAIConfig(model="gpt-5.4-mini", validator_model="gpt-5.4-mini"),
        )

        agents.screen("paper", "[PAGE 1]\nParticipants were adults.")

        usage = agents.usage_events[0]
        self.assertEqual(usage.cached_input_tokens, 100)
        self.assertEqual(usage.input_cost_per_million, 0.8623125)
        self.assertEqual(usage.cached_input_cost_per_million, 0.08623125)
        self.assertEqual(usage.output_cost_per_million, 5.173875)
        self.assertEqual(usage.estimated_cost_usd, 0.001302)

    def test_insufficient_quota_raises_user_facing_error(self) -> None:
        agents = DualAgentExtractor(client=QuotaClient(), config=OpenAIConfig())

        with self.assertRaises(OpenAIQuotaError) as context:
            agents.screen("paper", "[PAGE 1]\nText")

        self.assertIn("quota exceeded", str(context.exception).lower())
        self.assertIn("rerun the same command", str(context.exception).lower())


if __name__ == "__main__":
    unittest.main()
