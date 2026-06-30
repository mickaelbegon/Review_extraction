import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import ModuleType

from review_extraction.models import ArticleResult
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


if __name__ == "__main__":
    unittest.main()
