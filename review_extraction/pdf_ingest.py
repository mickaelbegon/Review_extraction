from __future__ import annotations

import re
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


CAPTION_RE = re.compile(r"^[^\w(]*(fig\.?|figure)\s*\d+", re.IGNORECASE)
# Words that suggest a figure defines markers, landmarks or coordinate systems (methods figures).
FIGURE_METHOD_KEYWORDS = (
    "axis", "axes", "coordinate", "frame", "reference system", "landmark", "marker", "sensor", "local",
    "anatomical", "definition", "defined", "model", "placement", "set-up", "setup", "experimental", "euler",
)


@dataclass(frozen=True)
class FigurePage:
    page: int
    captions: tuple[str, ...]
    priority: str  # "high" when a caption mentions methods keywords, else "low"


def find_figure_pages(pdf_path: Path, max_pages: int = 8) -> list[FigurePage]:
    """Pages holding a figure caption; methods-like captions first, then the others, up to ``max_pages``."""
    found: list[FigurePage] = []
    with fitz.open(pdf_path) as doc:
        for page_index, page in enumerate(doc, start=1):
            captions = []
            for block in page.get_text("blocks"):
                lines = str(block[4]).splitlines()
                for i, line in enumerate(lines):  # a caption may start inside a text block
                    if CAPTION_RE.match(line):
                        captions.append(" ".join(" ".join(lines[i:]).split())[:300])
                        break
            if not captions:
                if any(_is_figure_image(page, xref[0]) for xref in page.get_images(full=True)) or len(page.get_drawings()) >= 50:
                    found.append(FigurePage(page_index, ("(figure without detected caption)",), "low"))
                continue
            joined = " ".join(captions).lower()
            priority = "high" if any(k in joined for k in FIGURE_METHOD_KEYWORDS) else "low"
            found.append(FigurePage(page_index, tuple(captions), priority))
    found.sort(key=lambda f: (f.priority != "high", f.page))
    return sorted(found[:max_pages], key=lambda f: f.page)


def _is_figure_image(page: fitz.Page, xref: int) -> bool:
    """Ignore logos and icons: keep images covering at least 10% of the page."""
    area = page.rect.width * page.rect.height
    return any(r.width * r.height >= 0.10 * area for r in page.get_image_rects(xref))


def render_pages(pdf_path: Path, pages: list[int], out_dir: Path, dpi: int = 110) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    with fitz.open(pdf_path) as doc:
        for number in pages:
            path = out_dir / f"page_{number}.png"
            doc[number - 1].get_pixmap(dpi=dpi).save(path)
            paths.append(path)
    return paths


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
