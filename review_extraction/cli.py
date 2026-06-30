from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .env import load_environment
from .openai_agents import DualAgentExtractor, OpenAIConfig, OpenAIRequestError


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Extract systematic-review parameters from PDF articles.")
    parser.add_argument("input", type=Path, help="PDF file or directory containing PDFs.")
    parser.add_argument("--out", type=Path, default=Path("outputs"), help="Output directory.")
    parser.add_argument("--model", default=None, help="OpenAI model for extraction.")
    parser.add_argument("--validator-model", default=None, help="OpenAI model for independent validation.")
    parser.add_argument("--no-highlight", action="store_true", help="Disable highlighted PDF output.")
    parser.add_argument("--force", action="store_true", help="Re-run AI extraction even when output JSON files already exist.")
    return parser


def main() -> None:
    load_environment()
    args = build_parser().parse_args()
    from .pipeline import process_many

    config = OpenAIConfig.from_env()
    if args.model:
        config.model = args.model
    if args.validator_model:
        config.validator_model = args.validator_model

    try:
        agents = DualAgentExtractor(config=config)
        results = process_many(
            args.input,
            args.out,
            agents,
            write_highlights=not args.no_highlight,
            reuse_existing=not args.force,
            progress=lambda message: print(message, flush=True),
        )
    except KeyboardInterrupt:
        print("\nInterrupted. Existing JSON outputs were kept; rerun the same command to resume.", file=sys.stderr)
        raise SystemExit(130)
    except OpenAIRequestError as exc:
        print(f"\n{exc}", file=sys.stderr)
        print("Fix the OpenAI account/key issue, then rerun the same command to resume from existing JSON.", file=sys.stderr)
        raise SystemExit(2)

    review_required = sum(1 for result in results for answer in result.answers if answer.review_required)
    total = sum(len(result.answers) for result in results)
    print(f"Processed {len(results)} PDF(s).")
    print(f"Answers requiring human review: {review_required}/{total}.")
    print(f"Outputs written to: {args.out.resolve()}")


if __name__ == "__main__":
    main()
