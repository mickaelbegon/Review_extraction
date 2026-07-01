import csv
import tempfile
import unittest
from pathlib import Path

from review_extraction.benchmark import (
    compare_article,
    compare_model_results,
    load_reference_results,
    safe_model_dir_name,
    summarize_benchmarks,
    write_benchmark_reports,
)
from review_extraction.models import ArticleResult, Evidence, FinalAnswer, FinalScreeningResult, TokenUsage


def article(article_id: str, *, answer: str, decision: str = "include", confidence: float = 0.9) -> ArticleResult:
    return ArticleResult(
        article_id=article_id,
        source_pdf=f"{article_id}.pdf",
        screening=FinalScreeningResult(
            article_id=article_id,
            overall_decision=decision,
            final_confidence=confidence,
            review_required=False,
            extraction_allowed=decision == "include",
            criteria=[],
        ),
        answers=[
            FinalAnswer(
                item_id="thorax_used",
                final_answer=answer,
                extractor_answer=answer,
                validator_status="agree",
                validator_answer=None,
                extractor_confidence=confidence,
                validator_confidence=confidence,
                final_confidence=confidence,
                evidence=[Evidence(page=1, quote="Thorax was tracked.", relevance="segment use")],
                rationale_short="Supported.",
                review_required=False,
            )
        ],
        usage=[
            TokenUsage(
                step="extraction",
                model="candidate",
                input_tokens=100,
                output_tokens=20,
                total_tokens=120,
                estimated_cost_usd=0.001,
            )
        ],
    )


class BenchmarkTests(unittest.TestCase):
    def test_compare_article_detects_answer_disagreement(self) -> None:
        reference = article("paper", answer="yes")
        candidate = article("paper", answer="no", confidence=0.7)

        row, disagreements = compare_article(model="candidate", reference=reference, candidate=candidate)

        self.assertFalse(row["screening_match"] is False)
        self.assertEqual(row["matching_items"], 0)
        self.assertEqual(row["answer_agreement_rate"], 0)
        self.assertEqual(row["candidate_total_tokens"], 120)
        self.assertEqual(row["candidate_estimated_cost_usd"], 0.001)
        self.assertEqual(len(disagreements), 1)
        self.assertEqual(disagreements[0]["item_id"], "thorax_used")
        self.assertEqual(disagreements[0]["reference_value"], "yes")
        self.assertEqual(disagreements[0]["candidate_value"], "no")

    def test_summarize_benchmarks_aggregates_model_metrics(self) -> None:
        reference_results = {
            "paper1": article("paper1", answer="yes"),
            "paper2": article("paper2", answer="no"),
        }
        benchmark = compare_model_results(
            model="candidate",
            reference_results=reference_results,
            candidate_results=[article("paper1", answer="yes"), article("paper2", answer="yes")],
        )

        summary = summarize_benchmarks([benchmark])[0]

        self.assertEqual(summary["articles"], 2)
        self.assertEqual(summary["screening_agreement_rate"], 1.0)
        self.assertEqual(summary["answer_agreement_rate"], 0.5)
        self.assertEqual(summary["candidate_total_tokens"], 240)
        self.assertEqual(summary["candidate_estimated_cost_usd"], 0.002)
        self.assertEqual(summary["disagreements"], 1)

    def test_write_benchmark_reports_creates_csv_and_xlsx(self) -> None:
        benchmark = compare_model_results(
            model="candidate",
            reference_results={"paper": article("paper", answer="yes")},
            candidate_results=[article("paper", answer="no")],
        )

        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp)
            write_benchmark_reports([benchmark], out_dir)

            with (out_dir / "benchmark_summary.csv").open(newline="", encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))

            self.assertEqual(rows[0]["model"], "candidate")
            self.assertTrue((out_dir / "benchmark_articles.csv").exists())
            self.assertTrue((out_dir / "benchmark_disagreements.csv").exists())
            self.assertTrue((out_dir / "benchmark.xlsx").exists())

    def test_load_reference_results_uses_filename_as_stable_article_id(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp)
            changed = article("model_changed_id", answer="yes")
            (out_dir / "paper.json").write_text(changed.model_dump_json(indent=2), encoding="utf-8")

            loaded = load_reference_results(out_dir)

            self.assertIn("paper", loaded)
            self.assertEqual(loaded["paper"].article_id, "paper")

    def test_safe_model_dir_name_removes_path_unsafe_characters(self) -> None:
        self.assertEqual(safe_model_dir_name("gpt-5.4 mini/test"), "gpt-5.4_mini_test")


if __name__ == "__main__":
    unittest.main()
