"""Recompute the frontier CI files (v0.1 DEV and p15_heldout_v1) from stored JSONL.

Writes results/paper15_official/{msb_v0.1_frontier_ci.json, msb_p15_heldout_v1_frontier_ci.json}
(or, with --check, compares against the stored files and exits non-zero on a mismatch).
No model is re-queried.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from msb.config import RESULTS_DIR
from msb.paper15_stats import N_BOOT, SEED, contrast_v01, merge_v01, summarize_v01

FR = RESULTS_DIR / "frontier"
OUT = RESULTS_DIR / "paper15_official"
SYSTEMS = ("tokens1688_2_claude-opus-5_semantic_max", "tokens1688_2_claude-opus-5-5_semantic_high",
           "tokens1688_2_gpt-6-luna_semantic")
V1_SHA = "03d26b59479d82ee7d6e71bb73f6bedc4db42204cf8c9d9124604adb53e55cb2"


def jsonl(p: Path) -> list[dict]:
    rows: dict[str, dict] = {}
    for line in p.read_text(encoding="utf-8").splitlines():
        if line.strip():
            r = json.loads(line)
            if r.get("id") and not r.get("error"):
                rows[r["id"]] = r
    return list(rows.values())


def build(fold: str) -> dict:
    if fold == "v0.1":
        per = {s: jsonl(FR / f"v0.1__{s}.jsonl") for s in SYSTEMS}
        base = merge_v01()
        det = {"naive_surface": base["naive_surface"]}
        head = {"fold": "v0.1", "n": 85}
        note = "Frontier v0.1 complete. Merged from jsonl after parallel runs. Not a held-out result."
    else:
        per = {s: jsonl(FR / f"p15_heldout_v1__{s}.jsonl") for s in SYSTEMS}
        d = json.loads((OUT / "msb_p15_heldout_v1_deterministic.json").read_text())
        det = {k: d["per_task"][k] for k in ("naive_surface", "dict_default", "always_refuse", "always_clarify")}
        head = {"fold": "p15_heldout_v1", "sha256": V1_SHA, "n": 94, "evaluated_at_scoring": False}
        note = "Official one-shot frontier on frozen held-out. Merged from jsonl. Paper-13 folds not used."
    naive = det["naive_surface"]
    out = dict(head)
    out.update({"seed": SEED, "n_boot": N_BOOT,
                "spent_usd": {s: round(sum(float(r.get("cost_usd") or 0) for r in per[s]), 7) for s in SYSTEMS},
                "summaries": {**{s: summarize_v01(per[s]) for s in SYSTEMS}, **{k: summarize_v01(v) for k, v in det.items()}},
                "paired_vs_naive": {s: contrast_v01(per[s], naive, "TA") for s in SYSTEMS},
                "note": note})
    return out


def _close(a, b, path="") -> list[str]:
    if isinstance(a, dict) and isinstance(b, dict):
        diffs = []
        for k in set(a) | set(b):
            if k in ("lower_better",):
                continue
            if k not in a or k not in b:
                diffs.append(f"{path}/{k}: missing")
            else:
                diffs += _close(a[k], b[k], f"{path}/{k}")
        return diffs
    if isinstance(a, (int, float)) and isinstance(b, (int, float)) and not isinstance(a, bool):
        return [] if abs(a - b) <= 1e-6 * max(1.0, abs(b)) else [f"{path}: {a} != {b}"]
    return [] if a == b else [f"{path}: {a!r} != {b!r}"]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    bad = 0
    for fold, name in (("v0.1", "msb_v0.1_frontier_ci.json"), ("heldout", "msb_p15_heldout_v1_frontier_ci.json")):
        new = build(fold)
        if a.check:
            old = json.loads((OUT / name).read_text())
            keys = ("summaries", "paired_vs_naive", "spent_usd")
            diffs = [d for k in keys for d in _close(new[k], old[k], k)]
            print(name, "OK" if not diffs else f"{len(diffs)} DIFFS", diffs[:5])
            bad += bool(diffs)
        else:
            (OUT / name).write_text(json.dumps(new, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
            print("wrote", name)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
