"""Analysis variables: single-response items stay categorical, multiple-response items become binary variables.

Protocol: "multiple-response items will be represented as separate binary variables". An item is multiple-response
when its form guidance says "Select all" (``measurement_methods`` and the ``*_details`` items for axes construction
and rotations). Binary variables are named ``<item_id>__<option>`` and coded 1/0.
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .form_schema import EXTRACTION_ITEMS, ExtractionItem
from .models import ArticleResult

SEP = "__"


@dataclass(frozen=True)
class Variable:
    name: str
    item_id: str
    theme: str
    option: str | None  # None for single-response (categorical) variables
    allowed: tuple[str, ...]

    @property
    def binary(self) -> bool:
        return self.option is not None


def is_multi_response(item: ExtractionItem) -> bool:
    return "select all" in item.guidance.lower()


def build_variables() -> list[Variable]:
    variables: list[Variable] = []
    for item in EXTRACTION_ITEMS:
        if is_multi_response(item):
            variables += [Variable(f"{item.id}{SEP}{opt}", item.id, item.theme, opt, ("0", "1")) for opt in item.allowed_answers]
        else:
            variables.append(Variable(item.id, item.id, item.theme, None, tuple(item.allowed_answers)))
    return variables


def result_to_row(result: ArticleResult) -> dict[str, str]:
    """One wide row for an article: categorical value or 0/1 per binary variable ('' when the item is missing)."""
    answers = {a.item_id: a.final_answer for a in result.answers}
    row: dict[str, str] = {"article_id": result.article_id}
    for var in build_variables():
        value = answers.get(var.item_id)
        if value is None:
            row[var.name] = ""
        elif var.binary:
            chosen = value if isinstance(value, list) else [value]
            row[var.name] = "1" if var.option in chosen else "0"
        else:
            row[var.name] = "|".join(sorted(value)) if isinstance(value, list) else value
    return row


def load_results(results_dir: Path) -> list[ArticleResult]:
    results = []
    for path in sorted(results_dir.glob("*.json")):
        if path.name in {"index.json"} or path.name.endswith(".screening.json"):
            continue
        result = ArticleResult.model_validate_json(path.read_text(encoding="utf-8"))
        result.article_id = path.stem
        results.append(result)
    return results


def write_wide_csv(rows: list[dict[str, str]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    columns = ["article_id", *(v.name for v in build_variables())]
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def read_wide_table(path: Path) -> dict[str, dict[str, str]]:
    """Read a wide CSV or XLSX (first sheet) keyed by article_id. Blank cells are kept as ''."""
    if path.suffix.lower() in {".xlsx", ".xlsm"}:
        from openpyxl import load_workbook

        sheet = load_workbook(path, read_only=True, data_only=True).worksheets[0]
        rows_iter = sheet.iter_rows(values_only=True)
        header = [str(c).strip() if c is not None else "" for c in next(rows_iter)]
        records = [dict(zip(header, ("" if c is None else _cell(c) for c in row))) for row in rows_iter]
    else:
        with path.open(newline="", encoding="utf-8-sig") as handle:
            records = list(csv.DictReader(handle))
    table: dict[str, dict[str, str]] = {}
    for record in records:
        article_id = (record.get("article_id") or "").strip()
        if article_id:
            table[article_id] = {k: (v or "").strip() for k, v in record.items() if k}
    return table


def _cell(value: Any) -> str:
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def main() -> None:
    parser = argparse.ArgumentParser(description="Export extraction JSON as a wide table with binary variables for multi-response items.")
    parser.add_argument("--results", type=Path, required=True, help="Folder of article JSON files.")
    parser.add_argument("--out", type=Path, default=None, help="Output CSV (default: <results>/binary.csv).")
    args = parser.parse_args()
    results = load_results(args.results)
    out = args.out or args.results / "binary.csv"
    write_wide_csv([result_to_row(r) for r in results], out)
    print(f"{len(results)} article(s), {len(build_variables())} variable(s) -> {out}")


if __name__ == "__main__":
    main()
