"""One-shot official evaluation of Paper 15's second held-out (`p15_heldout_v2`).

Pre-registered in PREREG_P15_HELDOUT_V2.md BEFORE any score on the fold. Systems,
prompts, schema card, request extras and decoding are identical to the v0.1 / v1
profiles. No --limit. JSONL checkpoint per system; resume only re-asks ids that
have no successful prediction (API errors are not scored, never re-asked after a
successful prediction). Never loads paper-13 official TEST folds.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

os.environ.pop("OPENAI_API_KEY", None)
os.environ.pop("ANTHROPIC_API_KEY", None)

from msb.baselines import BASELINES
from msb.baselines.llm_hub import HubDirectBaseline, HubSemanticBaseline
from msb.baselines.llm_published import HubDAILSQLBaseline, HubDINSQLBaseline
from msb.build_paper15_heldout import _payload_sha
from msb.config import DB_PATH, RESULTS_DIR, TASKS_DIR
from msb.evaluate import _agg, blind_view, score_one
from msb.forbidden_folds import assert_allowed_task_path
from msb import run_frontier as RF

FOLD = "p15_heldout_v2"
TASK = TASKS_DIR / "msb_p15_heldout_v2_tasks.json"
EXPECTED_SHA = "abe30e25701882ef9ad3b9a53fefbe641b8c7aa2b0932b0cf8dab11d68c4db97"  # pre-registered freeze SHA
OUT = RESULTS_DIR / "paper15_official" / "v2"
EXP = "metricsembench-p15-heldout-v2"


def hub_systems():
    return {
        "ark_deepseek-v4-pro_semantic": HubSemanticBaseline("ark/deepseek-v4-pro", EXP, "ark_deepseek-v4-pro_semantic"),
        "tokens1688_claude-sonnet-4-6_semantic": HubSemanticBaseline("tokens1688/claude-sonnet-4-6", EXP, "tokens1688_claude-sonnet-4-6_semantic"),
        "tokens1688_gpt-6-sol_semantic": HubSemanticBaseline("tokens1688/gpt-6-sol", EXP, "tokens1688_gpt-6-sol_semantic"),
        "tokens1688_gpt-6-sol_direct": HubDirectBaseline("tokens1688/gpt-6-sol", EXP, "tokens1688_gpt-6-sol_direct"),
        "ark_deepseek-v4-pro_dailsql": HubDAILSQLBaseline("ark/deepseek-v4-pro", EXP + "-dailsql", "ark_deepseek-v4-pro_dailsql"),
        "ark_deepseek-v4-pro_dinsql": HubDINSQLBaseline("ark/deepseek-v4-pro", EXP + "-dinsql", "ark_deepseek-v4-pro_dinsql"),
    }


def load():
    assert_allowed_task_path(TASK)
    payload = json.loads(TASK.read_text(encoding="utf-8"))
    body = dict(payload)
    body["evaluated"] = False
    sha = _payload_sha(body)
    if sha != payload["sha256"]:
        raise SystemExit("freeze sha does not recompute")
    if EXPECTED_SHA and sha != EXPECTED_SHA:
        raise SystemExit(f"sha {sha} != pre-registered {EXPECTED_SHA}")
    return payload, payload["tasks"]


def ck(name):
    OUT.mkdir(parents=True, exist_ok=True)
    return OUT / f"{FOLD}__{name}.jsonl"


def run_generic(name, sys_obj, tasks, cap=15.0):
    path = ck(name)
    done = RF.load_done(path)
    spent = sum(float(r.get("cost_usd") or 0) for r in done.values())
    print(f"== {name} resume={len(done)} remaining={sum(t['id'] not in done for t in tasks)}", flush=True)
    t0 = time.time()
    for i, t in enumerate(tasks, 1):
        if t["id"] in done:
            continue
        if spent >= cap:
            print(f"  SOFT CAP {name} ${spent:.3f}", flush=True)
            break
        pred = sys_obj.answer(blind_view(t))
        if pred.get("error"):
            print(f"  API ERROR {name} {t['id']}: {pred.get('error')} {str(pred.get('err') or pred.get('quota'))[:200]}", flush=True)
            if pred.get("error") == "QuotaExceeded":
                break
            time.sleep(5)
            continue
        spent += float(pred.get("cost_usd") or 0)
        s = score_one(t, pred)
        rec = {**s, "baseline": name, "cost_usd": pred.get("cost_usd"), "cached": pred.get("cached"),
               "pred_sql": pred.get("sql"), "brief": pred.get("brief"), "clarify_axes": pred.get("clarify_axes"),
               "channel": pred.get("channel"), "provider_model": pred.get("provider_model")}
        RF.append_ckpt(path, rec)
        done[t["id"]] = rec
        if len(done) % 10 == 0:
            ta = sum(int(r.get("TA") or 0) for r in done.values()) / len(done)
            print(f"  {name} {len(done)}/{len(tasks)} TA={ta:.3f} spent=${spent:.3f} elapsed={time.time()-t0:.0f}s", flush=True)
    rows = [done[t["id"]] for t in tasks if t["id"] in done]
    print(f"{name} DONE n={len(rows)}/{len(tasks)} spent=${spent:.3f} {_agg(rows) if rows else {}}", flush=True)


def run_deterministic(tasks):
    for name, cls in BASELINES.items():
        path = ck(name)
        if path.exists():
            print("skip existing", name)
            continue
        sys_obj = cls()
        for t in tasks:
            s = score_one(t, sys_obj.answer(blind_view(t)))
            s["baseline"] = name
            RF.append_ckpt(path, s)
        print("deterministic", name, "done")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--system", required=True, help="deterministic | frontier substring | hub system name")
    a = ap.parse_args()
    payload, tasks = load()
    print(f"fold={FOLD} n={len(tasks)} sha={payload['sha256']}", flush=True)
    if a.system == "deterministic":
        run_deterministic(tasks)
        return
    fr = [s for s in RF.SYSTEMS if a.system in s["name"]]
    if fr:
        for spec in fr:
            spec = {**spec, "soft_cap": 15.0}
            # run_frontier writes to its own CKPT_DIR; point it at v2 output
            RF.CKPT_DIR = OUT
            RF.run_system(spec, tasks, FOLD, EXP, DB_PATH)
        return
    hs = hub_systems()
    if a.system not in hs:
        raise SystemExit(f"unknown system {a.system}")
    run_generic(a.system, hs[a.system], tasks)


if __name__ == "__main__":
    main()
