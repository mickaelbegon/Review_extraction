import csv
import tempfile
import unittest
import zipfile
from pathlib import Path

from review_extraction.covidence import (
    covidence_extraction_rows,
    covidence_screening_rows,
    export_results,
    import_pdfs,
)
from review_extraction.models import ArticleResult, Evidence, FinalAnswer, FinalScreeningCriterion, FinalScreeningResult


def result() -> ArticleResult:
    return ArticleResult(
        article_id="paper",
        source_pdf="paper.pdf",
        screening=FinalScreeningResult(
            article_id="paper",
            overall_decision="include",
            final_confidence=0.91,
            review_required=False,
            extraction_allowed=True,
            criteria=[
                FinalScreeningCriterion(
                    criterion_id="population",
                    final_decision="include",
                    screener_decision="include",
                    validator_status="agree",
                    validator_decision=None,
                    screener_confidence=0.9,
                    validator_confidence=0.92,
                    final_confidence=0.91,
                    evidence=[Evidence(page=2, quote="Healthy human participants", relevance="population")],
                    rationale_short="Human participants.",
                    review_required=False,
                )
            ],
        ),
        answers=[
            FinalAnswer(
                item_id="thorax_used",
                final_answer="yes",
                extractor_answer="yes",
                validator_status="agree",
                validator_answer=None,
                extractor_confidence=0.8,
                validator_confidence=0.9,
                final_confidence=0.85,
                evidence=[Evidence(page=3, quote="Thorax coordinate system", relevance="segment")],
                rationale_short="Thorax was used.",
                review_required=False,
            )
        ],
    )


class CovidenceTests(unittest.TestCase):
    def test_import_pdfs_from_directory_copies_and_writes_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "covidence"
            source.mkdir()
            (source / "Study 1.pdf").write_bytes(b"%PDF-1.4\n")
            out_dir = root / "pdf_input"

            summary = import_pdfs(source, out_dir)

            self.assertEqual(summary.copied, 1)
            self.assertEqual(summary.skipped, 0)
            self.assertTrue((out_dir / "Study_1.pdf").exists())
            with summary.manifest_path.open(newline="", encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(rows[0]["article_id"], "Study_1")
            self.assertEqual(rows[0]["status"], "copied")

    def test_import_pdfs_from_zip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            zip_path = root / "covidence.zip"
            with zipfile.ZipFile(zip_path, "w") as archive:
                archive.writestr("full_texts/Nested Study.pdf", b"%PDF-1.4\n")

            summary = import_pdfs(zip_path, root / "pdf_input")

            self.assertEqual(summary.copied, 1)
            self.assertTrue((root / "pdf_input" / "Nested_Study.pdf").exists())

    def test_covidence_rows_map_screening_and_extraction(self) -> None:
        rows = covidence_screening_rows([result()])
        extraction = covidence_extraction_rows([result()])

        self.assertEqual(rows[0]["covidence_decision"], "include")
        self.assertIn("population: include", rows[0]["criteria_summary"])
        self.assertEqual(extraction[0]["item_id"], "thorax_used")
        self.assertEqual(extraction[0]["answer"], "yes")

    def test_export_results_writes_csv_and_workbook(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            results_dir = root / "outputs"
            results_dir.mkdir()
            (results_dir / "paper.json").write_text(result().model_dump_json(indent=2), encoding="utf-8")

            summary = export_results(results_dir, root / "covidence_export")

            self.assertEqual(summary.articles, 1)
            self.assertTrue(summary.screening_csv.exists())
            self.assertTrue(summary.extraction_csv.exists())
            self.assertTrue(summary.workbook_path.exists())


if __name__ == "__main__":
    unittest.main()
