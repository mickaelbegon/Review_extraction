from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

from .export import write_csv_summary, write_xlsx_summary
from .models import ArticleResult, FinalScreeningResult
from .openai_agents import DualAgentExtractor
from .reconcile import reconcile
from .screening_reconcile import reconcile_screening


def process_pdf(
    pdf_path: Path,
    out_dir: Path,
    agents: DualAgentExtractor,
    *,
    write_highlights: bool = True,
    reuse_existing: bool = True,
    progress: Callable[[str], None] | None = None,
    current: int | None = None,
    total: int | None = None,
) -> ArticleResult:
    out_dir.mkdir(parents=True, exist_ok=True)
    article_id = pdf_path.stem
    json_path = out_dir / f"{article_id}.json"
    screening_path = out_dir / f"{article_id}.screening.json"
    prefix = _progress_prefix(current, total, pdf_path)

    if reuse_existing and json_path.exists():
        _emit(progress, f"{prefix}reuse existing JSON: {json_path.name}")
        result = ArticleResult.model_validate_json(json_path.read_text(encoding="utf-8"))
        if write_highlights:
            _emit(progress, f"{prefix}regenerate highlighted PDF from JSON")
            _write_highlights_if_possible(pdf_path, result, out_dir)
        _emit(progress, f"{prefix}done")
        return result

    _emit(progress, f"{prefix}extract PDF text")
    from .pdf_ingest import extract_pdf_text, pages_to_prompt_context

    pages = extract_pdf_text(pdf_path)
    context = pages_to_prompt_context(pages)

    if reuse_existing and screening_path.exists():
        _emit(progress, f"{prefix}reuse existing screening JSON: {screening_path.name}")
        final_screening = FinalScreeningResult.model_validate_json(screening_path.read_text(encoding="utf-8"))
    else:
        _emit(progress, f"{prefix}screen full paper")
        screening = agents.screen(article_id=article_id, paper_context=context)
        _emit(progress, f"{prefix}validate screening")
        screening_validation = agents.validate_screening(
            article_id=article_id,
            paper_context=context,
            screening=screening,
        )
        _emit(progress, f"{prefix}reconcile screening")
        final_screening = reconcile_screening(screening=screening, validation=screening_validation)
        screening_path.write_text(final_screening.model_dump_json(indent=2), encoding="utf-8")

    if not final_screening.extraction_allowed:
        _emit(
            progress,
            f"{prefix}skip detailed extraction: screening={final_screening.overall_decision}, "
            f"review_required={final_screening.review_required}",
        )
        result = ArticleResult(
            article_id=article_id,
            source_pdf=str(pdf_path),
            screening=final_screening,
            answers=[],
        )
        json_path.write_text(result.model_dump_json(indent=2), encoding="utf-8")
        if write_highlights:
            _emit(progress, f"{prefix}write highlighted PDF")
            _write_highlights_if_possible(pdf_path, result, out_dir)
        _emit(progress, f"{prefix}done")
        return result

    _emit(progress, f"{prefix}extract methodological parameters")
    extraction = agents.extract(article_id=article_id, paper_context=context)
    _emit(progress, f"{prefix}validate methodological parameters")
    validation = agents.validate(article_id=article_id, paper_context=context, extraction=extraction)
    _emit(progress, f"{prefix}reconcile methodological parameters")
    result = reconcile(source_pdf=str(pdf_path), extraction=extraction, validation=validation)
    result.screening = final_screening

    json_path.write_text(result.model_dump_json(indent=2), encoding="utf-8")

    if write_highlights:
        _emit(progress, f"{prefix}write highlighted PDF")
        _write_highlights_if_possible(pdf_path, result, out_dir)

    _emit(progress, f"{prefix}done")
    return result


def process_many(
    input_path: Path,
    out_dir: Path,
    agents: DualAgentExtractor,
    *,
    write_highlights: bool = True,
    reuse_existing: bool = True,
    progress: Callable[[str], None] | None = None,
) -> list[ArticleResult]:
    out_dir.mkdir(parents=True, exist_ok=True)
    pdfs = [pdf for pdf in (sorted(input_path.glob("*.pdf")) if input_path.is_dir() else [input_path]) if pdf.suffix.lower() == ".pdf"]
    total = len(pdfs)
    _emit(progress, f"Found {total} PDF(s) to process.")
    results = []
    for current, pdf in enumerate(pdfs, start=1):
        results.append(
            process_pdf(
                pdf,
                out_dir,
                agents,
                write_highlights=write_highlights,
                reuse_existing=reuse_existing,
                progress=progress,
                current=current,
                total=total,
            )
        )
    _emit(progress, "write index.json")
    index_path = out_dir / "index.json"
    index_path.write_text(json.dumps([result.model_dump() for result in results], indent=2), encoding="utf-8")
    _emit(progress, "write summary.csv")
    write_csv_summary(results, out_dir / "summary.csv")
    _emit(progress, "write summary.xlsx")
    write_xlsx_summary(results, out_dir / "summary.xlsx")
    return results


def _write_highlights_if_possible(pdf_path: Path, result: ArticleResult, out_dir: Path) -> None:
    if not pdf_path.exists():
        return
    from .highlight import write_highlighted_pdf

    highlighted_path = out_dir / f"{pdf_path.stem}.highlighted.pdf"
    write_highlighted_pdf(pdf_path, result, highlighted_path)


def _progress_prefix(current: int | None, total: int | None, pdf_path: Path) -> str:
    if current is None or total is None:
        return f"{pdf_path.name}: "
    return f"[{current}/{total}] {pdf_path.name}: "


def _emit(progress: Callable[[str], None] | None, message: str) -> None:
    if progress is not None:
        progress(message)
