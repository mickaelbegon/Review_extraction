import json
import tempfile
import unittest
from pathlib import Path

import fitz

from review_extraction.form_schema import EXTRACTION_ITEMS
from review_extraction.pdf_ingest import find_figure_pages
from review_extraction.study_metadata_schema import STUDY_METADATA_ITEMS
from review_extraction.validation_run import export_workbook, match_pdfs, parse_filename
from review_extraction.variables import read_wide_table


def make_pdf(path: Path, lines: list[str]) -> None:
    doc = fitz.open()
    page = doc.new_page()
    for i, line in enumerate(lines):
        page.insert_text((72, 72 + 30 * i), line)
    doc.save(path)
    doc.close()


class FilenameTests(unittest.TestCase):
    def test_zotero_and_short_patterns(self) -> None:
        a = parse_filename("Abadia et al. - 2012 - Functional movement modeling for robot (1).pdf")
        self.assertEqual((a["author"], a["year"], a["title"]), ("abadia", "2012", "functionalmovementmodelingforrobot"))
        b = parse_filename("Aarseth-2015-Kinesio Tape and Shoulder-Joint P.pdf")
        self.assertEqual((b["author"], b["year"]), ("aarseth", "2015"))


class MatchTests(unittest.TestCase):
    def test_matches_truncated_title_and_skips_other_year(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            make_pdf(folder / "Doe et al. - 2015 - Scapular kinematics during arm.pdf", ["Scapular kinematics during arm elevation"])
            make_pdf(folder / "Roe - 2020 - Unrelated paper.pdf", ["Unrelated paper"])
            studies = {"cov1": {"Title": "Scapular kinematics during arm elevation", "Published Year": "2015", "Study": "Doe 2015"}}
            rows = match_pdfs([{"article_id": "cov1"}], studies, folder)
            self.assertEqual(rows[0]["status"], "matched")
            self.assertTrue(rows[0]["pdf_file"].startswith("Doe"))

    def test_falls_back_to_pdf_text(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            make_pdf(folder / "scan_0001.pdf", ["Glenohumeral translations measured with biplane fluoroscopy"])
            studies = {"cov2": {"Title": "Glenohumeral translations measured with biplane fluoroscopy", "Published Year": "2019", "Study": "X 2019"}}
            rows = match_pdfs([{"article_id": "cov2"}], studies, folder)
            self.assertEqual((rows[0]["status"], rows[0]["method"]), ("matched", "pdf_text"))


class FigureTests(unittest.TestCase):
    def test_methods_caption_is_high_priority(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pdf = Path(tmp) / "p.pdf"
            doc = fitz.open()
            doc.new_page().insert_text((72, 72), "Figure 1. Mean elevation angle across trials")
            doc.new_page().insert_text((72, 72), "Fig. 2 Local coordinate system of the humerus")
            doc.save(pdf)
            doc.close()
            figures = find_figure_pages(pdf)
            self.assertEqual([(f.page, f.priority) for f in figures], [(1, "low"), (2, "high")])
            self.assertEqual(find_figure_pages(pdf, max_pages=1)[0].page, 2)


class ExportTests(unittest.TestCase):
    def test_extraction_sheet_has_rater_layout(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            results = Path(tmp) / "res"
            results.mkdir()
            answers = [
                {"item_id": i.id, "final_answer": i.allowed_answers[0], "extractor_answer": i.allowed_answers[0],
                 "validator_status": "none", "validator_answer": None, "extractor_confidence": 0.9,
                 "validator_confidence": 0, "final_confidence": 0.9, "evidence": [], "rationale_short": "r",
                 "review_required": i.id == "measurement_methods"}
                for i in EXTRACTION_ITEMS
            ]
            meta = [{"field_id": m.id, "value": "France" if m.id == "affiliation_countries" else "NR", "confidence": 0.9,
                     "evidence": [], "rationale_short": ""} for m in STUDY_METADATA_ITEMS]
            (results / "cov1.json").write_text(json.dumps({"article_id": "cov1", "source_pdf": "x.pdf", "screening": None,
                                                          "study_metadata": meta, "answers": answers}), encoding="utf-8")
            sample = [{"article_id": "cov1", "subset": "test", "label": "Doe 2015"}, {"article_id": "cov2", "subset": "test", "label": ""}]
            studies = {"cov1": {"Journal": "Journal of Biomechanics", "Title": "T"}}
            out = Path(tmp) / "ai.xlsx"
            stats = export_workbook(results, sample, studies, out, {"JOURNAL OF BIOMECHANICS": {"journal_class": "biomechanics"}})
            self.assertEqual(stats, {"articles": 2, "extracted": 1, "flagged_answers": 1})
            table = read_wide_table(out)
            self.assertEqual(set(table), {"cov1", "cov2"})
            self.assertEqual(table["cov2"]["thorax_used"], "")
            from openpyxl import load_workbook

            wb = load_workbook(out)
            header = [c.value for c in wb["Study metadata"][1]]
            row = [c.value for c in wb["Study metadata"][2]]
            self.assertEqual(row[header.index("journal_class")], "biomechanics")
            self.assertEqual(row[header.index("affiliation_countries")], "France")


if __name__ == "__main__":
    unittest.main()
