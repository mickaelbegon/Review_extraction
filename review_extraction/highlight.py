from __future__ import annotations

from pathlib import Path

import fitz

from .models import ArticleResult


HIGHLIGHT_COLORS = {
    "measurement": (1.0, 0.88, 0.25),
    "segment": (0.45, 0.75, 1.0),
    "joint": (0.55, 0.95, 0.60),
    "review": (1.0, 0.45, 0.45),
    "default": (0.85, 0.75, 1.0),
}


def write_highlighted_pdf(source_pdf: Path, result: ArticleResult, out_pdf: Path) -> int:
    highlights = 0
    with fitz.open(source_pdf) as doc:
        for answer in result.answers:
            color = _color_for_item(answer.item_id, answer.review_required)
            for evidence in answer.evidence:
                if not evidence.quote.strip() or evidence.page is None:
                    continue
                page_index = evidence.page - 1
                if page_index < 0 or page_index >= len(doc):
                    continue
                page = doc[page_index]
                matches = page.search_for(_trim_quote(evidence.quote))
                for rect in matches[:3]:
                    annot = page.add_highlight_annot(rect)
                    annot.set_colors(stroke=color)
                    annot.set_info(
                        content=f"{answer.item_id}: {answer.final_answer} (confidence {answer.final_confidence})"
                    )
                    annot.update()
                    highlights += 1
        doc.save(out_pdf, garbage=4, deflate=True)
    return highlights


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
