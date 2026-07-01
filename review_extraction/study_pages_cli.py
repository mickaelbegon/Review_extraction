from __future__ import annotations

import argparse
from pathlib import Path

from .study_pages import load_article_results, write_study_page_workbooks


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Create Covidence-like one-page-per-study Excel workbooks from existing article JSON outputs.")
    parser.add_argument("--results", type=Path, default=Path("outputs"), help="Directory containing article JSON outputs.")
    parser.add_argument("--out", type=Path, default=Path("study_pages"), help="Output directory for formatted workbook(s).")
    parser.add_argument("--split-by-letter", action="store_true", help="Write one workbook per first study-ID letter.")
    parser.add_argument(
        "--choice-format",
        action="store_true",
        help="Write a clearer choice-based workbook: screening first, then study data and Word-form items with evidence columns.",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    results = load_article_results(args.results)
    paths = write_study_page_workbooks(
        results,
        args.out,
        split_by_letter=args.split_by_letter,
        choice_format=args.choice_format,
    )
    print(f"Loaded {len(results)} study result(s).")
    for path in paths:
        print(f"Wrote {path.resolve()}")


if __name__ == "__main__":
    main()
