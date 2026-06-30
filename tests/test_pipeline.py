import json
import tempfile
import unittest
from pathlib import Path

from review_extraction.pipeline import process_many


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
            self.assertEqual(json.loads((out_dir / "index.json").read_text(encoding="utf-8")), [])


if __name__ == "__main__":
    unittest.main()
