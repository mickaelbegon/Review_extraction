from __future__ import annotations

from pathlib import Path

import fitz

from .models import ArticleResult


HIGHLIGHT_COLORS = {
    "measurement": (1.0, 0.93, 0.55),
    "segment": (0.62, 0.84, 1.0),
    "joint": (0.68, 0.96, 0.72),
    "review": (1.0, 0.64, 0.64),
    "default": (0.90, 0.82, 1.0),
}

HIGHLIGHT_OPACITY = 0.35


def write_highlighted_pdf(source_pdf: Path, result: ArticleResult, out_pdf: Path) -> int:
    highlights = 0
    seen_rects: set[tuple[int, float, float, float, float]] = set()
    with fitz.open(source_pdf) as doc:
        if result.screening is not None:
            for criterion in result.screening.criteria:
                color = HIGHLIGHT_COLORS["review"] if criterion.review_required else HIGHLIGHT_COLORS["default"]
                for evidence in criterion.evidence:
                    highlights += _highlight_evidence(
                        doc=doc,
                        page_number=evidence.page,
                        quote=evidence.quote,
                        color=color,
                        content=f"screening.{criterion.criterion_id}: {criterion.final_decision} "
                        f"(confidence {criterion.final_confidence})",
                        seen_rects=seen_rects,
                    )
        for answer in result.answers:
            color = _color_for_item(answer.item_id, answer.review_required)
            for evidence in answer.evidence:
                highlights += _highlight_evidence(
                    doc=doc,
                    page_number=evidence.page,
                    quote=evidence.quote,
                    color=color,
                    content=f"{answer.item_id}: {answer.final_answer} (confidence {answer.final_confidence})",
                    seen_rects=seen_rects,
                )
        doc.save(out_pdf, garbage=4, deflate=True)
    return highlights


def _highlight_evidence(
    doc: fitz.Document,
    page_number: int | None,
    quote: str,
    color: tuple[float, float, float],
    content: str,
    seen_rects: set[tuple[int, float, float, float, float]],
) -> int:
    if not quote.strip() or page_number is None:
        return 0
    page_index = page_number - 1
    if page_index < 0 or page_index >= len(doc):
        return 0
    page = doc[page_index]
    matches = page.search_for(_trim_quote(quote))
    highlights = 0
    for rect in matches[:3]:
        key = _rect_key(page_number, rect)
        if key in seen_rects:
            continue
        seen_rects.add(key)
        annot = page.add_highlight_annot(rect)
        annot.set_colors(stroke=color)
        annot.set_opacity(HIGHLIGHT_OPACITY)
        annot.set_info(content=content)
        annot.update()
        highlights += 1
    return highlights


def _rect_key(page_number: int, rect: fitz.Rect) -> tuple[int, float, float, float, float]:
    return (
        page_number,
        round(rect.x0, 1),
        round(rect.y0, 1),
        round(rect.x1, 1),
        round(rect.y1, 1),
    )


def _trim_quote(quote: str) -> str:
    quote = " ".join(quote.split())
    if len(quote) <= 220:
        return quote
    return quote[:220]


def _color_for_item(item_id: str, review_required: bool) -> tuple[float, float, float]:
    if review_required:
        return HIGHLIGHT_COLORS["review"]
    if item_id == "measurement_methods":
        return HIGHLIGHT_COLORS["measurement"]
    if any(segment in item_id for segment in ["thorax", "clavicle", "scapula", "humerus"]) and "reported" not in item_id:
        return HIGHLIGHT_COLORS["segment"]
    if "reported" in item_id or "rotations" in item_id or "translations" in item_id:
        return HIGHLIGHT_COLORS["joint"]
    return HIGHLIGHT_COLORS["default"]
