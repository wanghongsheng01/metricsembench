"""Run local Qwen baselines on MetricSemBench v0.1. Resumable via cache. Gold-blind."""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from msb.baselines.llm_qwen import (
    QwenDirectBaseline,
    QwenSemanticBaseline,
    QwenDINSQLBaseline,
    QwenDAILSQLBaseline,
)
from msb.config import RESULTS_DIR, TASKS_DIR, VERSION
from msb.evaluate import _agg, _markdown, _pct, blind_view, score_one


SYSTEMS = {
    "qwen25_7b_direct": QwenDirectBaseline,
    "qwen25_7b_semantic": QwenSemanticBaseline,
    "qwen25_7b_dinsql": QwenDINSQLBaseline,
    "qwen25_7b_dailsql": QwenDAILSQLBaseline,
}


def run(names: list[str] | None = None, limit: int | None = None) -> Path:
    payload = json.loads((TASKS_DIR / f"msb_{VERSION}_tasks.json").read_text(encoding="utf-8"))
    tasks = payload["tasks"]
    if limit:
        tasks = tasks[:limit]
    names = names or list(SYSTEMS.keys())
    all_rows = {}
    tables = {}
    by_type = {}
    for name in names:
        sys_obj = SYSTEMS[name]()
        rows = []
        t0 = time.time()
        for i, t in enumerate(tasks, 1):
            pred = sys_obj.answer(blind_view(t))
            s = score_one(t, pred)
            s["baseline"] = name
            s["pred_sql"] = (pred.get("sql") or "")[:500]
            s["pred_error"] = pred.get("error")
            rows.append(s)
            if i % 10 == 0 or i == len(tasks):
                acc = sum(r["TA"] for r in rows) / len(rows)
                print(f"  {name} {i}/{len(tasks)} TA_so_far={acc:.3f} elapsed={time.time()-t0:.0f}s", flush=True)
        all_rows[name] = rows
        tables[name] = _agg(rows)
        from collections import defaultdict
        tm = defaultdict(list)
        for r in rows:
            tm[r["type"]].append(r)
        by_type[name] = {k: _agg(v) for k, v in tm.items()}
        print(f"{name} DONE", tables[name], flush=True)

    # merge with previous deterministic summary if present
    prev = RESULTS_DIR / f"msb_{VERSION}_eval.json"
    merged_summary = {}
    merged_by = {}
    merged_per = {}
    if prev.exists():
        old = json.loads(prev.read_text(encoding="utf-8"))
        merged_summary.update(old.get("summary") or {})
        merged_by.update(old.get("by_type") or {})
        merged_per.update(old.get("per_task") or {})
    merged_summary.update(tables)
    merged_by.update(by_type)
    merged_per.update({n: [{k: v for k, v in r.items() if k != "pred_sql"} for r in rows] for n, rows in all_rows.items()})

    out = RESULTS_DIR / f"msb_{VERSION}_eval_with_llm.json"
    notes = {
        "gpt": "Paid GPT not run this cut: llmhub $50/day cap not yet landed; do not spend uncapped paid APIs.",
        "claude": "ANTHROPIC_API_KEY / llmhub cap pending; not run, not fabricated.",
        "qwen": "Local Qwen2.5-7B-Instruct Q4_K_M on GPU A10 via llama.cpp (n_ctx=8192).",
        "codes": "Actual CodeS checkpoint not run in this cut (see 进展). DIN-SQL and DAIL-SQL are prompting methods on Qwen, labeled as such.",
    }
    out.write_text(
        json.dumps(
            {
                "version": VERSION,
                "n_tasks": len(tasks),
                "summary": merged_summary,
                "by_type": merged_by,
                "per_task": merged_per,
                "notes": notes,
            },
            indent=2,
            ensure_ascii=False,
            default=str,
        ),
        encoding="utf-8",
    )
    # markdown table of all systems in merged_summary
    md_path = RESULTS_DIR / f"msb_{VERSION}_sota_table_with_llm.md"
    lines = [
        f"# MetricSemBench {VERSION} — baselines including local Qwen2.5-7B",
        "",
        f"- Tasks: {len(tasks)}. Gold-blind.",
        "- GPT / Claude: **not run** (llmhub daily cap not landed; paid APIs not spent). Not fabricated.",
        "- Qwen2.5-7B-Instruct Q4_K_M, local GPU A10, llama.cpp.",
        "- `qwen25_7b_dinsql` / `qwen25_7b_dailsql` are **prompting methods on Qwen**, not the original CodeS/DIN-SQL/DAIL-SQL model checkpoints.",
        "",
        "| Baseline | n | TA | Compute Acc | DSR | FAR (clarify∪refuse) | CRR | Missed clarify | Illegal YoY | Illegal Agg |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for name, s in merged_summary.items():
        lines.append(
            f"| {name} | {s.get('n','')} | {_pct(s.get('TA'))} | {_pct(s.get('compute_accuracy'))} | "
            f"{_pct(s.get('DSR'))} | {_pct(s.get('FAR_on_clarify_or_refuse'))} | {_pct(s.get('CRR'))} | "
            f"{_pct(s.get('missed_clarify'))} | {_pct(s.get('IllegalYoY'))} | {_pct(s.get('IllegalAgg'))} |"
        )
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("wrote", out, md_path)
    return out


if __name__ == "__main__":
    names = sys.argv[1:] or None
    run(names=names)
