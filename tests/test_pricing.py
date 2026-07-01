import unittest

from review_extraction.pricing import DEFAULT_TAX_RATE, pricing_for_model


class PricingTests(unittest.TestCase):
    def test_pricing_for_model_applies_default_quebec_tax(self) -> None:
        pricing = pricing_for_model("gpt-5.4-mini")

        self.assertIsNotNone(pricing)
        assert pricing is not None
        self.assertEqual(pricing.input_cost_per_million, 0.75)
        self.assertEqual(pricing.cached_input_cost_per_million, 0.075)
        self.assertEqual(pricing.output_cost_per_million, 4.50)
        self.assertEqual(pricing.tax_rate, DEFAULT_TAX_RATE)
        self.assertEqual(pricing.input_with_tax, 0.8623125)
        self.assertEqual(pricing.cached_input_with_tax, 0.08623125)
        self.assertEqual(pricing.output_with_tax, 5.173875)

    def test_unknown_model_has_no_builtin_pricing(self) -> None:
        self.assertIsNone(pricing_for_model("custom-model"))


if __name__ == "__main__":
    unittest.main()
