from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from time import perf_counter
from typing import Callable

from .adaptive_extraction import automatic_absent_answers, item_ids_for_plan, merge_adaptive_answers
from .export import write_csv_summary, write_xlsx_summary
from .models import ArticleResult, FinalScreeningResult, TokenUsage
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
    article_usage: list[TokenUsage] = []
    article_started = perf_counter()

    if reuse_existing and json_path.exists():
        _emit(progress, f"{prefix}reuse existing JSON: {json_path.name}")
        result = ArticleResult.model_validate_json(json_path.read_text(encoding="utf-8"))
        if write_highlights:
            _emit(progress, f"{prefix}regenerate highlighted PDF from JSON")
            _write_highlights_if_possible(pdf_path, result, out_dir)
        _emit(progress, f"{prefix}done")
        return result

    _emit(progress, f"{prefix}extract PDF text")
    from .pdf_ingest import extract_pdf_text
    from .targeted_context import build_extraction_context, build_full_context, build_screening_context, build_study_metadata_context

    pages = extract_pdf_text(pdf_path)
    full_context = build_full_context(pages)
    screening_context = build_screening_context(pages)
    screening_validation_context = build_screening_context(pages, max_chars=50_000, target_fraction=0.80)
    _emit(progress, f"{prefix}target screening context: {_context_report(screening_context)}")

    if reuse_existing and screening_path.exists():
        _emit(progress, f"{prefix}reuse existing screening JSON: {screening_path.name}")
        final_screening = FinalScreeningResult.model_validate_json(screening_path.read_text(encoding="utf-8"))
    else:
        _emit(progress, f"{prefix}screen targeted full paper")
        usage_start = _usage_marker(agents)
        step_started = perf_counter()
        screening = agents.screen(article_id=article_id, paper_context=screening_context.text)
        _collect_usage(agents, usage_start, article_usage, progress, prefix, elapsed_seconds=_elapsed(step_started))
        _emit(progress, f"{prefix}validate screening with broader targeted context")
        usage_start = _usage_marker(agents)
        step_started = perf_counter()
        screening_validation = agents.validate_screening(
            article_id=article_id,
            paper_context=screening_validation_context.text,
            screening=screening,
        )
        _collect_usage(agents, usage_start, article_usage, progress, prefix, elapsed_seconds=_elapsed(step_started))
        _emit(progress, f"{prefix}reconcile screening")
        final_screening = reconcile_screening(screening=screening, validation=screening_validation)
        if _screening_needs_full_context_fallback(final_screening, screening_context, full_context):
            _emit(
                progress,
                f"{prefix}screening uncertain/complex: escalate to {agents.config.fallback_model} with full PDF context",
            )
            usage_start = _usage_marker(agents)
            step_started = perf_counter()
            screening = agents.screen(
                article_id=article_id,
                paper_context=full_context.text,
                model=agents.config.fallback_model,
            )
            _collect_usage(agents, usage_start, article_usage, progress, prefix, elapsed_seconds=_elapsed(step_started))
            _emit(progress, f"{prefix}validate screening with {agents.config.fallback_validator_model} full PDF context")
            usage_start = _usage_marker(agents)
            step_started = perf_counter()
            screening_validation = agents.validate_screening(
                article_id=article_id,
                paper_context=full_context.text,
                screening=screening,
                model=agents.config.fallback_validator_model,
            )
            _collect_usage(agents, usage_start, article_usage, progress, prefix, elapsed_seconds=_elapsed(step_started))
            _emit(progress, f"{prefix}reconcile full-context screening")
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
            usage=article_usage,
            processing_seconds=_elapsed(article_started),
        )
        json_path.write_text(result.model_dump_json(indent=2), encoding="utf-8")
        _emit(progress, f"{prefix}article usage: {_usage_summary(article_usage)}, processing={result.processing_seconds:.2f}s")
        if write_highlights:
            _emit(progress, f"{prefix}write highlighted PDF")
            _write_highlights_if_possible(pdf_path, result, out_dir)
        _emit(progress, f"{prefix}done")
        return result

    study_metadata_context = build_study_metadata_context(pages)
    _emit(progress, f"{prefix}target study metadata context: {_context_report(study_metadata_context)}")
    _emit(progress, f"{prefix}extract study metadata")
    usage_start = _usage_marker(agents)
    step_started = perf_counter()
    study_metadata = agents.extract_study_metadata(article_id=article_id, paper_context=study_metadata_context.text)
    _collect_usage(agents, usage_start, article_usage, progress, prefix, elapsed_seconds=_elapsed(step_started))

    extraction_context = build_extraction_context(pages)
    extraction_validation_context = build_extraction_context(pages, max_chars=70_000, target_fraction=0.90)
    _emit(progress, f"{prefix}target extraction context: {_context_report(extraction_context)}")
    _emit(progress, f"{prefix}plan adaptive extraction blocks")
    usage_start = _usage_marker(agents)
    step_started = perf_counter()
    extraction_plan = agents.plan_extraction(article_id=article_id, paper_context=extraction_context.text)
    _collect_usage(agents, usage_start, article_usage, progress, prefix, elapsed_seconds=_elapsed(step_started))
    selected_item_ids = item_ids_for_plan(extraction_plan)
    automatic_answers = automatic_absent_answers(extraction_plan)
    _emit(
        progress,
        f"{prefix}adaptive extraction: {len(selected_item_ids)} item(s) sent to AI, "
        f"{len(automatic_answers)} item(s) filled automatically",
    )
    _emit(progress, f"{prefix}extract methodological parameters from targeted context")
    usage_start = _usage_marker(agents)
    step_started = perf_counter()
    extraction = agents.extract(
        article_id=article_id,
        paper_context=extraction_context.text,
        item_ids=selected_item_ids,
    )
    _collect_usage(agents, usage_start, article_usage, progress, prefix, elapsed_seconds=_elapsed(step_started))
    _emit(progress, f"{prefix}validate methodological parameters with broader targeted context")
    usage_start = _usage_marker(agents)
    step_started = perf_counter()
    validation = agents.validate(
        article_id=article_id,
        paper_context=extraction_validation_context.text,
        extraction=extraction,
        item_ids=selected_item_ids,
    )
    _collect_usage(agents, usage_start, article_usage, progress, prefix, elapsed_seconds=_elapsed(step_started))
    _emit(progress, f"{prefix}reconcile methodological parameters")
    result = reconcile(source_pdf=str(pdf_path), extraction=extraction, validation=validation)
    if _extraction_needs_fallback(result):
        _emit(
            progress,
            f"{prefix}extraction complex/divergent: escalate to {agents.config.fallback_model}",
        )
        usage_start = _usage_marker(agents)
        step_started = perf_counter()
        extraction = agents.extract(
            article_id=article_id,
            paper_context=extraction_context.text,
            model=agents.config.fallback_model,
            item_ids=selected_item_ids,
        )
        _collect_usage(agents, usage_start, article_usage, progress, prefix, elapsed_seconds=_elapsed(step_started))
        _emit(progress, f"{prefix}validate escalated extraction with {agents.config.fallback_validator_model}")
        usage_start = _usage_marker(agents)
        step_started = perf_counter()
        validation = agents.validate(
            article_id=article_id,
            paper_context=extraction_validation_context.text,
            extraction=extraction,
            model=agents.config.fallback_validator_model,
            item_ids=selected_item_ids,
        )
        _collect_usage(agents, usage_start, article_usage, progress, prefix, elapsed_seconds=_elapsed(step_started))
        _emit(progress, f"{prefix}reconcile escalated methodological parameters")
        result = reconcile(source_pdf=str(pdf_path), extraction=extraction, validation=validation)
    result.answers = merge_adaptive_answers(result.answers, automatic_answers)
    result.screening = final_screening
    result.study_metadata = study_metadata.fields
    result.usage = article_usage
    result.processing_seconds = _elapsed(article_started)

    json_path.write_text(result.model_dump_json(indent=2), encoding="utf-8")
    _emit(progress, f"{prefix}article usage: {_usage_summary(article_usage)}, processing={result.processing_seconds:.2f}s")

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
    limit: int | None = None,
    workers: int = 1,
    agent_factory: Callable[[], DualAgentExtractor] | None = None,
    progress: Callable[[str], None] | None = None,
) -> list[ArticleResult]:
    out_dir.mkdir(parents=True, exist_ok=True)
    if workers < 1:
        raise ValueError("workers must be greater than or equal to 1.")
    pdfs = [pdf for pdf in (sorted(input_path.glob("*.pdf")) if input_path.is_dir() else [input_path]) if pdf.suffix.lower() == ".pdf"]
    if limit is not None:
        if limit < 0:
            raise ValueError("limit must be greater than or equal to 0.")
        pdfs = pdfs[:limit]
    total = len(pdfs)
    limit_message = f" (limit={limit})" if limit is not None else ""
    worker_message = f", workers={workers}" if workers > 1 else ""
    _emit(progress, f"Found {total} PDF(s) to process{limit_message}{worker_message}.")
    if workers == 1:
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
    else:
        if agent_factory is None:
            if isinstance(agents, DualAgentExtractor):
                agent_factory = lambda: DualAgentExtractor(config=agents.config)
            else:
                raise ValueError("agent_factory is required when workers > 1 with custom agents.")
        results_by_index: list[ArticleResult | None] = [None] * total
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {
                executor.submit(
                    process_pdf,
                    pdf,
                    out_dir,
                    agent_factory(),
                    write_highlights=write_highlights,
                    reuse_existing=reuse_existing,
                    progress=progress,
                    current=current,
                    total=total,
                ): current - 1
                for current, pdf in enumerate(pdfs, start=1)
            }
            for future in as_completed(futures):
                results_by_index[futures[future]] = future.result()
        results = [result for result in results_by_index if result is not None]
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


def _context_report(context: object) -> str:
    selected_chars = getattr(context, "selected_chars", 0)
    full_chars = getattr(context, "full_chars", 0)
    selected_pages = getattr(context, "selected_pages", [])
    percent = (selected_chars / full_chars * 100) if full_chars else 0
    pages = ", ".join(str(page) for page in selected_pages[:12])
    if len(selected_pages) > 12:
        pages += ", ..."
    return f"{selected_chars}/{full_chars} chars ({percent:.0f}%), pages {pages or 'none'}"


def _screening_needs_full_context_fallback(
    final_screening: FinalScreeningResult,
    targeted_context: object,
    full_context: object,
) -> bool:
    targeted_chars = getattr(targeted_context, "selected_chars", 0)
    full_chars = getattr(full_context, "selected_chars", 0)
    if full_chars <= targeted_chars:
        return False
    return final_screening.overall_decision == "uncertain" or final_screening.review_required


def _extraction_needs_fallback(result: ArticleResult) -> bool:
    return any(answer.review_required or answer.validator_status != "agree" for answer in result.answers)


def _usage_marker(agents: object) -> int:
    usage_events = getattr(agents, "usage_events", [])
    return len(usage_events)


def _collect_usage(
    agents: object,
    start: int,
    article_usage: list[TokenUsage],
    progress: Callable[[str], None] | None,
    prefix: str,
    elapsed_seconds: float | None = None,
) -> None:
    usage_events = getattr(agents, "usage_events", [])
    new_events = list(usage_events[start:])
    if elapsed_seconds is not None and new_events:
        per_event_seconds = round(elapsed_seconds / len(new_events), 3)
        for usage in new_events:
            usage.elapsed_seconds = per_event_seconds
    article_usage.extend(new_events)
    for usage in new_events:
        _emit(progress, f"{prefix}{_format_usage(usage)}")


def _format_usage(usage: TokenUsage) -> str:
    cost = f", cost=${usage.estimated_cost_usd:.6f}" if usage.estimated_cost_usd is not None else ""
    elapsed = f", elapsed={usage.elapsed_seconds:.2f}s" if usage.elapsed_seconds is not None else ""
    return (
        f"usage {usage.step}: model={usage.model}, "
        f"input={usage.input_tokens}, cached_input={usage.cached_input_tokens}, "
        f"output={usage.output_tokens}, total={usage.total_tokens}{cost}{elapsed}"
    )


def _usage_summary(usages: list[TokenUsage]) -> str:
    input_tokens = sum(usage.input_tokens for usage in usages)
    cached_input_tokens = sum(usage.cached_input_tokens for usage in usages)
    output_tokens = sum(usage.output_tokens for usage in usages)
    total_tokens = sum(usage.total_tokens for usage in usages)
    costs = [usage.estimated_cost_usd for usage in usages if usage.estimated_cost_usd is not None]
    elapsed_values = [usage.elapsed_seconds for usage in usages if usage.elapsed_seconds is not None]
    cost = f", cost=${sum(costs):.6f}" if costs else ""
    elapsed = f", ai_elapsed={sum(elapsed_values):.2f}s" if elapsed_values else ""
    return f"input={input_tokens}, cached_input={cached_input_tokens}, output={output_tokens}, total={total_tokens}{cost}{elapsed}"


def _elapsed(started: float) -> float:
    return round(perf_counter() - started, 3)
