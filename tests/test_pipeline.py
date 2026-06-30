import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import ModuleType, SimpleNamespace

from review_extraction.models import (
    ArticleResult,
    Evidence,
    ExtractedAnswer,
    ExtractionResult,
    ScreeningCriterionAnswer,
    ScreeningResult,
    ScreeningValidationDecision,
    ScreeningValidationResult,
    ValidationDecision,
    ValidationResult,
)
from review_extraction.pipeline import process_many, process_pdf


class ExplodingAgents:
    def screen(self, *args, **kwargs):
        raise AssertionError("AI screening should not be called when cached JSON exists.")

    def validate_screening(self, *args, **kwargs):
        raise AssertionError("AI screening validation should not be called when cached JSON exists.")

    def extract(self, *args, **kwargs):
        raise AssertionError("AI extraction should not be called when cached JSON exists.")

    def validate(self, *args, **kwargs):
        raise AssertionError("AI validation should not be called when cached JSON exists.")


class RecordingAgents:
    def __init__(self) -> None:
        self.screen_contexts: list[str] = []
        self.screen_validation_contexts: list[str] = []
        self.extraction_contexts: list[str] = []
        self.validation_contexts: list[str] = []

    def screen(self, article_id: str, paper_context: str) -> ScreeningResult:
        self.screen_contexts.append(paper_context)
        return ScreeningResult(
            article_id=article_id,
            overall_decision="include",
            criteria=[
                ScreeningCriterionAnswer(
                    criterion_id="population",
                    decision="include",
                    confidence=0.9,
                    evidence=[
                        Evidence(
                            page=1,
                            quote="Healthy human participants",
                            relevance="Supports human population inclusion.",
                        )
                    ],
                    rationale_short="Human participants.",
                )
            ],
        )

    def validate_screening(
        self,
        article_id: str,
        paper_context: str,
        screening: ScreeningResult,
    ) -> ScreeningValidationResult:
        self.screen_validation_contexts.append(paper_context)
        return ScreeningValidationResult(
            article_id=article_id,
            overall_status="agree",
            corrected_overall_decision=None,
            decisions=[
                ScreeningValidationDecision(
                    criterion_id="population",
                    status="agree",
                    corrected_decision=None,
                    confidence=0.9,
                    evidence=[],
                    critique="Supported.",
                )
            ],
        )

    def extract(self, article_id: str, paper_context: str) -> ExtractionResult:
        self.extraction_contexts.append(paper_context)
        return ExtractionResult(
            article_id=article_id,
            answers=[
                ExtractedAnswer(
                    item_id="thorax_used",
                    answer="yes",
                    confidence=0.8,
                    evidence=[
                        Evidence(
                            page=2,
                            quote="Thorax and humerus coordinate systems",
                            relevance="Shows thorax segment use.",
                        )
                    ],
                    rationale_short="Thorax coordinate system reported.",
                    needs_human_review=False,
                )
            ],
        )

    def validate(self, article_id: str, paper_context: str, extraction: ExtractionResult) -> ValidationResult:
        self.validation_contexts.append(paper_context)
        return ValidationResult(
            article_id=article_id,
            decisions=[
                ValidationDecision(
                    item_id="thorax_used",
                    status="agree",
                    corrected_answer=None,
                    confidence=0.9,
                    evidence=[],
                    critique="Supported.",
                )
            ],
        )


class PipelineTests(unittest.TestCase):
    def test_process_many_creates_outputs_for_empty_pdf_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            input_dir = root / "pdf_input"
            out_dir = root / "outputs"
            input_dir.mkdir()

            results = process_many(input_dir, out_dir, agents=object(), write_highlights=False)

            self.assertEqual(results, [])
            self.assertTrue((out_dir / "index.json").exists())
            self.assertTrue((out_dir / "summary.csv").exists())
            self.assertTrue((out_dir / "summary.xlsx").exists())
            self.assertEqual(json.loads((out_dir / "index.json").read_text(encoding="utf-8")), [])

    def test_process_pdf_reuses_existing_article_json_without_ai_calls(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pdf_path = root / "paper.pdf"
            out_dir = root / "outputs"
            out_dir.mkdir()
            result = ArticleResult(article_id="paper", source_pdf=str(pdf_path), answers=[])
            (out_dir / "paper.json").write_text(result.model_dump_json(indent=2), encoding="utf-8")

            loaded = process_pdf(pdf_path, out_dir, agents=ExplodingAgents(), write_highlights=False)

            self.assertEqual(loaded.article_id, "paper")
            self.assertEqual(loaded.answers, [])

    def test_process_many_reports_progress_for_cached_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            input_dir = root / "pdf_input"
            out_dir = root / "outputs"
            input_dir.mkdir()
            out_dir.mkdir()
            pdf_path = input_dir / "paper.pdf"
            pdf_path.write_bytes(b"%PDF-1.4\n")
            result = ArticleResult(article_id="paper", source_pdf=str(pdf_path), answers=[])
            (out_dir / "paper.json").write_text(result.model_dump_json(indent=2), encoding="utf-8")
            messages: list[str] = []

            process_many(
                input_dir,
                out_dir,
                agents=ExplodingAgents(),
                write_highlights=False,
                progress=messages.append,
            )

            self.assertIn("Found 1 PDF(s) to process.", messages)
            self.assertTrue(any("[1/1] paper.pdf: reuse existing JSON: paper.json" in message for message in messages))
            self.assertIn("[1/1] paper.pdf: done", messages)
            self.assertIn("write index.json", messages)
            self.assertIn("write summary.csv", messages)

    def test_force_ignores_cached_article_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pdf_path = root / "paper.pdf"
            out_dir = root / "outputs"
            out_dir.mkdir()
            result = ArticleResult(article_id="paper", source_pdf=str(pdf_path), answers=[])
            (out_dir / "paper.json").write_text(result.model_dump_json(indent=2), encoding="utf-8")
            fake_pdf_ingest = ModuleType("review_extraction.pdf_ingest")
            fake_pdf_ingest.extract_pdf_text = lambda path: []
            fake_pdf_ingest.pages_to_prompt_context = lambda pages: ""
            original_pdf_ingest = sys.modules.get("review_extraction.pdf_ingest")
            sys.modules["review_extraction.pdf_ingest"] = fake_pdf_ingest

            try:
                with self.assertRaises(AssertionError):
                    process_pdf(
                        pdf_path,
                        out_dir,
                        agents=ExplodingAgents(),
                        write_highlights=False,
                        reuse_existing=False,
                    )
            finally:
                if original_pdf_ingest is None:
                    sys.modules.pop("review_extraction.pdf_ingest", None)
                else:
                    sys.modules["review_extraction.pdf_ingest"] = original_pdf_ingest

    def test_process_pdf_uses_targeted_contexts_for_ai_calls(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pdf_path = root / "paper.pdf"
            pdf_path.write_bytes(b"%PDF-1.4\n")
            out_dir = root / "outputs"
            pages = [
                SimpleNamespace(page=1, text="Abstract. Healthy human participants completed shoulder tasks."),
                SimpleNamespace(page=2, text="Methods. Thorax and humerus coordinate systems used marker clusters."),
                SimpleNamespace(page=3, text="Unrelated filler. " * 500),
            ]
            fake_pdf_ingest = ModuleType("review_extraction.pdf_ingest")
            fake_pdf_ingest.extract_pdf_text = lambda path: pages
            original_pdf_ingest = sys.modules.get("review_extraction.pdf_ingest")
            sys.modules["review_extraction.pdf_ingest"] = fake_pdf_ingest
            agents = RecordingAgents()

            try:
                result = process_pdf(pdf_path, out_dir, agents=agents, write_highlights=False)
            finally:
                if original_pdf_ingest is None:
                    sys.modules.pop("review_extraction.pdf_ingest", None)
                else:
                    sys.modules["review_extraction.pdf_ingest"] = original_pdf_ingest

            self.assertEqual(result.article_id, "paper")
            self.assertEqual(len(agents.screen_contexts), 1)
            self.assertEqual(len(agents.extraction_contexts), 1)
            self.assertIn("TARGETED FULL-PAPER SCREENING CONTEXT", agents.screen_contexts[0])
            self.assertIn("TARGETED METHODOLOGY EXTRACTION CONTEXT", agents.extraction_contexts[0])
            self.assertIn("TARGETED METHODOLOGY EXTRACTION CONTEXT", agents.validation_contexts[0])
            self.assertGreaterEqual(len(agents.screen_validation_contexts[0]), len(agents.screen_contexts[0]))
            self.assertGreaterEqual(len(agents.validation_contexts[0]), len(agents.extraction_contexts[0]))


if __name__ == "__main__":
    unittest.main()
