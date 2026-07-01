from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .pdf_ingest import PageText


@dataclass(frozen=True)
class ContextBuild:
    text: str
    selected_chars: int
    full_chars: int
    selected_pages: list[int]


SCREENING_KEYWORDS = [
    "abstract",
    "participant",
    "patient",
    "subject",
    "healthy",
    "human",
    "animal",
    "shoulder",
    "scapula",
    "humerus",
    "clavicle",
    "thorax",
    "kinematic",
    "posture",
    "prospective",
    "retrospective",
    "review",
    "secondary analysis",
    "conference",
    "proceeding",
    "methods",
]

EXTRACTION_KEYWORDS = [
    "acromion",
    "anatomical coordinate",
    "axis",
    "axes",
    "bone pin",
    "camera",
    "center of rotation",
    "centre of rotation",
    "clavicle",
    "coordinate system",
    "euler",
    "glenohumeral",
    "humeral head",
    "humerus",
    "inertial",
    "international society of biomechanics",
    "isb",
    "kinematic",
    "landmark",
    "marker",
    "motion capture",
    "optical",
    "origin",
    "rotation sequence",
    "scapula",
    "segment",
    "sensor",
    "shoulder",
    "thorax",
    "translation",
    "y-x-y",
    "y-x-z",
    "z-x-y",
]

STUDY_METADATA_KEYWORDS = [
    "abstract",
    "author",
    "doi",
    "journal",
    "participant",
    "patient",
    "subject",
    "healthy",
    "cadaver",
    "model",
    "country",
    "institution",
    "university",
    "hospital",
    "age",
    "sex",
    "female",
    "male",
    "shoulder",
    "side",
    "dominant",
    "movement",
    "task",
    "elevation",
    "abduction",
    "flexion",
    "plane",
    "active",
    "passive",
    "data availability",
    "supplementary",
    "repository",
    "isb",
    "international society of biomechanics",
    "methods",
]

METHOD_HEADINGS = [
    "method",
    "methods",
    "materials and methods",
    "participants",
    "subjects",
    "experimental protocol",
    "protocol",
    "instrumentation",
    "data analysis",
    "kinematic analysis",
]


def build_screening_context(
    pages: list[PageText],
    max_chars: int = 40_000,
    target_fraction: float = 0.65,
) -> ContextBuild:
    return _build_targeted_context(
        pages=pages,
        keywords=SCREENING_KEYWORDS,
        max_chars=max_chars,
        target_fraction=target_fraction,
        title="TARGETED FULL-PAPER SCREENING CONTEXT",
        always_include_pages=2,
        window_chars=1_500,
    )


def build_extraction_context(
    pages: list[PageText],
    max_chars: int = 55_000,
    target_fraction: float = 0.75,
) -> ContextBuild:
    return _build_targeted_context(
        pages=pages,
        keywords=EXTRACTION_KEYWORDS,
        max_chars=max_chars,
        target_fraction=target_fraction,
        title="TARGETED METHODOLOGY EXTRACTION CONTEXT",
        always_include_pages=1,
        window_chars=1_700,
    )


def build_study_metadata_context(
    pages: list[PageText],
    max_chars: int = 45_000,
    target_fraction: float = 0.70,
) -> ContextBuild:
    return _build_targeted_context(
        pages=pages,
        keywords=STUDY_METADATA_KEYWORDS,
        max_chars=max_chars,
        target_fraction=target_fraction,
        title="TARGETED STUDY METADATA CONTEXT",
        always_include_pages=2,
        window_chars=1_600,
    )


def build_full_context(pages: list[PageText], max_chars: int = 120_000) -> ContextBuild:
    text = _pages_to_prompt_context(pages, max_chars=max_chars)
    return ContextBuild(
        text=text,
        selected_chars=len(text),
        full_chars=_full_chars(pages),
        selected_pages=sorted({page.page for page in pages if page.text.strip()}),
    )


def _build_targeted_context(
    *,
    pages: list[PageText],
    keywords: list[str],
    max_chars: int,
    target_fraction: float,
    title: str,
    always_include_pages: int,
    window_chars: int,
) -> ContextBuild:
    full_chars = _full_chars(pages)
    effective_max_chars = min(max_chars, max(12_000, int(full_chars * target_fraction)))
    candidates = _candidate_windows(pages, window_chars=window_chars)
    scored = [
        (score, index, page, text)
        for index, (page, text) in enumerate(candidates)
        if (score := _score_window(page=page, text=text, keywords=keywords, always_include_pages=always_include_pages)) > 0
    ]
    scored.sort(key=lambda item: (-item[0], item[2], item[1]))

    selected: list[tuple[int, int, str]] = []
    used_signatures: set[tuple[int, str]] = set()
    used_chars = len(title) + 200
    for _, index, page, text in scored:
        normalized = _compact(text)
        signature = (page, normalized[:160])
        if signature in used_signatures:
            continue
        block_len = len(normalized) + 40
        if used_chars + block_len > effective_max_chars:
            continue
        selected.append((page, index, normalized))
        used_signatures.add(signature)
        used_chars += block_len

    selected.sort(key=lambda item: (item[0], item[1]))
    selected_pages = sorted({page for page, _, _ in selected})
    body = "\n\n".join(f"[PAGE {page}]\n{text}" for page, _, text in selected)
    header = (
        f"{title}\n"
        "The context below was selected locally from the PDF to reduce token use. "
        "Page markers are authoritative. If the evidence is insufficient, say so rather than guessing.\n"
        f"Selected pages: {', '.join(str(page) for page in selected_pages) or 'none'}.\n"
    )
    return ContextBuild(
        text=f"{header}\n{body}".strip(),
        selected_chars=len(body),
        full_chars=full_chars,
        selected_pages=selected_pages,
    )


def _candidate_windows(pages: list[PageText], window_chars: int) -> list[tuple[int, str]]:
    windows: list[tuple[int, str]] = []
    references_started = False
    for page in pages:
        text = _trim_references(page.text, references_started=references_started)
        if _starts_references(page.text):
            references_started = True
        if not text.strip() or references_started and not text.strip():
            continue
        cleaned = _compact(text)
        if len(cleaned) <= window_chars:
            windows.append((page.page, cleaned))
            continue
        step = max(600, window_chars - 200)
        for start in range(0, len(cleaned), step):
            chunk = cleaned[start : start + window_chars].strip()
            if len(chunk) >= 250:
                windows.append((page.page, chunk))
            if start + window_chars >= len(cleaned):
                break
    return windows


def _score_window(*, page: int, text: str, keywords: list[str], always_include_pages: int) -> int:
    lowered = text.lower()
    score = 0
    if page <= always_include_pages:
        score += 5
    if any(heading in lowered[:240] for heading in METHOD_HEADINGS):
        score += 6
    for keyword in keywords:
        if keyword in lowered:
            score += 3 if " " in keyword else 1
    if "reference" in lowered[:120] or "bibliography" in lowered[:120]:
        score -= 20
    return score


def _trim_references(text: str, *, references_started: bool) -> str:
    if references_started:
        return ""
    lowered = text.lower()
    for marker in ("\nreferences\n", "\nreference list\n", "\nbibliography\n"):
        index = lowered.find(marker)
        if index >= 0:
            return text[:index]
    return text


def _starts_references(text: str) -> bool:
    lowered = text.lower()
    return any(marker in lowered for marker in ("\nreferences\n", "\nreference list\n", "\nbibliography\n"))


def _compact(text: str) -> str:
    return " ".join(text.split())


def _full_chars(pages: list[PageText]) -> int:
    return sum(len(page.text) for page in pages)


def _pages_to_prompt_context(pages: list[PageText], max_chars: int) -> str:
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
