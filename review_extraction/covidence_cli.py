from __future__ import annotations

import argparse
from pathlib import Path

from .covidence import export_results, import_pdfs


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Move PDFs and review results between Covidence-style exports and this project.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    import_parser = subparsers.add_parser("import-pdfs", help="Copy PDFs from a Covidence download/export folder or ZIP.")
    import_parser.add_argument("source", type=Path, help="Covidence folder or ZIP containing PDFs.")
    import_parser.add_argument("--out", type=Path, default=Path("pdf_input"), help="Destination PDF input directory.")
    import_parser.add_argument("--manifest", type=Path, default=None, help="Optional CSV manifest path.")

    export_parser = subparsers.add_parser("export-results", help="Export review-extraction JSON outputs for Covidence/manual upload.")
    export_parser.add_argument("--results", type=Path, default=Path("outputs"), help="Directory containing review-extraction JSON outputs.")
    export_parser.add_argument("--out", type=Path, default=Path("covidence_export"), help="Destination directory for CSV/XLSX files.")

    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.command == "import-pdfs":
        summary = import_pdfs(args.source, args.out, manifest_path=args.manifest)
        print(f"Copied PDFs: {summary.copied}")
        print(f"Skipped existing PDFs: {summary.skipped}")
        print(f"Manifest: {summary.manifest_path.resolve()}")
        print(f"PDF input directory: {args.out.resolve()}")
        return
    if args.command == "export-results":
        summary = export_results(args.results, args.out)
        print(f"Articles exported: {summary.articles}")
        print(f"Screening CSV: {summary.screening_csv.resolve()}")
        print(f"Extraction CSV: {summary.extraction_csv.resolve()}")
        print(f"Workbook: {summary.workbook_path.resolve()}")
        return
    raise SystemExit(f"Unknown command: {args.command}")


if __name__ == "__main__":
    main()
