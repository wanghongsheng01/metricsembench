"""Gold-blind deterministic baselines on Paper 15's official held-out.

Run only AFTER the freeze commit (evaluated=false is already in the task file).
Does not load paper-13 folds. Does not call paid LLMs.
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

from msb.baselines import BASELINES
from msb.config import RESULTS_DIR, TASKS_DIR
from msb.evaluate import _agg, blind_view, score_one
from msb.forbidden_folds import assert_allowed_task_path
from msb.paper15_stats import summarize_v01, contrast_v01, write_v01_tables
from msb.public_stats import fmt_ci

EXPECTED_SHA = "03d26b59479d82ee7d6e71bb73f6bedc4db42204cf8c9d9124604adb53e55cb2"
TASK = TASKS_DIR / "msb_p15_heldout_v1_tasks.json"
OUT = RESULTS_DIR / "paper15_official" / "msb_p15_heldout_v1_deterministic.json"
OUT_MD = RESULTS_DIR / "paper15_official" / "msb_p15_heldout_v1_deterministic.md"


def main():
    assert_allowed_task_path(TASK)
    payload = json.loads(TASK.read_text(encoding="utf-8"))
    if payload.get("sha256") != EXPECTED_SHA:
        raise SystemExit(f"sha mismatch {payload.get('sha256')}")
    tasks = payload["tasks"]
    per = {}
    point = {}
    for name, cls in BASELINES.items():
        sys = cls()
        rows = []
        for t in tasks:
            pred = sys.answer(blind_view(t))
            s = score_one(t, pred)
            s["baseline"] = name
            rows.append(s)
        per[name] = rows
        point[name] = _agg(rows)
        print(name, point[name])
    summaries = {n: summarize_v01(rows) for n, rows in per.items()}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        json.dumps(
            {
                "fold": "p15_heldout_v1",
                "sha256": EXPECTED_SHA,
                "n": len(tasks),
                "counts": payload.get("counts"),
                "summary_point": point,
                "summary_ci": summaries,
                "per_task": per,
                "note": "Deterministic gold-blind baselines. First scores on this fold. LLM frontier is a separate run.",
            },
            indent=2,
            ensure_ascii=False,
            default=str,
        ),
        encoding="utf-8",
    )
    from msb.public_stats import fmt_ci as F
    lines = [
        "# Paper 15 official held-out v1 — deterministic baselines (first scores)",
        "",
        f"SHA-256 `{EXPECTED_SHA}`, n={len(tasks)} "
        f"(compute {payload['counts'].get('behavior:compute')} / "
        f"clarify {payload['counts'].get('behavior:clarify')} / "
        f"refuse {payload['counts'].get('behavior:refuse')}).",
        "Bootstrap 95% CIs, 10,000 resamples, seed 20261112.",
        "These are the first scores on this fold. Frozen with evaluated=false before this run.",
        "Paper-13 official TEST folds were not used. No paid LLM in this file.",
        "",
        "| System | n | TA | Compute Acc | FAR | CRR | Missed clarify | UCR | DSR | Illegal YoY | Illegal Agg |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    keys = [
        "TA", "compute_accuracy", "FAR_on_clarify_or_refuse", "CRR",
        "missed_clarify", "unnecessary_clarify", "DSR", "IllegalYoY", "IllegalAgg",
    ]
    for n, s in summaries.items():
        cells = " | ".join(F(s[k]) for k in keys)
        lines.append(f"| {n} | {s['n']} | {cells} |")
    # inversion
    lines += [
        "",
        "## EX vs TA on this held-out (deterministic systems)",
        "",
        "If GATE-INSIGHT-INVERT holds, naive_surface should again sit at or near the EX ceiling",
        "while official TA is pulled down by FAR on clarify∪refuse.",
        "",
    ]
    if "naive_surface" in summaries:
        ns = summaries["naive_surface"]
        lines.append(
            f"naive_surface: Compute Acc {F(ns['compute_accuracy'])}, "
            f"TA {F(ns['TA'])}, FAR {F(ns['FAR_on_clarify_or_refuse'])}."
        )
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("wrote", OUT, OUT_MD)


if __name__ == "__main__":
    main()
