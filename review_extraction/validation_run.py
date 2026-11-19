"""Validation run on the stratified sample: match the PDFs to the sample ids, then export the AI extraction workbook.

- ``match``: finds the PDF of every sampled article in a folder of PDFs named like Zotero/Covidence exports
  (``Author et al. - 2012 - Title.pdf`` or ``Author-2015-Title.pdf``), checks the title, and copies it as
  ``<article_id>.pdf`` into a local work folder. The source PDFs are never renamed or modified.
- ``export``: builds ``ai_extraction.xlsx`` with the same ``Extraction`` sheet as the human rater templates
  (so ``review-agreement`` compares them directly), plus the answers to review, all evidence, and study metadata
  (bibliographic data from Covidence, author affiliations extracted by the agent, journal class when available).
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import re
import shutil
import sys
import unicodedata
from pathlib import Path

from .models import ArticleResult
from .study_metadata_schema import STUDY_METADATA_ITEMS
from .variables import build_variables, result_to_row

FILENAME_RE = re.compile(r"^(?P<author>.+?)\s*-\s*(?P<year>\d{4})\s*-\s*(?P<title>.+?)(?:\s*\(\d+\))?\.pdf$", re.IGNORECASE)
BIBLIO_COLUMNS = ["Study", "Authors", "Title", "Published Year", "Journal", "DOI"]


def norm(text: str) -> str:
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]", "", text.lower())


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def parse_filename(name: str) -> dict[str, str] | None:
    match = FILENAME_RE.match(name)
    if not match:
        return None
    author = match["author"].replace(" et al.", "").split(",")[0].strip()
    return {"author": norm(author.split()[0]) if author else "", "year": match["year"], "title": norm(match["title"])}


def title_matches(csv_title: str, file_title: str) -> bool:
    """File names keep a truncated title: the file title must be a prefix of the Covidence title (both normalized)."""
    if len(file_title) < 10:
        return False
    return csv_title.startswith(file_title[:60]) or file_title.startswith(csv_title[:60])


def _first_pages_text(pdf: Path, pages: int = 2) -> str:
    import fitz

    try:
        with fitz.open(pdf) as doc:
            return norm(" ".join(doc[i].get_text("text") for i in range(min(pages, len(doc)))))
    except Exception:  # noqa: BLE001 - unreadable PDF: simply not a match
        return ""


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def match_pdfs(sample: list[dict[str, str]], studies: dict[str, dict[str, str]], pdf_dir: Path) -> list[dict[str, str]]:
    pdfs = sorted(p for p in pdf_dir.iterdir() if p.suffix.lower() == ".pdf")
    parsed = {p: parse_filename(p.name) for p in pdfs}
    rows = []
    for record in sample:
        article_id = record["article_id"]
        study = studies[article_id]
        title = norm(study["Title"])
        year = str(study.get("Published Year", "")).strip()
        surname = norm(study.get("Study", "").split()[0]) if study.get("Study") else ""
        candidates = [p for p, info in parsed.items() if info and title_matches(title, info["title"])]
        if len(candidates) > 1:  # prefer same year, then same first author
            narrowed = [p for p in candidates if parsed[p]["year"] == year] or candidates
            narrowed = [p for p in narrowed if parsed[p]["author"] == surname] or narrowed
            candidates = narrowed
        if len(candidates) > 1 and len({_digest(p) for p in candidates}) == 1:
            candidates = candidates[:1]  # identical copies such as "Title (1).pdf"
        if len(candidates) > 1:  # different files with the same name pattern: check the printed title
            candidates = [p for p in candidates if title[:50] in _first_pages_text(p)] or candidates
        method = "filename"
        if not candidates:  # odd file name: look for the title on the first pages of every PDF of that year
            candidates = [p for p, info in parsed.items() if (not info or info["year"] == year) and title[:50] in _first_pages_text(p)]
            method = "pdf_text"
        status = "matched" if len(candidates) == 1 else ("ambiguous" if candidates else "not_found")
        rows.append(
            {
                "article_id": article_id,
                "status": status,
                "method": method if candidates else "",
                "pdf_file": " | ".join(p.name for p in candidates),
                "covidence_title": study["Title"],
            }
        )
    return rows


def copy_matched(rows: list[dict[str, str]], pdf_dir: Path, dest: Path) -> int:
    dest.mkdir(parents=True, exist_ok=True)
    copied = 0
    for row in rows:
        if row["status"] == "matched":
            target = dest / f"{row['article_id']}.pdf"
            if not target.exists():
                shutil.copy2(pdf_dir / row["pdf_file"], target)
            copied += 1
    return copied


def load_result(path: Path) -> ArticleResult:
    return ArticleResult.model_validate_json(path.read_text(encoding="utf-8"))


def export_workbook(
    results_dir: Path,
    sample: list[dict[str, str]],
    studies: dict[str, dict[str, str]],
    out: Path,
    journals: dict[str, dict[str, str]] | None = None,
) -> dict[str, int]:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill

    variables = build_variables()
    results = {}
    for record in sample:
        path = results_dir / f"{record['article_id']}.json"
        if path.exists():
            results[record["article_id"]] = load_result(path)

    workbook = Workbook()
    extraction = workbook.active
    extraction.title = "Extraction"
    extraction.append(["article_id", "study_label", *(v.name for v in variables)])
    for record in sample:
        result = results.get(record["article_id"])
        row = result_to_row(result) if result else {}
        extraction.append([record["article_id"], record.get("label", ""), *(row.get(v.name, "") for v in variables)])

    review = workbook.create_sheet("To review")
    evidence = workbook.create_sheet("Evidence")
    header = ["article_id", "item_id", "answer", "confidence", "review_required", "page", "quote", "relevance", "rationale"]
    review.append(header)
    evidence.append(header)
    for article_id, result in results.items():
        for answer in result.answers:
            value = "; ".join(answer.final_answer) if isinstance(answer.final_answer, list) else answer.final_answer
            quotes = answer.evidence or [None]
            for ev in quotes:
                line = [
                    article_id,
                    answer.item_id,
                    value,
                    answer.final_confidence,
                    "yes" if answer.review_required else "",
                    ev.page if ev else "",
                    ev.quote if ev else "",
                    ev.relevance if ev else "",
                    answer.rationale_short,
                ]
                if ev or answer.review_required:
                    evidence.append(line)
                if answer.review_required:
                    review.append(line)

    meta = workbook.create_sheet("Study metadata")
    meta_ids = [m.id for m in STUDY_METADATA_ITEMS]
    meta.append(["article_id", "subset", *BIBLIO_COLUMNS, "journal_class", *meta_ids])
    for record in sample:
        study = studies.get(record["article_id"], {})
        result = results.get(record["article_id"])
        values = {m.field_id: m.value for m in result.study_metadata} if result else {}
        journal_class = (journals or {}).get(study.get("Journal", "").strip().upper(), {}).get("journal_class", "")
        meta.append(
            [record["article_id"], record.get("subset", ""), *(study.get(c, "") for c in BIBLIO_COLUMNS), journal_class,
             *(values.get(i, "") for i in meta_ids)]
        )

    head_fill = PatternFill("solid", fgColor="DDEBF7")
    for sheet, width in ((extraction, 16), (review, 22), (evidence, 22), (meta, 24)):
        for cell in sheet[1]:
            cell.font = Font(bold=True)
            cell.fill = head_fill
        for column in sheet.columns:
            sheet.column_dimensions[column[0].column_letter].width = width
        sheet.freeze_panes = "C2"
    for sheet in (review, evidence):
        sheet.column_dimensions["G"].width = 70
        sheet.column_dimensions["I"].width = 70
        for row in sheet.iter_rows(min_row=2):
            for cell in row:
                cell.alignment = Alignment(wrap_text=True, vertical="top")
    out.parent.mkdir(parents=True, exist_ok=True)
    workbook.save(out)
    flagged = sum(a.review_required for r in results.values() for a in r.answers)
    return {"articles": len(sample), "extracted": len(results), "flagged_answers": flagged}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validation run: match sample PDFs and export the AI extraction workbook.")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("match", "export"):
        p = sub.add_parser(name)
        p.add_argument("--sample", type=Path, default=Path("validation_study/validation_sample.csv"))
        p.add_argument("--studies", type=Path, default=Path("validation_study/included_studies.csv"))
    m = sub.choices["match"]
    m.add_argument("--pdf-dir", type=Path, required=True, help="Folder holding all included PDFs (read only).")
    m.add_argument("--dest", type=Path, default=Path("pdf_validation"), help="Local copies named <article_id>.pdf.")
    m.add_argument("--report", type=Path, default=Path("validation_study/pdf_matching.csv"))
    e = sub.choices["export"]
    e.add_argument("--results", type=Path, default=Path("outputs_validation"))
    e.add_argument("--journals", type=Path, default=Path("validation_study/journal_classification.csv"))
    e.add_argument("--out", type=Path, default=Path("outputs_validation/ai_extraction.xlsx"))
    args = parser.parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8")

    sample = read_csv(args.sample)
    studies = {r["article_id"]: r for r in read_csv(args.studies)}
    if args.command == "match":
        rows = match_pdfs(sample, studies, args.pdf_dir)
        args.report.parent.mkdir(parents=True, exist_ok=True)
        with args.report.open("w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
        copied = copy_matched(rows, args.pdf_dir, args.dest)
        counts = {s: sum(r["status"] == s for r in rows) for s in ("matched", "ambiguous", "not_found")}
        print(f"{counts} -> {copied} PDFs in {args.dest}; report {args.report}")
        for row in rows:
            if row["status"] != "matched":
                print(f"- {row['article_id']} {row['status']}: {row['covidence_title'][:80]} | {row['pdf_file'][:120]}")
        return 0 if counts["matched"] == len(rows) else 1
    journals = None
    if args.journals.exists():
        journals = {r["journal"].strip().upper(): r for r in read_csv(args.journals)}
    stats = export_workbook(args.results, sample, studies, args.out, journals)
    print(f"{stats} -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
