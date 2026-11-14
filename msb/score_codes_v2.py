"""Score the pre-registered CodeS-7B-Spider row on p15_heldout_v2 (first executable beam wins).

Pre-registered in PREREG_P15_HELDOUT_V2.md: run only after the DEV (v0.1) CodeS profile was
complete; same checkpoint, prompt builder, beams and scorer as DEV. Writes the per-item rows
as results/paper15_official/v2/p15_heldout_v2__codes-7b-spider.jsonl (picked up by
msb.paper15_v2_stats) and a summary JSON.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from msb.config import DB_PATH, RESULTS_DIR, TASKS_DIR
from msb.evaluate import score_one
from msb.forbidden_folds import assert_allowed_task_path
from msb.paper15_v2_stats import EXPECTED_SHA, freeze_sha
from msb.score_codes import first_executable


def main() -> int:
    task_path = TASKS_DIR / "msb_p15_heldout_v2_tasks.json"
    assert_allowed_task_path(task_path)
    raw = json.loads(task_path.read_text())
    assert freeze_sha(raw) == EXPECTED_SHA
    by = {t["id"]: t for t in raw["tasks"]}
    pred_path = Path(sys.argv[1]) if len(sys.argv) > 1 else RESULTS_DIR / "codes" / "p15_heldout_v2_codes_beams.jsonl"
    rows_in = [json.loads(l) for l in pred_path.read_text().splitlines() if l.strip()]
    seen, scored = set(), []
    for r in rows_in:
        if r.get("error") or r["id"] not in by or r["id"] in seen:
            continue
        seen.add(r["id"])
        sql, val, note = first_executable(r.get("sqls"), DB_PATH)
        s = score_one(by[r["id"]], {"behavior": "compute", "sql": sql, "value": val, "error": note})
        s.update({"baseline": "codes-7b-spider", "pred_sql": sql, "beam_sqls": r.get("sqls"),
                  "elapsed_s": r.get("elapsed_s"), "cost_usd": 0.0, "error": None})
        scored.append(s)
    out = RESULTS_DIR / "paper15_official" / "v2" / "p15_heldout_v2__codes-7b-spider.jsonl"
    out.write_text("".join(json.dumps(s, ensure_ascii=False, default=str) + "\n" for s in scored), encoding="utf-8")
    print("wrote", out, "n", len(scored), "/", len(by), "non-null", sum(1 for s in scored if s.get("pred_value") is not None))
    return 0 if len(scored) == len(by) else 2


if __name__ == "__main__":
    raise SystemExit(main())
