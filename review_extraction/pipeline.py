from __future__ import annotations

import json
from pathlib import Path

from .export import write_csv_summary
from .highlight import write_highlighted_pdf
from .models import ArticleResult
from .openai_agents import DualAgentExtractor
from .pdf_ingest import extract_pdf_text, pages_to_prompt_context
from .reconcile import reconcile
from .screening_reconcile import reconcile_screening


def process_pdf(
    pdf_path: Path,
    out_dir: Path,
    agents: DualAgentExtractor,
    *,
    write_highlights: bool = True,
) -> ArticleResult:
    out_dir.mkdir(parents=True, exist_ok=True)
    article_id = pdf_path.stem
    pages = extract_pdf_text(pdf_path)
    context = pages_to_prompt_context(pages)

    screening = agents.screen(article_id=article_id, paper_context=context)
    screening_validation = agents.validate_screening(
        article_id=article_id,
        paper_context=context,
        screening=screening,
    )
    final_screening = reconcile_screening(screening=screening, validation=screening_validation)
    screening_path = out_dir / f"{article_id}.screening.json"
    screening_path.write_text(final_screening.model_dump_json(indent=2), encoding="utf-8")

    if not final_screening.extraction_allowed:
        result = ArticleResult(
            article_id=article_id,
            source_pdf=str(pdf_path),
            screening=final_screening,
            answers=[],
        )
        json_path = out_dir / f"{article_id}.json"
        json_path.write_text(result.model_dump_json(indent=2), encoding="utf-8")
        if write_highlights:
            highlighted_path = out_dir / f"{article_id}.highlighted.pdf"
            write_highlighted_pdf(pdf_path, result, highlighted_path)
        return result

    extraction = agents.extract(article_id=article_id, paper_context=context)
    validation = agents.validate(article_id=article_id, paper_context=context, extraction=extraction)
    result = reconcile(source_pdf=str(pdf_path), extraction=extraction, validation=validation)
    result.screening = final_screening

    json_path = out_dir / f"{article_id}.json"
    json_path.write_text(result.model_dump_json(indent=2), encoding="utf-8")

    if write_highlights:
        highlighted_path = out_dir / f"{article_id}.highlighted.pdf"
        write_highlighted_pdf(pdf_path, result, highlighted_path)

    return result


def process_many(
    input_path: Path,
    out_dir: Path,
    agents: DualAgentExtractor,
    *,
    write_highlights: bool = True,
) -> list[ArticleResult]:
    pdfs = sorted(input_path.glob("*.pdf")) if input_path.is_dir() else [input_path]
    results = [
        process_pdf(pdf, out_dir, agents, write_highlights=write_highlights)
        for pdf in pdfs
        if pdf.suffix.lower() == ".pdf"
    ]
    index_path = out_dir / "index.json"
    index_path.write_text(json.dumps([result.model_dump() for result in results], indent=2), encoding="utf-8")
    write_csv_summary(results, out_dir / "summary.csv")
    return results
