"""Glue between the Claude Code subagent (subscription, no API) and the existing review_extraction outputs.

The subagent is the LLM. This module only does the deterministic parts:

- ``prepare``: PDF -> targeted context + form instructions in a work folder;
- ``finalize``: the agent's ``extraction.json`` -> checked ``<article>.json`` (same ArticleResult format as the
  API pipeline) + refreshed ``summary.csv`` / ``summary.xlsx``.

Human inclusion is assumed: no screening is run, ``screening`` stays empty.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path

from pydantic import ValidationError

from .export import write_csv_summary, write_xlsx_summary
from .form_schema import EXTRACTION_ITEMS, extraction_form_prompt
from .models import ArticleResult, Evidence, ExtractedAnswer, FinalAnswer, StudyMetadataField
from .pdf_ingest import extract_pdf_text
from .reconcile import REVIEW_THRESHOLD
from .study_metadata_schema import STUDY_METADATA_ITEMS, study_metadata_prompt
from .variables import result_to_row, write_wide_csv
from .targeted_context import build_extraction_context, build_study_metadata_context

OUTPUT_FORMAT = """\
Write `extraction.json` with exactly this structure (no other text in the file):
{
  "answers": [   // exactly one entry per item_id listed in form.md
    {"item_id": "...",
     "answer": "<one allowed answer>" | ["<allowed answer>", ...],   // list only for multi-response items
     "confidence": 0.0-1.0,
     "evidence": [{"page": <int or null>, "quote": "<short EXACT quote from the paper>", "relevance": "..."}],
     "rationale_short": "...",
     "needs_human_review": false}
  ],
  "study_metadata": [   // exactly one entry per field_id listed in form.md
    {"field_id": "...", "value": "... or NR", "confidence": 0.0-1.0,
     "evidence": [{"page": <int or null>, "quote": "...", "relevance": "..."}], "rationale_short": "..."}
  ]
}
Rules: only use allowed answer identifiers; quotes must be copied verbatim from context.txt/pages.txt;
prefer 'unclear' / 'no_method_or_reference' / 'not_assessed' over guessing; set needs_human_review=true when unsure.
"""


# Negative/default codes: absence of a method or of reporting is not quotable, so no evidence is required.
DEFAULT_ANSWERS = {"no", "no_method_or_reference", "not_assessed", "not_applicable", "not_reported", "NR"}


def article_id_for(pdf: Path) -> str:
    return pdf.stem


def prepare(pdf: Path, work_dir: Path) -> Path:
    folder = work_dir / article_id_for(pdf)
    folder.mkdir(parents=True, exist_ok=True)
    pages = extract_pdf_text(pdf)
    context = build_extraction_context(pages)
    metadata_context = build_study_metadata_context(pages)
    (folder / "context.txt").write_text(context.text, encoding="utf-8")
    (folder / "metadata_context.txt").write_text(metadata_context.text, encoding="utf-8")
    (folder / "pages.txt").write_text("\n\n".join(f"[PAGE {p.page}]\n{p.text}" for p in pages), encoding="utf-8")
    form = "\n\n".join(
        [
            "# Part 1 - methodological parameters (read context.txt)",
            extraction_form_prompt(),
            "# Part 2 - study metadata (read metadata_context.txt)",
            study_metadata_prompt(),
            "# Output format",
            OUTPUT_FORMAT,
        ]
    )
    (folder / "form.md").write_text(form, encoding="utf-8")
    template = {
        "answers": [{"item_id": i.id, "answer": "", "confidence": 0, "evidence": [], "rationale_short": "", "needs_human_review": False}
                    for i in EXTRACTION_ITEMS],
        "study_metadata": [{"field_id": i.id, "value": "", "confidence": 0, "evidence": [], "rationale_short": ""}
                           for i in STUDY_METADATA_ITEMS],
    }
    (folder / "extraction.template.json").write_text(json.dumps(template, indent=1), encoding="utf-8")
    return folder


def finalize(pdf: Path, work_dir: Path, out_dir: Path) -> tuple[ArticleResult | None, list[str]]:
    folder = work_dir / article_id_for(pdf)
    raw_path = folder / "extraction.json"
    errors: list[str] = []
    if not raw_path.exists():
        return None, [f"Missing {raw_path}"]
    try:
        data = json.loads(raw_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return None, [f"extraction.json is not valid JSON: {exc}"]
    try:
        answers = [ExtractedAnswer.model_validate(a) for a in data.get("answers", [])]
        metadata = [StudyMetadataField.model_validate(m) for m in data.get("study_metadata", [])]
    except ValidationError as exc:
        return None, [str(exc)]

    allowed = {item.id: set(item.allowed_answers) for item in EXTRACTION_ITEMS}
    seen = [a.item_id for a in answers]
    errors += [f"Missing item: {i}" for i in allowed if i not in seen]
    errors += [f"Unknown item: {i}" for i in seen if i not in allowed]
    errors += [f"Duplicate item: {i}" for i in sorted({i for i in seen if seen.count(i) > 1})]
    for answer in answers:
        values = answer.answer if isinstance(answer.answer, list) else [answer.answer]
        bad = [v for v in values if answer.item_id in allowed and v not in allowed[answer.item_id]]
        if bad:
            errors.append(f"{answer.item_id}: not allowed {bad}; allowed: {sorted(allowed[answer.item_id])}")
    meta_ids = {m.field_id for m in metadata}
    errors += [f"Missing metadata field: {item.id}" for item in STUDY_METADATA_ITEMS if item.id not in meta_ids]
    if errors:
        return None, errors

    pages = {p.page: _normalize(p.text) for p in extract_pdf_text(pdf)}
    whole = " ".join(pages.values())
    final_answers = [_final_answer(a, pages, whole) for a in answers]
    result = ArticleResult(
        article_id=article_id_for(pdf),
        source_pdf=str(pdf),
        screening=None,
        study_metadata=metadata,
        answers=final_answers,
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"{result.article_id}.json").write_text(result.model_dump_json(indent=2), encoding="utf-8")
    refresh_summaries(out_dir)
    return result, []


def refresh_summaries(out_dir: Path) -> None:
    results = []
    for path in sorted(out_dir.glob("*.json")):
        if path.name == "index.json" or path.name.endswith(".screening.json"):
            continue
        try:
            results.append(ArticleResult.model_validate_json(path.read_text(encoding="utf-8")))
        except ValidationError:
            continue
    write_csv_summary(results, out_dir / "summary.csv")
    write_xlsx_summary(results, out_dir / "summary.xlsx")
    write_wide_csv([result_to_row(r) for r in results], out_dir / "binary.csv")


def _final_answer(answer: ExtractedAnswer, pages: dict[int, str], whole: str) -> FinalAnswer:
    verified: list[Evidence] = []
    unverified = 0
    for evidence in answer.evidence:
        quote = _normalize(evidence.quote)
        if not quote:
            continue
        haystack = pages.get(evidence.page, "") if evidence.page else ""
        if quote in haystack or quote in whole:
            verified.append(evidence)
        else:
            unverified += 1
    note = f" [{unverified} quote(s) not found verbatim in the PDF text]" if unverified else ""
    return FinalAnswer(
        item_id=answer.item_id,
        final_answer=answer.answer,
        extractor_answer=answer.answer,
        validator_status="none",
        validator_answer=None,
        extractor_confidence=answer.confidence,
        validator_confidence=0,
        final_confidence=answer.confidence,
        evidence=verified,
        rationale_short=answer.rationale_short + note,
        review_required=answer.needs_human_review
        or answer.confidence < REVIEW_THRESHOLD
        or (not verified and not _is_default(answer.answer)),
    )


def _is_default(value: str | list[str]) -> bool:
    values = value if isinstance(value, list) else [value]
    return all(v in DEFAULT_ANSWERS for v in values)


def _normalize(text: str) -> str:
    """Normalize PDF text and quotes before the verbatim check: ligatures (fi/fl), odd plus signs, dash variants."""
    text = unicodedata.normalize("NFKC", text)
    text = text.replace("\u00ad", "").replace("-\n", "")
    text = text.replace("\u00fe", "+")  # font-mapped plus sign extracted as "thorn"
    for dash in ("\u2010", "\u2011", "\u2012", "\u2013", "\u2014", "\u2212"):
        text = text.replace(dash, "-")
    return re.sub(r"\s+", " ", text).strip().lower()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Prepare/finalize extraction work for the Claude Code subagent.")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("prepare", "finalize"):
        p = sub.add_parser(name)
        p.add_argument("pdf", type=Path)
        p.add_argument("--work", type=Path, default=Path("agent_work"))
        if name == "finalize":
            p.add_argument("--out", type=Path, default=Path("outputs_claude_agent"))
    args = parser.parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8")
    if args.command == "prepare":
        print(prepare(args.pdf, args.work))
        return 0
    result, errors = finalize(args.pdf, args.work, args.out)
    if errors:
        print("INVALID - fix extraction.json and rerun finalize:")
        print("\n".join(f"- {e}" for e in errors))
        return 1
    flagged = sum(a.review_required for a in result.answers)
    print(f"OK {result.article_id}: {len(result.answers)} answers, {flagged} flagged review_required -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
