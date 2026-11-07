import json
import tempfile
import unittest
from pathlib import Path

import fitz

from review_extraction.agent_io import finalize, prepare
from review_extraction.form_schema import EXTRACTION_ITEMS
from review_extraction.study_metadata_schema import STUDY_METADATA_ITEMS

QUOTE = "Shoulder kinematics were measured with skin markers"


class AgentIoTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.pdf = self.tmp / "paper.pdf"
        doc = fitz.open()
        doc.new_page().insert_text((72, 72), QUOTE + " and a camera system.")
        doc.save(self.pdf)
        doc.close()

    def _write(self, answers_patch=None) -> None:
        folder = prepare(self.pdf, self.tmp / "work")
        evidence = [{"page": 1, "quote": QUOTE, "relevance": "x"}]
        answers = [
            {"item_id": i.id, "answer": i.allowed_answers[-1], "confidence": 0.9, "evidence": evidence,
             "rationale_short": "r", "needs_human_review": False}
            for i in EXTRACTION_ITEMS
        ]
        if answers_patch:
            answers_patch(answers)
        meta = [{"field_id": i.id, "value": "NR", "confidence": 0.9, "evidence": [], "rationale_short": "r"}
                for i in STUDY_METADATA_ITEMS]
        (folder / "extraction.json").write_text(json.dumps({"answers": answers, "study_metadata": meta}), encoding="utf-8")

    def test_valid_extraction_is_exported(self) -> None:
        self._write()
        result, errors = finalize(self.pdf, self.tmp / "work", self.tmp / "out")
        self.assertEqual(errors, [])
        self.assertTrue((self.tmp / "out" / "paper.json").exists())
        self.assertTrue((self.tmp / "out" / "summary.csv").exists())
        self.assertIsNone(result.screening)
        self.assertFalse(any(a.review_required for a in result.answers))

    def test_invalid_answer_is_rejected(self) -> None:
        self._write(lambda a: a[0].update(answer="bogus"))
        result, errors = finalize(self.pdf, self.tmp / "work", self.tmp / "out")
        self.assertIsNone(result)
        self.assertTrue(any("not allowed" in e for e in errors))

    def test_default_answer_needs_no_quote(self) -> None:
        self._write(lambda a: a[0].update(answer="not_reported", evidence=[]))
        result, _ = finalize(self.pdf, self.tmp / "work", self.tmp / "out")
        self.assertFalse(result.answers[0].review_required)

    def test_fabricated_quote_flags_review(self) -> None:
        self._write(lambda a: a[0].update(answer="skin_markers_3d_optical", evidence=[{"page": 1, "quote": "never written", "relevance": "x"}]))
        result, _ = finalize(self.pdf, self.tmp / "work", self.tmp / "out")
        self.assertTrue(result.answers[0].review_required)
        self.assertEqual(result.answers[0].evidence, [])


if __name__ == "__main__":
    unittest.main()
