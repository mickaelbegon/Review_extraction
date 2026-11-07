"""Agreement statistics for the validation study (human-human and Claude-vs-human consensus).

Per variable: n, exact % agreement (Wilson 95% CI), unweighted Cohen kappa (percentile bootstrap 95% CI over
articles, fixed seed). Pre-specified thresholds: kappa >= 0.80 AND exact agreement >= 90%. A variable whose kappa is
undefined because both raters are constant passes only if agreement is 100%. A domain (form theme) is
"suitable for autonomous extraction" only when EVERY evaluable variable in it passes (conservative reading of the
protocol; shares and pooled agreement are reported next to it).

The held-out test subset can be evaluated once: a lock file is written next to the report.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import random
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .variables import Variable, build_variables, read_wide_table

KAPPA_THRESHOLD = 0.80
AGREEMENT_THRESHOLD = 0.90


@dataclass
class VarStats:
    variable: Variable
    n: int
    agreement: float | None
    agreement_ci: tuple[float, float] | None
    kappa: float | None
    kappa_ci: tuple[float, float] | None
    verdict: str


def cohen_kappa(a: list[str], b: list[str]) -> float | None:
    n = len(a)
    if n == 0:
        return None
    po = sum(x == y for x, y in zip(a, b)) / n
    ca, cb = Counter(a), Counter(b)
    pe = sum(ca[k] * cb[k] for k in set(ca) | set(cb)) / (n * n)
    if math.isclose(pe, 1.0):
        return None
    return (po - pe) / (1 - pe)


def wilson_ci(successes: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (0.0, 1.0)
    p = successes / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


def bootstrap_kappa_ci(a: list[str], b: list[str], *, reps: int, rng: random.Random) -> tuple[float, float] | None:
    n = len(a)
    values: list[float] = []
    for _ in range(reps):
        idx = [rng.randrange(n) for _ in range(n)]
        k = cohen_kappa([a[i] for i in idx], [b[i] for i in idx])
        if k is not None:
            values.append(k)
    if len(values) < reps * 0.5:
        return None
    values.sort()
    return (values[int(0.025 * (len(values) - 1))], values[int(math.ceil(0.975 * (len(values) - 1)))])


def variable_stats(variable: Variable, a: list[str], b: list[str], *, reps: int, seed: int) -> VarStats:
    n = len(a)
    if n == 0:
        return VarStats(variable, 0, None, None, None, None, "not_evaluable")
    matches = sum(x == y for x, y in zip(a, b))
    agreement = matches / n
    kappa = cohen_kappa(a, b)
    ci = bootstrap_kappa_ci(a, b, reps=reps, rng=random.Random(f"{seed}:{variable.name}")) if kappa is not None else None
    if kappa is None:
        verdict = "pass_kappa_undefined" if agreement == 1.0 else "fail_kappa_undefined"
    else:
        verdict = "pass" if kappa >= KAPPA_THRESHOLD and agreement >= AGREEMENT_THRESHOLD else "fail"
    return VarStats(variable, n, agreement, wilson_ci(matches, n), kappa, ci, verdict)


def compare_tables(
    table_a: dict[str, dict[str, str]],
    table_b: dict[str, dict[str, str]],
    *,
    articles: set[str] | None = None,
    reps: int = 1000,
    seed: int = 20260101,
) -> tuple[list[VarStats], list[dict[str, object]], list[str]]:
    ids = sorted(set(table_a) & set(table_b) & (articles if articles is not None else set(table_a)))
    stats: list[VarStats] = []
    for var in build_variables():
        pairs = [
            (table_a[i].get(var.name, ""), table_b[i].get(var.name, ""))
            for i in ids
            if table_a[i].get(var.name, "") != "" and table_b[i].get(var.name, "") != ""
        ]
        stats.append(variable_stats(var, [p[0] for p in pairs], [p[1] for p in pairs], reps=reps, seed=seed))
    return stats, domain_rows(stats), ids


def domain_rows(stats: list[VarStats]) -> list[dict[str, object]]:
    by_theme: dict[str, list[VarStats]] = defaultdict(list)
    for s in stats:
        by_theme[s.variable.theme].append(s)
    rows = []
    for theme, items in by_theme.items():
        evaluable = [s for s in items if s.n > 0]
        passing = [s for s in evaluable if s.verdict.startswith("pass")]
        pooled_n = sum(s.n for s in evaluable)
        pooled_match = sum(round(s.agreement * s.n) for s in evaluable)
        rows.append(
            {
                "domain": theme,
                "variables": len(items),
                "evaluable_variables": len(evaluable),
                "variables_passing": len(passing),
                "share_passing": round(len(passing) / len(evaluable), 3) if evaluable else "",
                "pooled_exact_agreement": round(pooled_match / pooled_n, 4) if pooled_n else "",
                "domain_suitable_for_autonomous_extraction": bool(evaluable) and len(passing) == len(evaluable),
            }
        )
    return rows


def _fmt(x: float | None) -> object:
    return "" if x is None else round(x, 4)


def stat_rows(stats: list[VarStats]) -> list[dict[str, object]]:
    return [
        {
            "variable": s.variable.name,
            "item_id": s.variable.item_id,
            "domain": s.variable.theme,
            "type": "binary" if s.variable.binary else "categorical",
            "n_articles": s.n,
            "exact_agreement": _fmt(s.agreement),
            "agreement_ci95_low": _fmt(s.agreement_ci[0]) if s.agreement_ci else "",
            "agreement_ci95_high": _fmt(s.agreement_ci[1]) if s.agreement_ci else "",
            "kappa": _fmt(s.kappa),
            "kappa_ci95_low": _fmt(s.kappa_ci[0]) if s.kappa_ci else "",
            "kappa_ci95_high": _fmt(s.kappa_ci[1]) if s.kappa_ci else "",
            "verdict": s.verdict,
        }
        for s in stats
    ]


def write_report(out_dir: Path, stats: list[VarStats], domains: list[dict[str, object]], meta: dict[str, object]) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    rows = stat_rows(stats)
    for name, data in (("agreement_variables.csv", rows), ("agreement_domains.csv", domains)):
        with (out_dir / name).open("w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(data[0].keys()))
            writer.writeheader()
            writer.writerows(data)
    (out_dir / "agreement_meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    try:
        from openpyxl import Workbook
    except ImportError:
        return
    workbook = Workbook()
    workbook.remove(workbook.active)
    for title, data in (("Domains", domains), ("Variables", rows)):
        sheet = workbook.create_sheet(title)
        sheet.append(list(data[0].keys()))
        for row in data:
            sheet.append(list(row.values()))
    workbook.save(out_dir / "agreement.xlsx")


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description="Agreement (exact % + Cohen kappa, 95% CI) between two wide extraction tables.")
    parser.add_argument("--a", type=Path, required=True, help="Reference table (human consensus, or human rater 1). CSV/XLSX, see review-binary.")
    parser.add_argument("--b", type=Path, required=True, help="Compared table (Claude binary.csv, or human rater 2).")
    parser.add_argument("--label", default="claude_vs_human", help="Free label stored in the report (e.g. human_vs_human).")
    parser.add_argument("--out", type=Path, default=Path("agreement"), help="Report folder.")
    parser.add_argument("--sample", type=Path, default=None, help="validation_sample.csv from review-sample.")
    parser.add_argument("--subset", choices=["development", "tuning", "test"], default=None, help="Restrict to a subset of --sample.")
    parser.add_argument("--final-evaluation", action="store_true", help="Required for --subset test; allowed once (lock file).")
    parser.add_argument("--force", action="store_true", help="Override the one-time test lock (recorded as a protocol deviation).")
    parser.add_argument("--reps", type=int, default=1000, help="Bootstrap replicates for the kappa CI.")
    parser.add_argument("--seed", type=int, default=20260101)
    args = parser.parse_args()

    articles = None
    if args.subset:
        if not args.sample:
            sys.exit("--subset needs --sample.")
        with args.sample.open(newline="", encoding="utf-8-sig") as handle:
            articles = {r["article_id"] for r in csv.DictReader(handle) if r["subset"] == args.subset}
    lock = args.out / "final_test_evaluation.lock.json"
    already_done = lock.exists()
    if args.subset == "test":
        if not args.final_evaluation:
            sys.exit("The held-out test set is evaluated once, after the prompt is frozen: add --final-evaluation.")
        if already_done and not args.force:
            sys.exit(f"Final test evaluation already done ({lock}). Protocol: evaluate once. --force records a deviation.")

    stats, domains, ids = compare_tables(
        read_wide_table(args.a), read_wide_table(args.b), articles=articles, reps=args.reps, seed=args.seed
    )
    meta = {
        "label": args.label,
        "subset": args.subset,
        "created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "n_articles_compared": len(ids),
        "thresholds": {"kappa": KAPPA_THRESHOLD, "exact_agreement": AGREEMENT_THRESHOLD},
        "kappa_ci": f"percentile bootstrap over articles, {args.reps} replicates, seed {args.seed}",
        "table_a_sha256": _sha(args.a),
        "table_b_sha256": _sha(args.b),
        "forced_rerun_protocol_deviation": bool(args.subset == "test" and already_done),
    }
    write_report(args.out, stats, domains, meta)
    if args.subset == "test":
        lock.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(f"{len(ids)} article(s) compared -> {args.out}")
    for row in domains:
        print(
            f"  {row['domain']:<28} passing {row['variables_passing']}/{row['evaluable_variables']}  "
            f"pooled agreement {row['pooled_exact_agreement']}  suitable={row['domain_suitable_for_autonomous_extraction']}"
        )


if __name__ == "__main__":
    main()
