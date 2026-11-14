"""Frontier-LLM semantic baselines for Paper 15, via llmhub.

Protocol (frozen; summarized in README.md, section Protocol):
  - tokens1688_2/claude-opus-5    reasoning_effort=max, thinking adaptive
  - tokens1688_2/claude-opus-5-5  reasoning_effort=high
  - tokens1688_2/gpt-6-luna       reasoning_effort=high
  Same SCHEMA_CARD + SEMANTIC_RULES as mid-tier runs. temperature 0.
  Per-model soft cap $18. Stops on QuotaExceeded.
  JSONL checkpoints; resume skips completed ids. Does not re-query cache-hits.

NEVER loads paper-13 official TEST folds (forbidden_folds).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import traceback
from collections import defaultdict
from pathlib import Path

os.environ.pop("OPENAI_API_KEY", None)
os.environ.pop("ANTHROPIC_API_KEY", None)

from llmhub import QuotaExceeded, chat as hub_chat

from msb.baselines.llm_qwen import _extract_json, _extract_sql, exec_scalar
from msb.config import DB_PATH, RESULTS_DIR, TASKS_DIR
from msb.evaluate import _agg, blind_view, score_one
from msb.forbidden_folds import assert_allowed_task_path
from msb.paper15_stats import summarize_v01
from msb.prompts.schema_card import SCHEMA_CARD, SEMANTIC_RULES

SOFT_CAP = 18.0
EXPERIMENT_V01 = "metricsembench-p15-frontier-v0.1"
EXPERIMENT_HELD = "metricsembench-p15-frontier-heldout-v1"
CKPT_DIR = RESULTS_DIR / "frontier"

SYSTEMS = [
    {
        "name": "tokens1688_2_claude-opus-5_semantic_max",
        "model": "tokens1688_2/claude-opus-5",
        "experiment_v01": EXPERIMENT_V01,
        "experiment_held": EXPERIMENT_HELD,
        "extra": {"reasoning_effort": "max", "thinking": {"type": "adaptive"}},
        "extra_fallback": {"reasoning_effort": "max"},
        "max_tokens": 16000,
        "soft_cap": SOFT_CAP,
    },
    {
        "name": "tokens1688_2_claude-opus-5-5_semantic_high",
        "model": "tokens1688_2/claude-opus-5-5",
        "experiment_v01": EXPERIMENT_V01,
        "experiment_held": EXPERIMENT_HELD,
        # Channel requires adaptive thinking (HTTP 400 otherwise, observed on probe).
        # effort=high is the strongest this model accepted.
        # Frozen after probe: reasoning_effort=high alone is intermittent (1/2 HTTP 400);
        # reasoning_effort combined with adaptive also 400; this pair is the working setting.
        "extra": {
            "thinking": {"type": "adaptive"},
            "output_config": {"effort": "high"},
        },
        "extra_fallback": {
            "thinking": {"type": "adaptive"},
            "output_config": {"effort": "high"},
        },
        "max_tokens": 16000,
        "soft_cap": SOFT_CAP,
    },
    {
        "name": "tokens1688_2_gpt-6-luna_semantic",
        "model": "tokens1688_2/gpt-6-luna",
        "experiment_v01": EXPERIMENT_V01,
        "experiment_held": EXPERIMENT_HELD,
        "extra": {"reasoning_effort": "high"},
        "extra_fallback": {"reasoning_effort": "medium"},
        "max_tokens": 8192,
        "soft_cap": 12.0,
    },
]


def _parse_behavior(content: str, js: dict) -> str:
    behavior = (js.get("behavior") or "").strip().lower()
    if behavior in ("compute", "clarify", "refuse"):
        return behavior
    tl = content.lower()
    if "\"clarify\"" in tl or (tl.find("clarify") >= 0 and tl.find("compute") > 80):
        return "clarify"
    if "refuse" in tl:
        return "refuse"
    return "compute"


def call_one(spec: dict, task_view: dict, experiment: str, db_path, used_fallback: dict) -> dict:
    q = task_view["question_en"]
    zh = task_view.get("question_zh") or ""
    messages = [
        {"role": "system", "content": SCHEMA_CARD + "\n\n" + SEMANTIC_RULES},
        {"role": "user", "content": f"Question (EN): {q}\nQuestion (ZH): {zh}\n\nJSON:"},
    ]
    extra = spec["extra"] if not used_fallback.get(spec["name"]) else (spec.get("extra_fallback") or spec["extra"])
    try:
        r = hub_chat(
            spec["model"],
            messages,
            experiment=experiment,
            max_tokens=spec["max_tokens"],
            temperature=None,  # opus-5 / luna reject `temperature` (HTTP 400)
            extra=extra,
        )
    except QuotaExceeded as e:
        return {"behavior": "compute", "sql": None, "value": None, "error": "QuotaExceeded", "quota": str(e)[:300]}
    except Exception as e:
        msg = str(e)
        # If adaptive thinking is rejected, retry once with the fallback extra.
        if (
            not used_fallback.get(spec["name"])
            and spec.get("extra_fallback")
            and any(s in msg.lower() for s in ("thinking", "reasoning_effort", "adaptive", "400", "invalid", "unsupported"))
        ):
            used_fallback[spec["name"]] = True
            print(f"  FALLBACK extra for {spec['name']}: {type(e).__name__}: {msg[:200]}", flush=True)
            return call_one(spec, task_view, experiment, db_path, used_fallback)
        return {
            "behavior": "compute",
            "sql": None,
            "value": None,
            "error": type(e).__name__,
            "err": msg[:500],
        }
    content = r.text or ""
    js = _extract_json(content) or {}
    behavior = _parse_behavior(content, js)
    sql = js.get("sql") or (_extract_sql(content) if behavior == "compute" else None)
    value = exec_scalar(sql, db_path) if (behavior == "compute" and sql) else None
    return {
        "behavior": behavior,
        "sql": sql,
        "value": value,
        "refuse_reason_cat": js.get("refuse_reason"),
        "clarify_axes": js.get("clarify_axes"),
        "brief": js.get("brief"),
        "raw": content[:4000],
        "cost_usd": r.cost_usd,
        "cached": r.cached,
        "channel": r.channel,
        "provider_model": r.provider_model,
        "used_fallback_extra": bool(used_fallback.get(spec["name"])),
    }


def ckpt_path(fold: str, name: str) -> Path:
    CKPT_DIR.mkdir(parents=True, exist_ok=True)
    return CKPT_DIR / f"{fold}__{name}.jsonl"


def load_done(path: Path) -> dict[str, dict]:
    done = {}
    if not path.exists():
        return done
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        rec = json.loads(line)
        # Only resume successfully scored items. API errors and quota stops are retried / halt.
        if rec.get("id") and not rec.get("error"):
            done[rec["id"]] = rec
    return done


def append_ckpt(path: Path, rec: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
        f.flush()
        os.fsync(f.fileno())


def run_system(spec: dict, tasks: list[dict], fold: str, experiment: str, db_path, limit: int | None = None) -> dict:
    name = spec["name"]
    path = ckpt_path(fold, name)
    done = load_done(path)
    spent = sum(float(r.get("cost_usd") or 0) for r in done.values() if not r.get("cached"))
    # cached costs are 0 in ledger; sum all recorded for display
    spent = sum(float(r.get("cost_usd") or 0) for r in done.values())
    used_fallback: dict = {}
    if any(r.get("used_fallback_extra") for r in done.values()):
        used_fallback[name] = True
    todo = tasks[:limit] if limit else tasks
    print(f"== {name} fold={fold} resume={len(done)} remaining={sum(1 for t in todo if t['id'] not in done)} spent_so_far=${spent:.4f}", flush=True)
    t0 = time.time()
    stopped = None
    for i, t in enumerate(todo, 1):
        if t["id"] in done:
            continue
        if spent >= spec["soft_cap"]:
            stopped = f"soft_cap ${spec['soft_cap']}"
            print(f"  SOFT CAP {name} spent=${spent:.4f}", flush=True)
            break
        pred = call_one(spec, blind_view(t), experiment, db_path, used_fallback)
        if pred.get("error") == "QuotaExceeded":
            stopped = pred.get("quota")
            print(f"  QUOTA STOP {name}: {stopped}", flush=True)
            append_ckpt(path, {"id": t["id"], "error": "QuotaExceeded", "quota": stopped})
            break
        if pred.get("error"):
            print(f"  API ERROR {name} {t['id']}: {pred.get('error')} {pred.get('err') or pred.get('quota')}", flush=True)
            # Do not checkpoint as a scored prediction; leave unfinished for resume.
            # Consecutive errors: stop the system rather than spinning.
            stopped = f"api_error:{pred.get('error')}:{str(pred.get('err') or '')[:160]}"
            break
        cost = float(pred.get("cost_usd") or 0)
        spent += cost
        s = score_one(t, pred)
        rec = {
            **s,
            "baseline": name,
            "cost_usd": pred.get("cost_usd"),
            "cached": pred.get("cached"),
            "error": pred.get("error"),
            "err": pred.get("err"),
            "channel": pred.get("channel"),
            "provider_model": pred.get("provider_model"),
            "used_fallback_extra": pred.get("used_fallback_extra"),
            "pred_sql": pred.get("sql"),
            "brief": pred.get("brief"),
            "clarify_axes": pred.get("clarify_axes"),
            "raw_head": (pred.get("raw") or "")[:500],
        }
        append_ckpt(path, rec)
        done[t["id"]] = rec
        if i % 5 == 0 or i == len(todo) or cost >= 0.5:
            acc = sum(r.get("TA") or 0 for r in done.values() if r.get("id") in {x["id"] for x in todo}) / max(
                sum(1 for x in todo if x["id"] in done), 1
            )
            print(
                f"  {name} {len([x for x in todo if x['id'] in done])}/{len(todo)} "
                f"TA={acc:.3f} spent=${spent:.4f} last=${cost:.4f} cached={pred.get('cached')} "
                f"elapsed={time.time()-t0:.0f}s",
                flush=True,
            )
    # aligned rows in task order
    rows = []
    for t in todo:
        if t["id"] in done and done[t["id"]].get("error") != "QuotaExceeded":
            rows.append(done[t["id"]])
    summary = _agg(rows) if rows else {}
    print(f"{name} DONE n={len(rows)} {summary} spent=${spent:.4f} stop={stopped}", flush=True)
    return {
        "name": name,
        "rows": rows,
        "summary": summary,
        "spent_usd": spent,
        "n": len(rows),
        "n_tasks": len(todo),
        "quota_or_cap_stop": stopped,
        "ckpt": str(path),
    }


def load_fold(path: Path) -> tuple[dict, list]:
    assert_allowed_task_path(path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("evaluated") is False and "heldout" in path.name:
        # Loading for a first official eval is allowed; we do not flip the flag here.
        pass
    return payload, payload["tasks"]


def write_report(fold: str, payload: dict, results: list[dict], out_stem: str) -> None:
    summaries = {r["name"]: summarize_v01(r["rows"]) if r["rows"] else {} for r in results}
    raw = {
        "fold": fold,
        "n_tasks": payload.get("n_tasks") or payload.get("n"),
        "sha256": payload.get("sha256"),
        "evaluated_this_run": True,
        "systems": {
            r["name"]: {
                "summary_point": r["summary"],
                "summary_ci": summaries[r["name"]],
                "spent_usd": r["spent_usd"],
                "n": r["n"],
                "n_tasks": r["n_tasks"],
                "quota_or_cap_stop": r["quota_or_cap_stop"],
                "per_task": [
                    {k: v for k, v in row.items() if k not in ("pred_sql", "raw_head", "brief")}
                    for row in r["rows"]
                ],
            }
            for r in results
        },
    }
    out = CKPT_DIR / f"{out_stem}.json"
    out.write_text(json.dumps(raw, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    lines = [
        f"# Frontier semantic profile — {fold}",
        "",
        f"SHA `{payload.get('sha256', '—')}`. n={payload.get('n_tasks')}. Protocol: semantic compute/clarify/refuse, "
        "tokens1688_2, reasoning_effort max/high as registered. Bootstrap CIs seed 20261112.",
        "Paper-13 official TEST folds were not used.",
        "",
        "| System | n | spent | TA | Compute Acc | FAR | CRR | Missed | UCR | DSR | stop |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    from msb.public_stats import fmt_ci
    for r in results:
        s = summaries[r["name"]]
        def c(k):
            return fmt_ci(s[k]) if s and s.get(k) else "—"
        lines.append(
            f"| {r['name']} | {r['n']} | ${r['spent_usd']:.3f} | {c('TA')} | {c('compute_accuracy')} | "
            f"{c('FAR_on_clarify_or_refuse')} | {c('CRR')} | {c('missed_clarify')} | {c('unnecessary_clarify')} | "
            f"{c('DSR')} | {r['quota_or_cap_stop']} |"
        )
    md = CKPT_DIR / f"{out_stem}.md"
    md.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("wrote", out, md)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fold", choices=["v0.1", "heldout", "probe"], required=True)
    ap.add_argument("--limit", type=int, default=None, help="first N tasks (probe)")
    ap.add_argument("--system", default=None, help="run only this system name substring")
    args = ap.parse_args()
    if args.fold == "v0.1" or args.fold == "probe":
        path = TASKS_DIR / "msb_v0.1_tasks.json"
        exp = EXPERIMENT_V01
        fold = "v0.1" if args.fold == "v0.1" else "v0.1_probe"
        limit = args.limit if args.limit is not None else (2 if args.fold == "probe" else None)
    else:
        path = TASKS_DIR / "msb_p15_heldout_v1_tasks.json"
        exp = EXPERIMENT_HELD
        fold = "p15_heldout_v1"
        limit = args.limit
        # Official TEST: refuse if someone tries to use it as a probe with a tiny
        # non-pre-registered slice that would still write scores into the official ckpt.
        if limit is not None:
            raise SystemExit(
                "Refusing --limit on the official held-out. Evaluate the full frozen "
                "fold once, after the protocol is frozen. Use --fold v0.1 or probe for DEV."
            )
    payload, tasks = load_fold(path)
    if payload.get("sha256") and fold == "p15_heldout_v1":
        expected = "03d26b59479d82ee7d6e71bb73f6bedc4db42204cf8c9d9124604adb53e55cb2"
        if payload["sha256"] != expected:
            raise SystemExit(f"held-out sha mismatch: {payload['sha256']} != {expected}")
        if payload.get("evaluated") is not False and payload.get("evaluated") is not True:
            pass
    db = DB_PATH
    if not db.exists():
        raise SystemExit(f"missing {db}")
    specs = SYSTEMS
    if args.system:
        specs = [s for s in SYSTEMS if args.system in s["name"] or args.system in s["model"]]
        if not specs:
            raise SystemExit(f"no system matched {args.system}")
    results = []
    for spec in specs:
        results.append(run_system(spec, tasks, fold, exp, db, limit=limit))
    write_report(fold, payload, results, f"frontier_{fold}")
    # If this was the official held-out and all systems finished all tasks, we
    # do NOT flip evaluated=false in the task file from this script (that is a
    # separate, explicit commit after review).


if __name__ == "__main__":
    main()
