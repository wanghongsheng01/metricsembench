"""Mix-robustness analysis of official TA (class-balanced TA and compute-share crossover).

Computed only from stored per-item predictions; no model is re-queried and no gold changes.
On v0.1 and p15_heldout_v1 this is a post-hoc analysis; on p15_heldout_v2 it is
pre-registered (PREREG_P15_HELDOUT_V2.md).

balanced TA  = mean over gold behaviors b in {compute, clarify, refuse} of TA on items with gold b.
TA_s(w)      = w * A_compute + (1 - w) * A_cr, where A_cr = TA on clarify U refuse items
               (clarify:refuse ratio of the fold held fixed); naive has A_compute=1, A_cr=0, so
               TA_naive(w) = w.  Crossover w* = A_cr / (1 - A_compute + A_cr): system s beats naive
               in expectation iff the gold-compute share is below w*.
Bootstrap: stratified by gold behavior, 10,000 resamples, seed 20261112 (percentile 95%).
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from msb.config import RESULTS_DIR
from msb.paper15_stats import merge_v01

SEED, NB = 20261112, 10000
BEH = ("compute", "clarify", "refuse")


def _jsonl(p: Path):
    rows = {}
    for l in p.read_text(encoding="utf-8").splitlines():
        if l.strip():
            r = json.loads(l)
            if r.get("id") and not r.get("error"):
                rows[r["id"]] = r
    return list(rows.values())


def load_fold(fold: str) -> dict[str, list[dict]]:
    per: dict[str, list[dict]] = {}
    if fold == "v0.1":
        per.update(merge_v01())
        fr = json.loads((RESULTS_DIR / "frontier" / "frontier_v0.1.json").read_text())
        for k, v in fr["systems"].items():
            per[k] = v["per_task"]
    elif fold == "v1":
        d = json.loads((RESULTS_DIR / "paper15_official" / "msb_p15_heldout_v1_deterministic.json").read_text())
        per.update(d["per_task"])
        for p in sorted((RESULTS_DIR / "frontier").glob("p15_heldout_v1__*.jsonl")):
            per[p.name.split("__", 1)[1][:-6]] = _jsonl(p)
    elif fold == "v2":
        for p in sorted((RESULTS_DIR / "paper15_official" / "v2").glob("p15_heldout_v2__*.jsonl")):
            per[p.name.split("__", 1)[1][:-6]] = _jsonl(p)
    return per


def _ta(r) -> float:
    return 1.0 if int(r.get("TA") or 0) else 0.0


def stats(rows: list[dict], naive: list[dict]):
    nmap = {r["id"]: r for r in naive}
    rows = [r for r in rows if r["id"] in nmap]
    groups = {b: [r for r in rows if r["gold_behavior"] == b] for b in BEH}
    groups = {b: g for b, g in groups.items() if g}
    acc = {b: np.array([_ta(r) for r in g]) for b, g in groups.items()}
    nacc = {b: np.array([_ta(nmap[r["id"]]) for r in g]) for b, g in groups.items()}
    cr_s = np.concatenate([acc[b] for b in acc if b != "compute"])
    cr_n = np.concatenate([nacc[b] for b in nacc if b != "compute"])

    def point(a, n):
        bal = float(np.mean([a[b].mean() for b in a]))
        nbal = float(np.mean([n[b].mean() for b in n]))
        ac = a["compute"].mean()
        acr = np.concatenate([a[b] for b in a if b != "compute"]).mean()
        w = acr / (1 - ac + acr) if (1 - ac + acr) > 0 else float("nan")
        return bal, bal - nbal, w

    bal, dbal, w = point(acc, nacc)
    rng = np.random.default_rng(SEED)
    B = np.empty((NB, 3))
    for i in range(NB):
        ia, ina = {}, {}
        for b in acc:
            idx = rng.integers(0, len(acc[b]), len(acc[b]))
            ia[b], ina[b] = acc[b][idx], nacc[b][idx]
        B[i] = point(ia, ina)
    q = lambda j: [float(np.nanquantile(B[:, j], 0.025)), float(np.nanquantile(B[:, j], 0.975))]
    p = float(min(1.0, 2 * min((B[:, 1] <= 0).mean(), (B[:, 1] >= 0).mean())))
    return {
        "n": len(rows), "acc_compute": float(acc["compute"].mean()), "acc_cr": float(cr_s.mean()),
        **{f"acc_{b}": float(acc[b].mean()) for b in acc},
        "balanced_TA": bal, "balanced_TA_ci": q(0),
        "delta_balanced_vs_naive": dbal, "delta_ci": q(1), "p_boot": p,
        "w_star": w, "w_star_ci": q(2),
        "fold_compute_share": len(groups["compute"]) / len(rows),
    }


def holm(ps: dict[str, float]) -> dict[str, float]:
    items = sorted(ps.items(), key=lambda kv: kv[1])
    m, out, run = len(items), {}, 0.0
    for i, (k, p) in enumerate(items):
        run = max(run, min(1.0, (m - i) * p))
        out[k] = run
    return out


def main():
    out = {}
    for fold in ("v0.1", "v1", "v2"):
        per = load_fold(fold)
        if not per or "naive_surface" not in per:
            continue
        naive = per["naive_surface"]
        res = {k: stats(v, naive) for k, v in per.items() if v and len(v) == len(naive)}
        ps = {k: r["p_boot"] for k, r in res.items() if k != "naive_surface"}
        for k, ph in holm(ps).items():
            res[k]["p_holm"] = ph
        out[fold] = res
        print(f"== {fold} (n={len(naive)})")
        for k, r in sorted(res.items(), key=lambda kv: -kv[1]["balanced_TA"]):
            print(f"  {k:48s} bal={100*r['balanced_TA']:5.1f} [{100*r['balanced_TA_ci'][0]:.1f},{100*r['balanced_TA_ci'][1]:.1f}] "
                  f"d={100*r['delta_balanced_vs_naive']:+5.1f} [{100*r['delta_ci'][0]:+.1f},{100*r['delta_ci'][1]:+.1f}] p={r['p_boot']:.4f} "
                  f"holm={r.get('p_holm', float('nan')):.4f} w*={r['w_star']:.3f} [{r['w_star_ci'][0]:.3f},{r['w_star_ci'][1]:.3f}] "
                  f"Ac={100*r['acc_compute']:.1f} Acr={100*r['acc_cr']:.1f}")
    dst = RESULTS_DIR / "paper15_official" / "mix_robustness.json"
    dst.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print("wrote", dst)


if __name__ == "__main__":
    main()
