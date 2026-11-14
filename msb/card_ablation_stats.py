"""Summarize the DEV card-sensitivity run (msb.run_card_ablation) against the frozen-card v0.1 rows.

Paired over the same 85 v0.1 items: TA difference (native-measure card minus frozen card),
percentile paired bootstrap (10,000, seed 20261112). Also counts compute SQL that use
net_paid_usd and unnecessary clarifies on gold-compute items whose axes mention currency.
"""
from __future__ import annotations

import json

from msb.config import RESULTS_DIR
from msb.frontier_stats import SYSTEMS, jsonl
from msb.paper15_stats import N_BOOT, SEED, summarize_v01
from msb.public_stats import paired_bootstrap_diff


def fx_ucr(rows):
    n = 0
    for r in rows:
        if r.get("gold_behavior") == "compute" and r.get("unnecessary_clarify"):
            ax = " ".join(map(str, r.get("clarify_axes") or [])) + " " + str(r.get("brief") or "")
            if any(w in ax.lower() for w in ("currenc", "usd", "fx")):
                n += 1
    return n


def usd_sql(rows):
    return sum(1 for r in rows if r.get("gold_behavior") == "compute" and r.get("pred_behavior") == "compute" and "net_paid_usd" in str(r.get("pred_sql") or ""))


def main() -> int:
    out = {"fold": "v0.1 (DEV)", "role": "DEV sensitivity analysis; official folds and frozen card unchanged",
           "bootstrap": {"n": N_BOOT, "seed": SEED}, "systems": {}}
    for s in SYSTEMS:
        p = RESULTS_DIR / "frontier" / "card_native" / f"v0.1__{s}.jsonl"
        if not p.exists():
            continue
        new = jsonl(p)
        old = {r["id"]: r for r in jsonl(RESULTS_DIR / "frontier" / f"v0.1__{s}.jsonl")}
        if len(new) != 85:
            out["systems"][s] = {"incomplete": len(new)}
            continue
        a = [1.0 if r.get("TA") else 0.0 for r in new]
        b = [1.0 if old[r["id"]].get("TA") else 0.0 for r in new]
        out["systems"][s] = {
            "summary": summarize_v01(new),
            "vs_frozen": paired_bootstrap_diff(a, b, n_boot=N_BOOT, seed=SEED),
            "usd_sql": usd_sql(new), "usd_sql_frozen": usd_sql(old.values()),
            "fx_ucr": fx_ucr(new), "fx_ucr_frozen": fx_ucr(old.values()),
            "spend": round(sum(float(r.get("cost_usd") or 0) for r in new), 4),
        }
    dest = RESULTS_DIR / "paper15_official" / "card_native_v01.json"
    dest.write_text(json.dumps(out, indent=2, default=str))
    for k, v in out["systems"].items():
        if "summary" in v:
            print(k, "TA", round(v["summary"]["TA"]["mean"], 3), "dTA", round(v["vs_frozen"]["diff"], 3), [round(v["vs_frozen"]["ci_low"], 3), round(v["vs_frozen"]["ci_high"], 3)],
                  "usd", v["usd_sql"], "/", v["usd_sql_frozen"], "fxUCR", v["fx_ucr"], "/", v["fx_ucr_frozen"], "$", v["spend"])
        else:
            print(k, v)
    # post-hoc sensitivity on the already-evaluated official v2 (official v2 rows untouched)
    out2 = {"fold": "p15_heldout_v2 (post-hoc sensitivity after the official one-shot evaluation)",
            "role": "secondary analysis; official v2 scores use the frozen card",
            "bootstrap": {"n": N_BOOT, "seed": SEED}, "systems": {}}
    for s in SYSTEMS:
        p = RESULTS_DIR / "frontier" / "card_native" / f"p15_heldout_v2__{s}.jsonl"
        if not p.exists():
            continue
        new = jsonl(p)
        old = {r["id"]: r for r in jsonl(RESULTS_DIR / "paper15_official" / "v2" / f"p15_heldout_v2__{s}.jsonl")}
        if len(new) != 250:
            out2["systems"][s] = {"incomplete": len(new)}
            continue
        a = [1.0 if r.get("TA") else 0.0 for r in new]
        b = [1.0 if old[r["id"]].get("TA") else 0.0 for r in new]
        out2["systems"][s] = {
            "summary": summarize_v01(new),
            "vs_frozen": paired_bootstrap_diff(a, b, n_boot=N_BOOT, seed=SEED),
            "usd_sql": usd_sql(new), "usd_sql_frozen": usd_sql(old.values()),
            "fx_ucr": fx_ucr(new), "fx_ucr_frozen": fx_ucr(old.values()),
            "spend": round(sum(float(r.get("cost_usd") or 0) for r in new), 4),
        }
    if out2["systems"]:
        (RESULTS_DIR / "paper15_official" / "card_native_v2.json").write_text(json.dumps(out2, indent=2, default=str))
        for k, v in out2["systems"].items():
            if "summary" in v:
                print("v2", k, "TA", round(v["summary"]["TA"]["mean"], 3), "dTA", round(v["vs_frozen"]["diff"], 3), [round(v["vs_frozen"]["ci_low"], 3), round(v["vs_frozen"]["ci_high"], 3)],
                      "usd", v["usd_sql"], "/", v["usd_sql_frozen"], "fxUCR", v["fx_ucr"], "/", v["fx_ucr_frozen"], "$", v["spend"])
            else:
                print("v2", k, v)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
