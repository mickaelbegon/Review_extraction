from __future__ import annotations

import argparse

from .pricing import BUILTIN_MODEL_PRICING, pricing_for_model, tax_rate_from_env


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Show built-in OpenAI model prices used for cost estimates.")
    parser.add_argument("--no-tax", action="store_true", help="Show prices before tax.")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    tax_rate = 0.0 if args.no_tax else tax_rate_from_env()
    print(f"Tax rate: {tax_rate:.5f}")
    print("Prices are USD per 1M tokens.")
    print("")
    print(f"{'model':<16} {'input':>12} {'cached_input':>15} {'output':>12}")
    print("-" * 59)
    for model in sorted(BUILTIN_MODEL_PRICING):
        pricing = pricing_for_model(model, tax_rate=tax_rate)
        assert pricing is not None
        print(
            f"{model:<16} "
            f"{pricing.input_with_tax:>12.6f} "
            f"{pricing.cached_input_with_tax:>15.6f} "
            f"{pricing.output_with_tax:>12.6f}"
        )


if __name__ == "__main__":
    main()
