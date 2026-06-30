import csv
import tempfile
import unittest
from pathlib import Path

from review_extraction.export import write_csv_summary
from review_extraction.models import ArticleResult, Evidence, FinalAnswer, FinalScreeningResult


class ExportTests(unittest.TestCase):
    def test_write_csv_summary_flattens_answers_and_evidence(self) -> None:
        result = ArticleResult(
            article_id="paper",
            source_pdf="paper.pdf",
            answers=[
                FinalAnswer(
                    item_id="measurement_methods",
                    final_answer=["skin_markers_3d_optical", "skin_imu"],
                    extractor_answer=["skin_markers_3d_optical"],
                    validator_status="partial",
                    validator_answer=["skin_markers_3d_optical", "skin_imu"],
                    extractor_confidence=0.7,
                    validator_confidence=0.8,
                    final_confidence=0.68,
                    evidence=[
                        Evidence(page=3, quote="Motion was captured using optical markers.", relevance="optical system"),
                        Evidence(page=4, quote="IMUs were also used.", relevance="IMU system"),
                    ],
                    rationale_short="Two methods are supported.",
                    review_required=True,
                )
            ],
        )

        with tempfile.TemporaryDirectory() as tmp:
            out_path = Path(tmp) / "summary.csv"
            write_csv_summary([result], out_path)

            with out_path.open(newline="", encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))

        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["article_id"], "paper")
        self.assertEqual(row["final_answer"], "skin_markers_3d_optical; skin_imu")
        self.assertEqual(row["review_required"], "True")
        self.assertEqual(row["validator_status"], "partial")
        self.assertEqual(row["evidence_pages"], "3; 4")
        self.assertIn("optical markers", row["evidence_quotes"])
        self.assertIn("IMUs", row["evidence_quotes"])

    def test_write_csv_summary_includes_screening_only_rows(self) -> None:
        result = ArticleResult(
            article_id="excluded",
            source_pdf="excluded.pdf",
            screening=FinalScreeningResult(
                article_id="excluded",
                overall_decision="exclude",
                final_confidence=0.92,
                review_required=False,
                extraction_allowed=False,
                criteria=[],
            ),
            answers=[],
        )

        with tempfile.TemporaryDirectory() as tmp:
            out_path = Path(tmp) / "summary.csv"
            write_csv_summary([result], out_path)

            with out_path.open(newline="", encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))

        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["article_id"], "excluded")
        self.assertEqual(row["screening_decision"], "exclude")
        self.assertEqual(row["screening_confidence"], "0.92")
        self.assertEqual(row["screening_review_required"], "False")
        self.assertEqual(row["item_id"], "")


if __name__ == "__main__":
    unittest.main()
