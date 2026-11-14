"""Official statistics for the second Paper-15 held-out p15_heldout_v2 (n=250).

Pre-registered in PREREG_P15_HELDOUT_V2.md before any v2 score. Reads only the
stored one-shot per-item JSONL predictions; no model is re-queried, no gold is
changed. Same estimators as paper15_stats (percentile bootstrap 95% CI,
10,000 resamples, seed 20261112; paired bootstrap on per-item TA difference;
McNemar mid-p; W/T/L vs naive). Holm correction over the pre-registered
non-deterministic contrasts vs naive. Kendall tau between Compute-Acc (EX-like)
ranks and official-TA ranks.

Refuses to report a system with fewer than n rows (incomplete run).
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from msb.config import RESULTS_DIR, TASKS_DIR
from msb.forbidden_folds import assert_allowed_task_path
from msb.paper15_stats import (
    N_BOOT, SEED, V01_METRICS, contrast_v01, kendall_tau, _rank, summarize_v01,
)

TASK = TASKS_DIR / "msb_p15_heldout_v2_tasks.json"
V2_DIR = RESULTS_DIR / "paper15_official" / "v2"
OUT = RESULTS_DIR / "paper15_official" / "msb_p15_heldout_v2_ci.json"
OUT_MD = RESULTS_DIR / "paper15_official" / "msb_p15_heldout_v2_ci.md"
EXPECTED_SHA = "abe30e25701882ef9ad3b9a53fefbe641b8c7aa2b0932b0cf8dab11d68c4db97"
DETERMINISTIC = ("naive_surface", "dict_default", "always_clarify", "always_refuse")


def freeze_sha(d: dict) -> str:
    p = {k: v for k, v in d.items() if k != "sha256"}
    p["evaluated"] = False
    s = json.dumps(p, indent=2, sort_keys=True, ensure_ascii=False, default=str) + "\n"
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def _jsonl(p: Path) -> list[dict]:
    rows = {}
    for line in p.read_text(encoding="utf-8").splitlines():
        if line.strip():
            r = json.loads(line)
            if r.get("id") and not r.get("error"):
                rows[r["id"]] = r
    return list(rows.values())


def holm(ps: dict[str, float]) -> dict[str, float]:
    items = sorted(ps.items(), key=lambda kv: kv[1])
    m, out, run = len(items), {}, 0.0
    for i, (k, p) in enumerate(items):
        run = max(run, min(1.0, (m - i) * p))
        out[k] = run
    return out


def main() -> int:
    assert_allowed_task_path(TASK)
    d = json.loads(TASK.read_text())
    assert freeze_sha(d) == EXPECTED_SHA == d["sha256"], "freeze SHA mismatch"
    ids = {t["id"] for t in d["tasks"]}
    n = len(ids)
    per, incomplete = {}, {}
    for p in sorted(V2_DIR.glob("p15_heldout_v2__*.jsonl")):
        name = p.name.split("__", 1)[1][:-6]
        rows = [r for r in _jsonl(p) if r["id"] in ids]
        if len(rows) == n:
            per[name] = rows
        else:
            incomplete[name] = len(rows)
    naive = per["naive_surface"]
    summaries = {k: summarize_v01(v) for k, v in per.items()}
    contrasts, ps = {}, {}
    for k, rows in per.items():
        if k == "naive_surface":
            continue
        c = contrast_v01(rows, naive, "TA")
        nmap = {r["id"]: r for r in naive}
        w = sum(1 for r in rows if r.get("TA") and not nmap[r["id"]].get("TA"))
        l = sum(1 for r in rows if not r.get("TA") and nmap[r["id"]].get("TA"))
        c["WTL"] = f"{w}/{n - w - l}/{l}"
        contrasts[k] = c
        if k not in DETERMINISTIC:
            ps[k] = float(c["bootstrap"].get("p_boot", c["bootstrap"].get("p", 1.0)))
    hp = holm(ps)
    for k, v in hp.items():
        contrasts[k]["holm_p_boot"] = v
    ex = _rank([(k, s["compute_accuracy"]["mean"]) for k, s in summaries.items()], higher=True)
    ta = _rank([(k, s["TA"]["mean"]) for k, s in summaries.items()], higher=True)
    names = sorted(summaries)
    tau = kendall_tau([ex[k] for k in names], [ta[k] for k in names])
    spend = {}
    for k, rows in per.items():
        spend[k] = round(sum(float(r.get("cost_usd") or 0) for r in rows), 4)
    out = {
        "fold": "p15_heldout_v2", "freeze_sha256": EXPECTED_SHA, "n": n,
        "counts": {b: sum(1 for t in d["tasks"] if t["gold_behavior"] == b) for b in ("compute", "clarify", "refuse")},
        "bootstrap": {"n": N_BOOT, "seed": SEED}, "metrics": V01_METRICS,
        "summaries": summaries, "contrasts_vs_naive_TA": contrasts,
        "ranks": {"compute_accuracy": ex, "TA": ta}, "kendall_tau_ex_ta": tau,
        "spend_usd_recorded": spend, "incomplete_not_reported": incomplete,
        "per_task": per,
    }
    OUT.write_text(json.dumps(out, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    lines = [f"# p15_heldout_v2 official profile (n={n}, freeze {EXPECTED_SHA[:8]})", "",
             "| System | TA | CompAcc | FAR | CRR | Missed | UCR | DSR | dTA vs naive [CI] p (Holm) | W/T/L | $ |", "|---|---|---|---|---|---|---|---|---|---|---|"]
    def f(ci):
        return "-" if not ci or ci.get("mean") is None else f"{100*ci['mean']:.1f} [{100*ci['ci_low']:.1f}, {100*ci['ci_high']:.1f}]"
    for k in sorted(summaries, key=lambda k: -summaries[k]["TA"]["mean"]):
        s = summaries[k]
        c = contrasts.get(k)
        cs = "-"
        if c:
            b = c["bootstrap"]
            cs = f"{100*b['diff']:+.1f} [{100*b['ci_low']:+.1f}, {100*b['ci_high']:+.1f}] p={b.get('p_boot', b.get('p'))}" + (f" (Holm {c['holm_p_boot']:.4f})" if "holm_p_boot" in c else "")
        lines.append(f"| {k} | {f(s['TA'])} | {f(s['compute_accuracy'])} | {f(s['FAR_on_clarify_or_refuse'])} | {f(s['CRR'])} | {f(s['missed_clarify'])} | {f(s['unnecessary_clarify'])} | {f(s['DSR'])} | {cs} | {c['WTL'] if c else '-'} | {spend[k]} |")
    lines += ["", f"Kendall tau (CompAcc rank vs TA rank, {len(names)} systems): {tau:.3f}", f"Incomplete (not reported): {incomplete}"]
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
