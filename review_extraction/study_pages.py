from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path
from typing import Any

from .form_schema import EXTRACTION_ITEMS
from .models import ArticleResult, FinalAnswer
from .study_metadata_schema import STUDY_METADATA_ITEMS, metadata_labels


def load_article_results(results_dir: Path) -> list[ArticleResult]:
    results: list[ArticleResult] = []
    for json_path in sorted(results_dir.glob("*.json")):
        if json_path.name == "index.json" or json_path.name.endswith(".screening.json"):
            continue
        results.append(ArticleResult.model_validate_json(json_path.read_text(encoding="utf-8")))
    return results


def write_study_page_workbooks(
    results: list[ArticleResult],
    out_dir: Path,
    *,
    split_by_letter: bool = False,
) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    if split_by_letter:
        groups: dict[str, list[ArticleResult]] = defaultdict(list)
        for result in results:
            groups[_study_letter(result)].append(result)
        return [
            _write_workbook(group_results, out_dir / f"study_pages_{letter}.xlsx")
            for letter, group_results in sorted(groups.items())
        ]
    return [_write_workbook(results, out_dir / "study_pages.xlsx")]


def _write_workbook(results: list[ArticleResult], out_path: Path) -> Path:
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
        from openpyxl.utils import get_column_letter
    except ImportError as exc:
        raise RuntimeError("openpyxl is required to write study page workbooks. Recreate the conda environment.") from exc

    workbook = Workbook()
    workbook.remove(workbook.active)
    if not results:
        sheet = workbook.create_sheet("No studies")
        sheet["A1"] = "No article JSON files found."
    for result in results:
        sheet = workbook.create_sheet(_sheet_title(result, workbook.sheetnames))
        _write_study_sheet(sheet, result, get_column_letter, Font, PatternFill, Alignment, Border, Side)
    workbook.save(out_path)
    return out_path


def _write_study_sheet(sheet: Any, result: ArticleResult, get_column_letter: Any, Font: Any, PatternFill: Any, Alignment: Any, Border: Any, Side: Any) -> None:
    labels = metadata_labels()
    metadata = {field.field_id: field for field in result.study_metadata}
    answers = {answer.item_id: answer for answer in result.answers}
    thin = Side(style="thin", color="D9E2F3")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    title_fill = PatternFill("solid", fgColor="1F4E78")
    section_fill = PatternFill("solid", fgColor="D9EAF7")
    value_fill = PatternFill("solid", fgColor="F7FBFF")
    review_fill = PatternFill("solid", fgColor="FCE4D6")
    auto_fill = PatternFill("solid", fgColor="E2F0D9")

    sheet.page_setup.orientation = "landscape"
    sheet.page_setup.fitToWidth = 1
    sheet.page_setup.fitToHeight = 1
    sheet.sheet_properties.pageSetUpPr.fitToPage = True
    sheet.page_margins.left = 0.25
    sheet.page_margins.right = 0.25
    sheet.page_margins.top = 0.35
    sheet.page_margins.bottom = 0.35

    for col, width in enumerate([24, 30, 16, 34, 18, 18, 30, 18], start=1):
        sheet.column_dimensions[get_column_letter(col)].width = width

    sheet.merge_cells("A1:H1")
    title = _metadata_value(metadata, "study_id") or result.article_id
    sheet["A1"] = f"{title} - study review page"
    sheet["A1"].font = Font(color="FFFFFF", bold=True, size=16)
    sheet["A1"].fill = title_fill
    sheet["A1"].alignment = Alignment(horizontal="center")

    row = 3
    row = _write_section_title(sheet, row, "Study identification and population", section_fill, Font, Alignment)
    for item in STUDY_METADATA_ITEMS:
        row = _write_key_value(
            sheet,
            row,
            item.label,
            _metadata_value(metadata, item.id),
            _metadata_confidence(metadata, item.id),
            _metadata_evidence(metadata, item.id),
            value_fill,
            border,
            Alignment,
        )

    row += 1
    row = _write_section_title(sheet, row, "Screening decision", section_fill, Font, Alignment)
    screening = result.screening
    screening_values = [
        ("Overall decision", screening.overall_decision if screening else ""),
        ("Confidence", screening.final_confidence if screening else ""),
        ("Review required", screening.review_required if screening else ""),
    ]
    for label, value in screening_values:
        row = _write_key_value(sheet, row, label, value, "", "", value_fill, border, Alignment)
    if screening:
        for criterion in screening.criteria:
            row = _write_key_value(
                sheet,
                row,
                f"Criterion: {criterion.criterion_id}",
                criterion.final_decision,
                criterion.final_confidence,
                _evidence_text(criterion.evidence),
                review_fill if criterion.review_required else value_fill,
                border,
                Alignment,
            )

    extraction_start = 3
    _write_extraction_blocks(
        sheet,
        extraction_start,
        answers,
        section_fill,
        value_fill,
        review_fill,
        auto_fill,
        border,
        Font,
        Alignment,
    )

    for row_cells in sheet.iter_rows():
        for cell in row_cells:
            cell.alignment = Alignment(vertical="top", wrap_text=True)
    sheet.freeze_panes = "A3"


def _write_extraction_blocks(sheet: Any, start_row: int, answers: dict[str, FinalAnswer], section_fill: Any, value_fill: Any, review_fill: Any, auto_fill: Any, border: Any, Font: Any, Alignment: Any) -> None:
    row = start_row
    sheet.merge_cells(start_row=row, start_column=5, end_row=row, end_column=8)
    cell = sheet.cell(row=row, column=5)
    cell.value = "Methodological extraction"
    cell.font = Font(bold=True)
    cell.fill = section_fill
    cell.alignment = Alignment(horizontal="center")
    row += 1
    headers = ["Item", "Answer", "Confidence", "Status"]
    for offset, header in enumerate(headers, start=5):
        cell = sheet.cell(row=row, column=offset)
        cell.value = header
        cell.font = Font(bold=True)
        cell.fill = section_fill
        cell.border = border
    row += 1
    for item in EXTRACTION_ITEMS:
        answer = answers.get(item.id)
        if answer is None:
            continue
        fill = review_fill if answer.review_required else auto_fill if answer.validator_status == "auto_absent" else value_fill
        values = [
            item.id,
            _stringify(answer.final_answer),
            answer.final_confidence,
            answer.validator_status,
        ]
        for offset, value in enumerate(values, start=5):
            cell = sheet.cell(row=row, column=offset)
            cell.value = value
            cell.fill = fill
            cell.border = border
        row += 1


def _write_section_title(sheet: Any, row: int, title: str, fill: Any, Font: Any, Alignment: Any) -> int:
    sheet.merge_cells(start_row=row, start_column=1, end_row=row, end_column=4)
    cell = sheet.cell(row=row, column=1)
    cell.value = title
    cell.font = Font(bold=True)
    cell.fill = fill
    cell.alignment = Alignment(horizontal="center")
    return row + 1


def _write_key_value(sheet: Any, row: int, label: str, value: Any, confidence: Any, evidence: Any, fill: Any, border: Any, Alignment: Any) -> int:
    values = [label, value if value not in {None, ""} else "NR", confidence, evidence]
    for column, cell_value in enumerate(values, start=1):
        cell = sheet.cell(row=row, column=column)
        cell.value = cell_value
        cell.fill = fill
        cell.border = border
        cell.alignment = Alignment(vertical="top", wrap_text=True)
    return row + 1


def _metadata_value(metadata: dict[str, Any], field_id: str) -> str:
    field = metadata.get(field_id)
    return field.value if field else ""


def _metadata_confidence(metadata: dict[str, Any], field_id: str) -> float | str:
    field = metadata.get(field_id)
    return field.confidence if field else ""


def _metadata_evidence(metadata: dict[str, Any], field_id: str) -> str:
    field = metadata.get(field_id)
    return _evidence_text(field.evidence) if field else ""


def _evidence_text(evidence: list[Any]) -> str:
    snippets = []
    for item in evidence[:2]:
        page = f"p.{item.page}: " if item.page is not None else ""
        snippets.append(f"{page}{item.quote}")
    return " | ".join(snippets)


def _stringify(value: str | list[str]) -> str:
    return "; ".join(value) if isinstance(value, list) else str(value)


def _study_letter(result: ArticleResult) -> str:
    study_id = next((field.value for field in result.study_metadata if field.field_id == "study_id" and field.value), result.article_id)
    match = re.search(r"[A-Za-z]", study_id)
    return match.group(0).upper() if match else "Other"


def _sheet_title(result: ArticleResult, existing: list[str]) -> str:
    base = next((field.value for field in result.study_metadata if field.field_id == "study_id" and field.value), result.article_id)
    base = re.sub(r"[\[\]\:\*\?\/\\]", "_", base)[:31] or "Study"
    title = base
    counter = 2
    while title in existing:
        suffix = f"_{counter}"
        title = f"{base[:31 - len(suffix)]}{suffix}"
        counter += 1
    return title
