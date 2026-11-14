"""Score CodeS DEV (v0.1) beams: first executable SQL wins; always-answer.

DEV only. Does not load paper-13 folds or the official held-out. Produces CIs
with seed 20261112, 10k resamples, paired tests vs naive, W/T/L. Clearly
labeled DEV profile — not an official held-out row.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from msb.baselines.llm_published import exec_scalar
from msb.config import DB_PATH, RESULTS_DIR, TASKS_DIR
from msb.evaluate import _agg, score_one
from msb.forbidden_folds import assert_allowed_task_path
from msb.paper15_stats import contrast_v01, merge_v01, summarize_v01


def first_executable(sqls, db) -> tuple[str | None, object | None, str | None]:
    for sql in sqls or []:
        if not sql or not str(sql).strip():
            continue
        val = exec_scalar(sql, db, timeout_s=12)
        if val is not None:
            return sql, val, None
    for sql in sqls or []:
        if sql and str(sql).strip():
            return sql, None, "not_executable"
    return None, None, "empty"


def wtl(ours: list[dict], naive: list[dict], metric: str = "TA") -> dict:
    bmap = {r["id"]: r for r in naive}
    w = t = l = 0
    ids_aligned = 0
    for r in ours:
        if r["id"] not in bmap:
            continue
        ids_aligned += 1
        a = bool(r.get(metric))
        b = bool(bmap[r["id"]].get(metric))
        if a and not b:
            w += 1
        elif a == b:
            t += 1
        else:
            l += 1
    return {"W": w, "T": t, "L": l, "n": ids_aligned, "WTL": f"{w}/{t}/{l}"}


def main() -> int:
    tasks_path = TASKS_DIR / "msb_v0.1_tasks.json"
    assert_allowed_task_path(tasks_path)
    raw = json.loads(tasks_path.read_text())
    tasks = raw["tasks"] if isinstance(raw, dict) and "tasks" in raw else raw
    by = {t["id"]: t for t in tasks}

    pred_path = Path(sys.argv[1]) if len(sys.argv) > 1 else RESULTS_DIR / "codes" / "v0.1_codes_beams.jsonl"
    rows_in = [json.loads(l) for l in pred_path.read_text().splitlines() if l.strip()]
    errs = [r for r in rows_in if r.get("error")]
    if errs:
        print("WARNING error rows", len(errs), errs[0].get("id"), errs[0].get("error"))

    scored = []
    for r in rows_in:
        if r.get("error") or r["id"] not in by:
            continue
        t = by[r["id"]]
        sql, val, note = first_executable(r.get("sqls"), DB_PATH)
        pred = {"behavior": "compute", "sql": sql, "value": val, "error": note}
        s = score_one(t, pred)
        s["baseline"] = "codes-7b-spider"
        s["pred_sql"] = sql
        s["beam_sqls"] = r.get("sqls")
        s["elapsed_s"] = r.get("elapsed_s")
        s["used_usd_col"] = bool(sql and "net_paid_usd" in str(sql))
        s["used_raw_col"] = bool(
            sql
            and ("ss_net_paid" in str(sql) or "ws_net_paid" in str(sql) or "cs_net_paid" in str(sql))
        )
        scored.append(s)

    complete = len(scored) == len(tasks) and not errs
    summary = summarize_v01(scored) if scored else {}
    per = merge_v01()
    naive = per.get("naive_surface") or []
    contrasts = {}
    wtl_ta = None
    if naive and scored:
        for m in ("TA", "compute_accuracy", "FAR_on_clarify_or_refuse", "CRR"):
            contrasts[m] = contrast_v01(scored, naive, m)
        wtl_ta = wtl(scored, naive, "TA")

    report = {
        "fold": "v0.1",
        "role": "DEV profile only; not an official held-out row. Protocol §6.",
        "system": "codes-7b-spider",
        "checkpoint": "seeklhy/codes-7b-spider",
        "quantization": "4-bit NF4 bitsandbytes, max_memory 16GiB, co-resident GPU service undisturbed",
        "generation": "num_beams=4, num_return_sequences=4, max_new_tokens=256, first executable SQL",
        "n": len(scored),
        "n_tasks_fold": len(tasks),
        "n_error_rows": len(errs),
        "complete": complete,
        "summary": summary,
        "contrast_vs_naive": contrasts,
        "WTL_TA_vs_naive": wtl_ta,
        "note": (
            "Always-answer CodeS-7B Spider SFT, official prompt, no C/C/R wrap. "
            "DEV only. Gold and prompts were frozen before scores were seen. "
            "This is not an official TEST row."
        ),
        "aggregate_raw": _agg(scored) if scored else {},
        "per_task": scored,
    }
    dest = RESULTS_DIR / "paper15_official" / "msb_v0.1_codes_ci.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print("wrote", dest)
    print("complete", complete, "n", len(scored), "/", len(tasks))
    if summary:
        print("TA", summary.get("TA"))
        print("EX", summary.get("compute_accuracy"))
        print("FAR", summary.get("FAR_on_clarify_or_refuse"))
    print("WTL", wtl_ta)
    if not complete:
        print("INCOMPLETE — do not add a manuscript row")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
