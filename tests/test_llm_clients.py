import json
import unittest
from types import SimpleNamespace

from review_extraction.llm_clients import AnthropicApiClient, LLMRequestError, parse_cli_output
from review_extraction.openai_agents import DualAgentExtractor, OpenAIConfig

SCREENING = {"article_id": "x", "overall_decision": "include", "criteria": []}


class ParseCliOutputTests(unittest.TestCase):
    def test_structured_output_and_usage(self) -> None:
        out = json.dumps({
            "is_error": False,
            "structured_output": {"a": 1},
            "usage": {"input_tokens": 10, "cache_read_input_tokens": 5, "cache_creation_input_tokens": 2, "output_tokens": 7},
        })
        response = parse_cli_output(out, 0)
        self.assertEqual(json.loads(response.output_text), {"a": 1})
        self.assertEqual(response.usage.input_tokens, 17)
        self.assertEqual(response.usage.input_tokens_details.cached_tokens, 5)
        self.assertEqual(response.usage.total_tokens, 24)

    def test_falls_back_to_result_text(self) -> None:
        response = parse_cli_output(json.dumps({"result": '{"a": 2}'}), 0)
        self.assertEqual(json.loads(response.output_text), {"a": 2})

    def test_login_error_has_hint(self) -> None:
        with self.assertRaisesRegex(LLMRequestError, "/login"):
            parse_cli_output(json.dumps({"is_error": True, "result": "Not logged in"}), 1)

    def test_limit_error_has_hint(self) -> None:
        with self.assertRaisesRegex(LLMRequestError, "limit reached"):
            parse_cli_output(json.dumps({"is_error": True, "result": "Usage limit reached"}), 1)


class DualAgentWithClaudeShimTests(unittest.TestCase):
    def test_anthropic_client_drives_screening(self) -> None:
        calls = {}

        def create(**kwargs):
            calls.update(kwargs)
            return SimpleNamespace(
                content=[SimpleNamespace(type="tool_use", input=SCREENING)],
                usage=SimpleNamespace(input_tokens=100, output_tokens=20),
            )

        sdk = SimpleNamespace(messages=SimpleNamespace(create=create))
        agents = DualAgentExtractor(client=AnthropicApiClient(client=sdk), config=OpenAIConfig(model="claude-sonnet-5-5"))
        result = agents.screen("x", "paper text")
        self.assertEqual(result.overall_decision, "include")
        self.assertEqual(calls["tool_choice"]["name"], "return_result")
        self.assertEqual(agents.usage_events[0].input_tokens, 100)


if __name__ == "__main__":
    unittest.main()
