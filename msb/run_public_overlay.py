"""Run all systems on a public BIRD/Spider metric-ambiguity overlay."""
from __future__ import annotations

import json, os, sys, time
from pathlib import Path

os.environ.pop("OPENAI_API_KEY", None)
os.environ.pop("ANTHROPIC_API_KEY", None)

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
# The reference-protocol rows were produced by a companion code base (under submission);
# their predictions are stored in results/. Set MSB_COMPANION_ROOT to re-run them.
BOC = Path(os.environ.get("MSB_COMPANION_ROOT", "companion"))
sys.path.insert(0, str(BOC))
try:
    from boc.binder_v1 import BindOrClarifyV1
    from boc.binder_v1_1 import BindOrClarifyV11
except ImportError:  # companion code not shipped; stored predictions are
    BindOrClarifyV1 = BindOrClarifyV11 = None
from msb.baselines.always_clarify import AlwaysClarifyBaseline
from msb.baselines.always_refuse import AlwaysRefuseBaseline
from msb.baselines.llm_public import PublicDAILSQLBaseline, PublicSemanticBaseline
from msb.public_score import agg_public, score_public
from msb.tables import md_sota, md_winlose

# A thin always-compute baseline
class AlwaysComputeBaseline:
    name = "always_compute"
    def answer(self, task_view):
        return {"behavior": "compute", "sql": None, "value": None}


def public_view(task: dict) -> dict:
    """Gold-blind public view. Includes official evidence only when the item says so."""
    return {
        "id": task["id"],
        "question_en": task["question_en"],
        "question_zh": task.get("question_zh") or "",
        "db_id": task.get("db_id"),
        "engine": task.get("engine"),
        "evidence": task.get("evidence") or "",
        "external_knowledge": task.get("evidence") or "",
        "prompt_includes_evidence": task.get("prompt_includes_evidence", True),
    }


def systems(exp: str):
    return [
        ("bindorclarify_v1", BindOrClarifyV1()),
        ("bindorclarify_v1_1", BindOrClarifyV11()),
        ("always_compute", AlwaysComputeBaseline()),
        ("always_clarify", AlwaysClarifyBaseline()),
        ("always_refuse", AlwaysRefuseBaseline()),
        ("tokens1688_gpt-6-sol_semantic", PublicSemanticBaseline("tokens1688/gpt-6-sol", exp, "tokens1688_gpt-6-sol_semantic")),
        ("tokens1688_claude-sonnet-4-6_semantic", PublicSemanticBaseline("tokens1688/claude-sonnet-4-6", exp, "tokens1688_claude-sonnet-4-6_semantic")),
        ("ark_deepseek-v4-pro_semantic", PublicSemanticBaseline("ark/deepseek-v4-pro", exp, "ark_deepseek-v4-pro_semantic")),
        ("ark_deepseek-v4-pro_dailsql", PublicDAILSQLBaseline("ark/deepseek-v4-pro", exp + "-dailsql", "ark_deepseek-v4-pro_dailsql")),
    ]


def run(task_file: Path, out_stem: str, exp: str, ours="bindorclarify_v1"):
    payload = json.loads(task_file.read_text(encoding="utf-8"))
    tasks = payload["tasks"]
    print(f"n={len(tasks)} counts={payload.get('counts')} exp={exp}", flush=True)
    tables, per, costs = {}, {}, {}
    for name, sys_obj in systems(exp):
        rows, spent, t0, stopped = [], 0.0, time.time(), None
        is_llm = "tokens1688" in name or "deepseek" in name or "dail" in name
        for i, t in enumerate(tasks, 1):
            pred = sys_obj.answer(public_view(t))
            if pred.get("error") == "QuotaExceeded":
                stopped = pred.get("quota")
                print(f"  QUOTA STOP {name} after {i-1}: {stopped}", flush=True)
                break
            spent += float(pred.get("cost_usd") or 0)
            s = score_public(t, pred)
            s["baseline"] = name
            rows.append(s)
            if i % 5 == 0 or i == len(tasks):
                acc = sum(r["TA"] for r in rows if r["in_official_ta"]) / max(sum(1 for r in rows if r["in_official_ta"]), 1)
                print(f"  {name} {i}/{len(tasks)} official_TA={acc:.3f} spent=${spent:.4f} elapsed={time.time()-t0:.0f}s", flush=True)
        per[name] = rows
        tables[name] = agg_public(rows) if rows else {}
        # map to tables.py metric names
        s = tables[name]
        s["FAR_on_clarify_or_refuse"] = s.get("FAR_on_clarify_or_refuse")
        costs[name] = {"spent_usd": spent, "n": len(rows), "quota_stop": stopped}
        print(f"{name} DONE {tables[name]} cost={costs[name]}", flush=True)
        if stopped:
            break

    outdir = ROOT / "results"
    outdir.mkdir(exist_ok=True)
    out = outdir / f"{out_stem}_eval.json"
    out.write_text(json.dumps({"version": payload.get("version"), "n": len(tasks), "counts": payload.get("counts"),
                               "summary": tables, "per_task": per, "llmhub_costs": costs,
                               "note": payload.get("note")}, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print("wrote", out)

    # tables: only systems with official TA
    order = [ours] + [k for k in tables if k != ours]
    present = [n for n in order if tables.get(n)]
    extra = [
        f"Public metric-ambiguity overlay `{payload.get('version')}`, n={len(tasks)}. "
        "Official TA = clarify/refuse behavior + compute items with official numeric gold "
        "(official BIRD SQL executed on official Mini-Dev SQLite). "
        "Behavior-only compute (Spider without a local DB; multi-column results) is EXCLUDED from official TA "
        "and reported as `behavior_match_all` / `n_compute_behavior_only`. No invented gold.",
        "bindorclarify_v1/v1.1 are TPC-DS dictionary-grounded; transfer failure on public DBs is an honest result, not hidden.",
        "llmhub spend: " + "; ".join(f"{n}: ${c['spent_usd']:.3f}" for n,c in costs.items() if c['spent_usd']) + ".",
    ]
    sota = md_sota({n: tables[n] for n in present},
                   f"Public overlay — SOTA ({payload.get('version')})",
                   ours=ours, extra_lines=extra, order=present)
    win = md_winlose({n: tables[n] for n in present},
                     f"Public overlay — W/T/L vs {ours}",
                     ours=ours,
                     explanations="See 进展: per-component analysis (refuse / clarify / bind). "
                     "TPC-DS binders are not expected to transfer. Official TA track excludes behavior-only compute.")
    (outdir / f"{out_stem}_sota.md").write_text(sota, encoding="utf-8")
    (outdir / f"{out_stem}_winlose.md").write_text(win, encoding="utf-8")
    paper = ROOT.parent
    (paper / f"SOTA表_{out_stem}.md").write_text(sota, encoding="utf-8")
    (paper / f"胜负表_{out_stem}.md").write_text(win, encoding="utf-8")
    print(sota)


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--tasks", default=str(ROOT / "data/public_bench/msb_public_overlay_v0_26.json"))
    ap.add_argument("--out", default="msb_public_v0_26")
    ap.add_argument("--exp", default="metricsembench-public-v0")
    args = ap.parse_args()
    run(Path(args.tasks), args.out, args.exp)
