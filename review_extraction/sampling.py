"""Stratified validation sample + a priori development/tuning/test split + blinded human extraction templates.

Protocol: a stratified random 10% sample of the included articles is extracted independently by two blinded human
reviewers, and partitioned BEFORE any prompt refinement into development (~40), tuning (~30) and held-out test (~100)
subsets (proportions scaled when the sample size differs from 170). Everything is seeded and written to a manifest;
an existing sample is never overwritten without --force, so the split stays a priori.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import random
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from .form_schema import EXTRACTION_ITEMS
from .variables import build_variables, load_results

SUBSETS = ("development", "tuning", "test")


def largest_remainder(total: int, weights: dict[str, float], rng: random.Random) -> dict[str, int]:
    """Apportion ``total`` units proportionally to weights (Hamilton), random tie-break."""
    weight_sum = sum(weights.values())
    exact = {k: total * w / weight_sum for k, w in weights.items()}
    counts = {k: int(math.floor(v)) for k, v in exact.items()}
    leftovers = sorted(exact, key=lambda k: (exact[k] - counts[k], rng.random()), reverse=True)
    for k in leftovers[: total - sum(counts.values())]:
        counts[k] += 1
    return counts


def candidates_from_pdfs(folder: Path) -> list[dict[str, str]]:
    rows = []
    for pdf in sorted(folder.glob("*.pdf")):
        match = re.search(r"(?<!\d)((?:19|20)\d{2})(?!\d)", pdf.stem)
        rows.append({"article_id": pdf.stem, "year": match.group(1) if match else ""})
    return rows


def candidates_from_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return [dict(r) for r in csv.DictReader(handle)]


def add_metadata_from_results(rows: list[dict[str, str]], results_dir: Path) -> None:
    results = {r.article_id: r for r in load_results(results_dir)}
    for row in rows:
        result = results.get(row["article_id"])
        if result:
            for field in result.study_metadata:
                row.setdefault(field.field_id, field.value)


def add_year_bin(rows: list[dict[str, str]]) -> None:
    for row in rows:
        year = (row.get("year") or "").strip()
        row["year_bin"] = f"{int(year) // 10 * 10}s" if year.isdigit() else "NA"


def stratified_sample(
    rows: list[dict[str, str]], *, n: int, strata_cols: list[str], seed: int
) -> list[dict[str, str]]:
    rng = random.Random(seed)
    strata: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in sorted(rows, key=lambda r: r["article_id"]):
        key = " | ".join(f"{c}={row.get(c) or 'NA'}" for c in strata_cols) or "all"
        strata[key].append(row)
    counts = largest_remainder(n, {k: float(len(v)) for k, v in strata.items()}, rng)
    chosen: list[dict[str, str]] = []
    for key in sorted(strata):
        members = list(strata[key])
        rng.shuffle(members)
        for row in members[: min(counts[key], len(members))]:
            chosen.append({**row, "stratum": key})
    return chosen


def assign_subsets(sample: list[dict[str, str]], sizes: dict[str, int], seed: int) -> list[dict[str, str]]:
    """Deal articles (ordered by stratum, shuffled inside) to subsets by error diffusion so each subset keeps the
    stratum mix; exact subset sizes are enforced."""
    rng = random.Random(f"{seed}:subsets")
    ordered = sorted(sample, key=lambda r: (r["stratum"], rng.random()))
    total = sum(sizes.values())
    assigned = {s: 0 for s in sizes}
    for position, row in enumerate(ordered, start=1):
        open_subsets = [s for s in sizes if assigned[s] < sizes[s]]
        chosen = max(open_subsets, key=lambda s: sizes[s] / total * position - assigned[s])
        assigned[chosen] += 1
        row["subset"] = chosen
    return ordered


def subset_sizes(n: int, ratio: tuple[int, int, int], seed: int) -> dict[str, int]:
    rng = random.Random(f"{seed}:sizes")
    return largest_remainder(n, dict(zip(SUBSETS, map(float, ratio))), rng)


def write_template(path: Path, article_ids: list[str]) -> None:
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill
    from openpyxl.utils import get_column_letter
    from openpyxl.worksheet.datavalidation import DataValidation

    items = {i.id: i for i in EXTRACTION_ITEMS}
    variables = build_variables()
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Extraction"
    lists = workbook.create_sheet("Lists")
    codebook = workbook.create_sheet("Codebook")

    list_ref: dict[str, str] = {}
    for col, item in enumerate((i for i in EXTRACTION_ITEMS if i.id in {v.item_id for v in variables if not v.binary}), start=1):
        lists.cell(row=1, column=col, value=item.id)
        for r, option in enumerate(item.allowed_answers, start=2):
            lists.cell(row=r, column=col, value=option)
        letter = get_column_letter(col)
        list_ref[item.id] = f"=Lists!${letter}$2:${letter}${len(item.allowed_answers) + 1}"

    header = ["article_id", *(v.name for v in variables)]
    sheet.append(header)
    for cell in sheet[1]:
        cell.font = Font(bold=True)
        cell.fill = PatternFill("solid", fgColor="DDEBF7")
    for article_id in article_ids:
        sheet.append([article_id])
    last_row = len(article_ids) + 1
    binary_dv = DataValidation(type="list", formula1='"0,1"', allow_blank=True)
    sheet.add_data_validation(binary_dv)
    for col, var in enumerate(variables, start=2):
        letter = get_column_letter(col)
        rng = f"{letter}2:{letter}{last_row}"
        if var.binary:
            binary_dv.add(rng)
        else:
            dv = DataValidation(type="list", formula1=list_ref[var.item_id], allow_blank=True)
            sheet.add_data_validation(dv)
            dv.add(rng)
    sheet.freeze_panes = "B2"
    sheet.column_dimensions["A"].width = 40

    codebook.append(["variable", "domain", "type", "question", "allowed answers", "guidance"])
    for var in variables:
        item = items[var.item_id]
        codebook.append(
            [
                var.name,
                var.theme,
                "binary 0/1 (tick every option that applies)" if var.binary else "single choice",
                item.question,
                "0, 1" if var.binary else ", ".join(item.allowed_answers),
                item.guidance,
            ]
        )
    for cell in codebook[1]:
        cell.font = Font(bold=True)
    workbook.save(path)


def main() -> None:
    parser = argparse.ArgumentParser(description="Stratified validation sample, a priori 40/30/100 split and blinded human templates.")
    parser.add_argument("input", type=Path, help="Folder of PDFs (included articles) or CSV with article_id and optional strata columns.")
    parser.add_argument("--out", type=Path, default=Path("validation_study"))
    parser.add_argument("--fraction", type=float, default=0.10, help="Sample fraction (default 0.10).")
    parser.add_argument("--n", type=int, default=None, help="Explicit sample size (overrides --fraction).")
    parser.add_argument("--split", default="40,30,100", help="development,tuning,test proportions (default 40,30,100).")
    parser.add_argument("--strata-cols", default="year_bin", help="Comma-separated stratification columns (default year_bin; '' for none).")
    parser.add_argument("--results", type=Path, default=None, help="Optional extraction JSON folder to add study metadata columns for stratification.")
    parser.add_argument("--seed", type=int, default=20260101)
    parser.add_argument("--force", action="store_true", help="Overwrite an existing sample (breaks the a priori split: avoid).")
    args = parser.parse_args()

    sample_path = args.out / "validation_sample.csv"
    if sample_path.exists() and not args.force:
        sys.exit(f"{sample_path} already exists: the split is defined a priori and is not redrawn. Use --force only before any prompt work.")

    rows = candidates_from_pdfs(args.input) if args.input.is_dir() else candidates_from_csv(args.input)
    if not rows:
        sys.exit("No candidate articles found.")
    if not any("year_bin" in r for r in rows):
        add_year_bin(rows)
    if args.results:
        add_metadata_from_results(rows, args.results)
    strata_cols = [c for c in args.strata_cols.split(",") if c]
    missing = [c for c in strata_cols if c not in rows[0]]
    if missing:
        sys.exit(f"Unknown strata column(s): {missing}. Available: {sorted(rows[0])}")

    n = args.n if args.n is not None else round(args.fraction * len(rows))
    ratio = tuple(int(x) for x in args.split.split(","))
    if len(ratio) != 3 or n < 3 or n > len(rows):
        sys.exit("Invalid --split or sample size.")
    sizes = subset_sizes(n, ratio, args.seed)
    sample = assign_subsets(stratified_sample(rows, n=n, strata_cols=strata_cols, seed=args.seed), sizes, args.seed)

    args.out.mkdir(parents=True, exist_ok=True)
    columns = ["article_id", "subset", "stratum", *strata_cols]
    with sample_path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(sorted(sample, key=lambda r: (r["subset"], r["article_id"])))
    ids = sorted(r["article_id"] for r in sample)
    for rater in ("A", "B"):
        write_template(args.out / f"human_extraction_rater_{rater}.xlsx", ids)
    manifest = {
        "created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "seed": args.seed,
        "population_size": len(rows),
        "population_ids_sha256": hashlib.sha256("\n".join(sorted(r["article_id"] for r in rows)).encode()).hexdigest(),
        "sample_size": n,
        "fraction": n / len(rows),
        "strata_cols": strata_cols,
        "split_ratio": dict(zip(SUBSETS, ratio)),
        "subset_sizes": sizes,
        "python": sys.version.split()[0],
    }
    (args.out / "sample_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"Population {len(rows)} -> sample {n}: " + ", ".join(f"{k}={v}" for k, v in sizes.items()))
    print(f"Wrote {sample_path}, 2 blinded rater templates and sample_manifest.json in {args.out}")


if __name__ == "__main__":
    main()
