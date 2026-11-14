"""Run DIN-SQL and DAIL-SQL (published prompting) via llmhub on DeepSeek V4 Pro (ark)."""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

os.environ.pop("OPENAI_API_KEY", None)
os.environ.pop("ANTHROPIC_API_KEY", None)

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from msb.baselines.llm_published import HubDAILSQLBaseline, HubDINSQLBaseline
from msb.config import RESULTS_DIR, TASKS_DIR, VERSION
from msb.evaluate import _agg, _pct, blind_view, score_one


def main():
    tasks = json.loads((TASKS_DIR / f"msb_{VERSION}_tasks.json").read_text())["tasks"]
    systems = [
        HubDAILSQLBaseline("ark/deepseek-v4-pro", "metricsembench-v0.1-dailsql", "ark_deepseek-v4-pro_dailsql"),
        HubDINSQLBaseline("ark/deepseek-v4-pro", "metricsembench-v0.1-dinsql", "ark_deepseek-v4-pro_dinsql"),
    ]
    tables, per, costs = {}, {}, {}
    for sys_obj in systems:
        name = sys_obj.name
        rows, spent, t0, stopped = [], 0.0, time.time(), None
        for i, t in enumerate(tasks, 1):
            pred = sys_obj.answer(blind_view(t))
            if pred.get("error") == "QuotaExceeded":
                stopped = pred.get("quota")
                print(f"  QUOTA STOP {name} after {i-1}", flush=True)
                break
            spent += float(pred.get("cost_usd") or 0)
            s = score_one(t, pred)
            s["baseline"] = name
            s["cost_usd"] = pred.get("cost_usd")
            s["error"] = pred.get("error")
            rows.append(s)
            if i % 10 == 0 or i == len(tasks):
                acc = sum(r["TA"] for r in rows) / max(len(rows), 1)
                print(f"  {name} {i}/{len(tasks)} TA={acc:.3f} spent=${spent:.4f} elapsed={time.time()-t0:.0f}s", flush=True)
        per[name] = rows
        tables[name] = _agg(rows) if rows else {}
        costs[name] = {"spent_usd": spent, "n": len(rows), "quota_stop": stopped}
        print(f"{name} DONE {tables[name]} cost={costs[name]}", flush=True)
    out = RESULTS_DIR / f"msb_{VERSION}_published.json"
    out.write_text(json.dumps({"summary": tables, "per_task": per, "llmhub_costs": costs, "note": "DIN-SQL (Pourreza & Rafiei 2023) and DAIL-SQL (Gao et al.) prompting on ark/deepseek-v4-pro via llmhub. Always-answer Text-to-SQL. CodeS checkpoint not run (GPU unreachable from box)."}, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print("wrote", out, tables)


if __name__ == "__main__":
    main()
