from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .benchmark import (
    compare_model_results,
    load_reference_results,
    safe_model_dir_name,
    summarize_benchmarks,
    write_benchmark_reports,
)
from .env import load_environment
from .models import ArticleResult
from .openai_agents import DualAgentExtractor, OpenAIConfig, OpenAIRequestError


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Benchmark candidate OpenAI models against existing 5.5 reference JSON outputs."
    )
    parser.add_argument("input", type=Path, help="PDF file or directory containing PDFs.")
    parser.add_argument("--reference-out", type=Path, default=Path("outputs"), help="Directory containing 5.5 reference JSON outputs.")
    parser.add_argument("--out", type=Path, default=Path("benchmark_outputs"), help="Benchmark output directory.")
    parser.add_argument(
        "--models",
        nargs="+",
        default=["gpt-5.4", "gpt-5.4-mini"],
        help="Candidate models to test. Each candidate is used for extraction and validation.",
    )
    parser.add_argument("--limit", type=int, default=None, help="Optional number of PDFs to test.")
    parser.add_argument("--force", action="store_true", help="Re-run candidate model outputs even when JSON exists.")
    parser.add_argument("--compare-only", action="store_true", help="Do not call OpenAI; compare existing candidate JSON outputs only.")
    parser.add_argument("--highlight", action="store_true", help="Also write highlighted candidate PDFs.")
    return parser


def main() -> None:
    load_environment()
    args = build_parser().parse_args()
    from .pipeline import process_pdf

    reference_results = load_reference_results(args.reference_out)
    if not reference_results:
        print(f"No reference JSON outputs found in {args.reference_out.resolve()}.", file=sys.stderr)
        raise SystemExit(2)

    pdfs = _pdfs_for_reference(args.input, reference_results, limit=args.limit)
    if not pdfs:
        print("No matching PDFs found for the reference JSON outputs.", file=sys.stderr)
        raise SystemExit(2)

    benchmarks = []
    try:
        for model in args.models:
            model_dir = args.out / safe_model_dir_name(model)
            print(f"\n=== Benchmark {model} -> {model_dir} ===", flush=True)
            if args.compare_only:
                results = _load_existing_candidate_results(model_dir)
            else:
                config = OpenAIConfig.from_env()
                config.model = model
                config.validator_model = model
                agents = DualAgentExtractor(config=config)
                results = []
                for current, pdf in enumerate(pdfs, start=1):
                    results.append(
                        process_pdf(
                            pdf,
                            model_dir,
                            agents,
                            write_highlights=args.highlight,
                            reuse_existing=not args.force,
                            progress=lambda message: print(message, flush=True),
                            current=current,
                            total=len(pdfs),
                        )
                    )
            benchmark = compare_model_results(
                model=model,
                reference_results=reference_results,
                candidate_results=results,
            )
            benchmarks.append(benchmark)
            _print_model_summary(benchmark)
    except KeyboardInterrupt:
        print("\nInterrupted. Existing candidate JSON outputs were kept; rerun to resume.", file=sys.stderr)
        raise SystemExit(130)
    except OpenAIRequestError as exc:
        print(f"\n{exc}", file=sys.stderr)
        print("Fix the OpenAI account/key issue, then rerun this benchmark to resume.", file=sys.stderr)
        raise SystemExit(2)

    write_benchmark_reports(benchmarks, args.out)
    print(f"\nBenchmark reports written to: {args.out.resolve()}")


def _pdfs_for_reference(input_path: Path, reference_results: dict[str, ArticleResult], *, limit: int | None) -> list[Path]:
    candidates = sorted(input_path.glob("*.pdf")) if input_path.is_dir() else [input_path]
    pdfs = [pdf for pdf in candidates if pdf.suffix.lower() == ".pdf" and pdf.stem in reference_results]
    if limit is not None:
        return pdfs[:limit]
    return pdfs


def _load_existing_candidate_results(model_dir: Path) -> list[ArticleResult]:
    results: list[ArticleResult] = []
    for json_path in sorted(model_dir.glob("*.json")):
        if json_path.name.endswith(".screening.json") or json_path.name in {"index.json"}:
            continue
        result = ArticleResult.model_validate_json(json_path.read_text(encoding="utf-8"))
        result.article_id = json_path.stem
        results.append(result)
    return results


def _print_model_summary(benchmark: object) -> None:
    summary = summarize_benchmarks([benchmark])[0]
    print(
        "Summary: "
        f"articles={summary['articles']}, "
        f"screening_agreement={summary['screening_agreement_rate']}, "
        f"answer_agreement={summary['answer_agreement_rate']}, "
        f"disagreements={summary['disagreements']}, "
        f"tokens={summary['candidate_total_tokens']}, "
        f"cost={summary['candidate_estimated_cost_usd']}",
        flush=True,
    )


if __name__ == "__main__":
    main()
