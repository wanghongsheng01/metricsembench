"""Run llmhub GPT/Claude/Ark baselines. Experiment-tagged. Stops on QuotaExceeded."""
from __future__ import annotations

import json
import os
import sys
import time
from collections import defaultdict
from pathlib import Path

# Must drop invalid OPENAI_API_KEY before llmhub is used.
os.environ.pop("OPENAI_API_KEY", None)
os.environ.pop("ANTHROPIC_API_KEY", None)

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from msb.baselines.llm_hub import HubDirectBaseline, HubSemanticBaseline
from msb.config import RESULTS_DIR, TASKS_DIR, VERSION
from msb.evaluate import _agg, _pct, blind_view, score_one

# (name, constructor)
def systems_15():
    return [
        ("tokens1688_gpt-6-sol_semantic", HubSemanticBaseline("tokens1688/gpt-6-sol", "metricsembench-v0.1", "tokens1688_gpt-6-sol_semantic")),
        ("tokens1688_gpt-6-sol_direct", HubDirectBaseline("tokens1688/gpt-6-sol", "metricsembench-v0.1", "tokens1688_gpt-6-sol_direct")),
        ("tokens1688_claude-sonnet-4-6_semantic", HubSemanticBaseline("tokens1688/claude-sonnet-4-6", "metricsembench-v0.1", "tokens1688_claude-sonnet-4-6_semantic")),
        ("ark_deepseek-v4-pro_semantic", HubSemanticBaseline("ark/deepseek-v4-pro", "metricsembench-v0.1", "ark_deepseek-v4-pro_semantic")),
    ]


def run_on_tasks(tasks, systems, out_stem: str):
    all_rows = {}
    tables = {}
    by_type = {}
    costs = {}
    for name, sys_obj in systems:
        rows = []
        spent = 0.0
        t0 = time.time()
        stopped = None
        for i, t in enumerate(tasks, 1):
            pred = sys_obj.answer(blind_view(t))
            if pred.get("error") == "QuotaExceeded":
                stopped = pred.get("quota")
                print(f"  QUOTA STOP {name} after {i-1} tasks: {stopped}", flush=True)
                break
            spent += float(pred.get("cost_usd") or 0)
            s = score_one(t, pred)
            s["baseline"] = name
            s["cost_usd"] = pred.get("cost_usd")
            s["cached"] = pred.get("cached")
            s["error"] = pred.get("error")
            rows.append(s)
            if i % 10 == 0 or i == len(tasks):
                acc = sum(r["TA"] for r in rows) / max(len(rows), 1)
                print(
                    f"  {name} {i}/{len(tasks)} TA={acc:.3f} spent=${spent:.4f} "
                    f"elapsed={time.time()-t0:.0f}s",
                    flush=True,
                )
        all_rows[name] = rows
        tables[name] = _agg(rows) if rows else {}
        costs[name] = {"spent_usd": spent, "n": len(rows), "quota_stop": stopped}
        tm = defaultdict(list)
        for r in rows:
            tm[r["type"]].append(r)
        by_type[name] = {k: _agg(v) for k, v in tm.items()}
        print(f"{name} DONE {tables[name]} cost={costs[name]}", flush=True)
        if stopped:
            break  # stop remaining systems on same channel? No: different channels. Only this system stopped.
    return all_rows, tables, by_type, costs


def main():
    payload = json.loads((TASKS_DIR / f"msb_{VERSION}_tasks.json").read_text(encoding="utf-8"))
    tasks = payload["tasks"]
    rows, tables, by_type, costs = run_on_tasks(tasks, systems_15(), "msb")

    # merge qwen + deterministic
    merged_summary, merged_by, merged_per = {}, {}, {}
    prev = RESULTS_DIR / f"msb_{VERSION}_eval.json"
    if prev.exists():
        old = json.loads(prev.read_text(encoding="utf-8"))
        merged_summary.update(old.get("summary") or {})
        merged_by.update(old.get("by_type") or {})
        merged_per.update(old.get("per_task") or {})
    qwen = RESULTS_DIR / f"msb_{VERSION}_qwen_partial.json"
    if qwen.exists():
        q = json.loads(qwen.read_text(encoding="utf-8"))
        for n, v in q.items():
            merged_summary[n] = v["summary"]
            merged_per[n] = v["per_task"]
    merged_summary.update(tables)
    merged_by.update(by_type)
    merged_per.update({n: rows_n for n, rows_n in rows.items()})

    out = RESULTS_DIR / f"msb_{VERSION}_eval_with_llm.json"
    out.write_text(
        json.dumps(
            {
                "version": VERSION,
                "n_tasks": len(tasks),
                "summary": merged_summary,
                "by_type": merged_by,
                "per_task": merged_per,
                "llmhub_costs": costs,
                "notes": {
                    "gpt": "tokens1688/gpt-6-sol via llmhub, experiment=metricsembench-v0.1. Not OpenAI official API.",
                    "claude": "tokens1688/claude-sonnet-4-6 via llmhub (prompt_tokens may be inflated; costs conservative).",
                    "deepseek": "ark/deepseek-v4-pro via llmhub.",
                    "qwen": "Local Qwen2.5-7B Q4_K_M completed for direct+semantic before GPU became unreliable; DIN-SQL/DAIL-SQL not finished.",
                    "codes": "CodeS checkpoint not run this cut.",
                    "openai_api_key": "Not used (invalid wrapped env). ANTHROPIC_API_KEY not used.",
                },
            },
            indent=2,
            ensure_ascii=False,
            default=str,
        ),
        encoding="utf-8",
    )
    lines = [
        f"# MetricSemBench {VERSION} — baselines including llmhub GPT/Claude/DeepSeek and local Qwen",
        "",
        "- GPT/Claude via llmhub `tokens1688` (experiment `metricsembench-v0.1`), within $50/day cap.",
        "- DeepSeek via llmhub `ark`. Qwen2.5-7B local GPU (direct + semantic only).",
        "- Official OpenAI/Anthropic keys not used. CodeS checkpoint not run. DIN-SQL/DAIL-SQL on Qwen not finished.",
        "",
        "| Baseline | n | TA | Compute Acc | FAR (clarify∪refuse) | CRR | Missed clarify | Illegal YoY | Illegal Agg |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for name, s in merged_summary.items():
        if not s:
            continue
        lines.append(
            f"| {name} | {s.get('n','')} | {_pct(s.get('TA'))} | {_pct(s.get('compute_accuracy'))} | "
            f"{_pct(s.get('FAR_on_clarify_or_refuse'))} | {_pct(s.get('CRR'))} | {_pct(s.get('missed_clarify'))} | "
            f"{_pct(s.get('IllegalYoY'))} | {_pct(s.get('IllegalAgg'))} |"
        )
    lines += ["", "## llmhub cost (this run, cache hits $0)", ""]
    for n, c in costs.items():
        lines.append(f"- {n}: n={c['n']} spent=${c['spent_usd']:.4f} quota_stop={c['quota_stop']}")
    md = RESULTS_DIR / f"msb_{VERSION}_sota_table_with_llm.md"
    md.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("wrote", out, md)


if __name__ == "__main__":
    main()
