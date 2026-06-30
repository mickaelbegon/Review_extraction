import unittest

from review_extraction.pdf_ingest import PageText
from review_extraction.targeted_context import build_extraction_context, build_full_context, build_screening_context


class TargetedContextTests(unittest.TestCase):
    def test_screening_context_selects_relevant_pages_and_reduces_text(self) -> None:
        pages = [
            PageText(page=1, text="Abstract. Healthy human participants performed shoulder elevation tasks."),
            PageText(page=2, text="Methods. Participants were adults. Shoulder kinematics were measured prospectively."),
            PageText(page=3, text="This page is unrelated filler. " * 300),
            PageText(page=4, text="\nReferences\nA paper about shoulder kinematics in animals."),
        ]

        full = build_full_context(pages)
        targeted = build_screening_context(pages, max_chars=3_000)

        self.assertLess(targeted.selected_chars, full.selected_chars)
        self.assertIn(1, targeted.selected_pages)
        self.assertIn(2, targeted.selected_pages)
        self.assertNotIn("References", targeted.text)

    def test_extraction_context_prioritizes_methodology_terms(self) -> None:
        pages = [
            PageText(page=1, text="Abstract. Shoulder motion was studied."),
            PageText(page=2, text="Methods. Markers defined the thorax, scapula, humerus and clavicle coordinate systems."),
            PageText(page=3, text="Euler rotation sequence Y-X-Y was used for humeral rotations."),
            PageText(page=4, text="General discussion without extraction-relevant details. " * 200),
        ]

        targeted = build_extraction_context(pages, max_chars=4_000)

        self.assertIn(2, targeted.selected_pages)
        self.assertIn(3, targeted.selected_pages)
        self.assertIn("coordinate systems", targeted.text)
        self.assertIn("Y-X-Y", targeted.text)


if __name__ == "__main__":
    unittest.main()
