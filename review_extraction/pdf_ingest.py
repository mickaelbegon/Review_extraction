from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import fitz


@dataclass(frozen=True)
class PageText:
    page: int
    text: str


def extract_pdf_text(pdf_path: Path) -> list[PageText]:
    pages: list[PageText] = []
    with fitz.open(pdf_path) as doc:
        for page_index, page in enumerate(doc, start=1):
            text = page.get_text("text").strip()
            pages.append(PageText(page=page_index, text=text))
    return pages


def pages_to_prompt_context(pages: list[PageText], max_chars: int = 120_000) -> str:
    chunks: list[str] = []
    used = 0
    for page in pages:
        block = f"\n\n[PAGE {page.page}]\n{page.text}"
        if used + len(block) > max_chars:
            remaining = max_chars - used
            if remaining > 500:
                chunks.append(block[:remaining])
            break
        chunks.append(block)
        used += len(block)
    return "".join(chunks).strip()
