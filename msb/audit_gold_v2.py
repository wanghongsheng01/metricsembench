"""Mechanical gold audit for p15_heldout_v2 (re-execution + handbook structure + overlap).

Same audit as msb.audit_gold, applied to the second Paper-15 held-out. Changes no gold.
"""
from __future__ import annotations

import json
from pathlib import Path

import duckdb

from msb.audit_gold import audit_fold
from msb.config import DB_PATH, RESULTS_DIR, TASKS_DIR

V2 = TASKS_DIR / "msb_p15_heldout_v2_tasks.json"
FREEZE = "abe30e25701882ef9ad3b9a53fefbe641b8c7aa2b0932b0cf8dab11d68c4db97"


def main() -> int:
    con = duckdb.connect(str(DB_PATH), read_only=True)
    raw = json.loads(V2.read_text())
    r = audit_fold(V2, con, expect_evaluated=raw.get("evaluated"), freeze_sha_expected=FREEZE)
    t2 = raw["tasks"]
    ov = {}
    for name in ("msb_v0.1_tasks.json", "msb_p15_heldout_v1_tasks.json"):
        t1 = json.loads((TASKS_DIR / name).read_text())["tasks"]
        ov[name] = {
            "id_overlap": sorted({t["id"] for t in t1} & {t["id"] for t in t2}),
            "question_overlap": sorted({t["question_en"].strip() for t in t1} & {t["question_en"].strip() for t in t2}),
        }
    out = {"p15_heldout_v2": r, "overlap": ov, "note": "Mechanical verification; not a dual-human kappa."}
    dest = RESULTS_DIR / "paper15_official" / "gold_audit_v2.json"
    dest.write_text(json.dumps(out, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print("n", r["n"], "issues", r["issues"][:8], "freeze", r["freeze_sha"][:16])
    print("ok", {k: v for k, v in r["ok"].items() if k != "handbook_struct_fail"})
    print("handbook fail", r["ok"]["handbook_struct_fail"][:8])
    print("overlap", {k: (len(v["id_overlap"]), len(v["question_overlap"])) for k, v in ov.items()})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
