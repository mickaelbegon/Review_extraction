import csv
import random
import tempfile
import unittest
from pathlib import Path

from review_extraction.agreement import cohen_kappa, compare_tables, wilson_ci
from review_extraction.models import ArticleResult, FinalAnswer
from review_extraction.sampling import assign_subsets, stratified_sample, subset_sizes, write_template
from review_extraction.variables import build_variables, read_wide_table, result_to_row, write_wide_csv


def _answer(item_id, value):
    return FinalAnswer(
        item_id=item_id, final_answer=value, extractor_answer=value, validator_status="none",
        extractor_confidence=1, validator_confidence=0, final_confidence=1, rationale_short="", review_required=False,
    )


class BinaryExportTests(unittest.TestCase):
    def test_multi_response_items_become_binary_variables(self) -> None:
        result = ArticleResult(
            article_id="a", source_pdf="a.pdf",
            answers=[_answer("measurement_methods", ["skin_imu", "skin_markers_3d_optical"]), _answer("thorax_used", "yes")],
        )
        row = result_to_row(result)
        self.assertEqual(row["measurement_methods__skin_imu"], "1")
        self.assertEqual(row["measurement_methods__skin_markers_2d_video"], "0")
        self.assertEqual(row["thorax_used"], "yes")
        self.assertEqual(row["clavicle_used"], "")
        self.assertNotIn("measurement_methods", row)

    def test_csv_roundtrip(self) -> None:
        tmp = Path(tempfile.mkdtemp()) / "t.csv"
        result = ArticleResult(article_id="a", source_pdf="a.pdf", answers=[_answer("thorax_used", "no")])
        write_wide_csv([result_to_row(result)], tmp)
        self.assertEqual(read_wide_table(tmp)["a"]["thorax_used"], "no")


class AgreementTests(unittest.TestCase):
    def test_kappa_known_value(self) -> None:
        a = ["y"] * 20 + ["y"] * 5 + ["n"] * 10 + ["n"] * 15
        b = ["y"] * 20 + ["n"] * 5 + ["y"] * 10 + ["n"] * 15
        self.assertAlmostEqual(cohen_kappa(a, b), 0.4, places=6)  # classic 50-item example

    def test_kappa_undefined_without_variance(self) -> None:
        self.assertIsNone(cohen_kappa(["a"] * 5, ["a"] * 5))

    def test_wilson_bounds(self) -> None:
        low, high = wilson_ci(9, 10)
        self.assertTrue(0.55 < low < 0.6 and 0.97 < high <= 1.0)

    def test_compare_tables_and_domain_verdict(self) -> None:
        names = [v.name for v in build_variables()]
        ids = [f"s{i}" for i in range(20)]
        table_a = {i: {n: "0" if n.endswith("__skin_imu") else "" for n in names} for i in ids}
        table_b = {i: dict(row) for i, row in table_a.items()}
        for i, article in enumerate(ids):  # alternating positives, identical in both raters
            table_a[article]["thorax_used"] = table_b[article]["thorax_used"] = "yes" if i % 2 else "no"
        stats, domains, compared = compare_tables(table_a, table_b, reps=50)
        self.assertEqual(len(compared), 20)
        thorax = next(s for s in stats if s.variable.name == "thorax_used")
        self.assertEqual(thorax.verdict, "pass")
        # introduce disagreement on 5 articles -> fails kappa threshold
        for article in ids[:5]:
            table_b[article]["thorax_used"] = "no" if table_a[article]["thorax_used"] == "yes" else "yes"
        stats, domains, _ = compare_tables(table_a, table_b, reps=50)
        thorax = next(s for s in stats if s.variable.name == "thorax_used")
        self.assertEqual(thorax.verdict, "fail")
        domain = next(d for d in domains if d["domain"] == "segment.thorax")
        self.assertFalse(domain["domain_suitable_for_autonomous_extraction"])


class SamplingTests(unittest.TestCase):
    def _rows(self):
        return [{"article_id": f"a{i:04d}", "year_bin": "2010s" if i % 3 else "2020s"} for i in range(1700)]

    def test_sizes_and_stratification(self) -> None:
        self.assertEqual(sum(subset_sizes(170, (40, 30, 100), 1).values()), 170)
        self.assertEqual(subset_sizes(170, (40, 30, 100), 1), {"development": 40, "tuning": 30, "test": 100})
        sample = stratified_sample(self._rows(), n=170, strata_cols=["year_bin"], seed=1)
        self.assertEqual(len(sample), 170)
        share_2020 = sum(r["year_bin"] == "2020s" for r in sample) / 170
        self.assertAlmostEqual(share_2020, 1 / 3, delta=0.02)
        split = assign_subsets(sample, {"development": 40, "tuning": 30, "test": 100}, 1)
        self.assertEqual(sum(r["subset"] == "test" for r in split), 100)
        test_2020 = sum(r["subset"] == "test" and r["year_bin"] == "2020s" for r in split) / 100
        self.assertAlmostEqual(test_2020, 1 / 3, delta=0.08)

    def test_deterministic(self) -> None:
        first = [r["article_id"] for r in stratified_sample(self._rows(), n=170, strata_cols=["year_bin"], seed=7)]
        second = [r["article_id"] for r in stratified_sample(self._rows(), n=170, strata_cols=["year_bin"], seed=7)]
        self.assertEqual(first, second)

    def test_template_is_blank_and_roundtrips(self) -> None:
        path = Path(tempfile.mkdtemp()) / "t.xlsx"
        write_template(path, ["a", "b"])
        table = read_wide_table(path)
        self.assertEqual(set(table), {"a", "b"})
        self.assertEqual(table["a"]["thorax_used"], "")


if __name__ == "__main__":
    unittest.main()
