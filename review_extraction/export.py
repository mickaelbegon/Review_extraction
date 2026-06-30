from __future__ import annotations

import csv
from pathlib import Path

from .models import ArticleResult


def write_csv_summary(results: list[ArticleResult], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "article_id",
                "source_pdf",
                "item_id",
                "final_answer",
                "final_confidence",
                "review_required",
                "validator_status",
                "evidence_pages",
                "evidence_quotes",
            ],
        )
        writer.writeheader()
        for result in results:
            for answer in result.answers:
                writer.writerow(
                    {
                        "article_id": result.article_id,
                        "source_pdf": result.source_pdf,
                        "item_id": answer.item_id,
                        "final_answer": _stringify_answer(answer.final_answer),
                        "final_confidence": answer.final_confidence,
                        "review_required": answer.review_required,
                        "validator_status": answer.validator_status,
                        "evidence_pages": "; ".join(str(e.page) for e in answer.evidence if e.page is not None),
                        "evidence_quotes": " || ".join(e.quote for e in answer.evidence),
                    }
                )


def _stringify_answer(value: str | list[str]) -> str:
    if isinstance(value, list):
        return "; ".join(value)
    return value
