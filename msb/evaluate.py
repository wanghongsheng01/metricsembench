"""Evaluate baselines on MetricSemBench. Baselines see a gold-blind task view only."""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

from msb.baselines import BASELINES
from msb.config import RESULTS_DIR, TASKS_DIR, VERSION


def _close(a, b, abs_tol=1e-4, rel_tol=1e-5) -> bool:
    if a is None or b is None:
        return False
    try:
        a, b = float(a), float(b)
    except (TypeError, ValueError):
        return False
    return abs(a - b) <= max(abs_tol, rel_tol * max(abs(a), abs(b)))


def blind_view(task: dict) -> dict:
    """What a system is allowed to see. No gold behavior, values, or SQL."""
    return {
        "id": task["id"],
        "question_en": task["question_en"],
        "question_zh": task.get("question_zh", ""),
        "schema_hint": (
            "TPC-DS SF=1 with views msb_store_sales, msb_web_sales, msb_catalog_sales, "
            "msb_store_returns, msb_date; extension metricsem_fx_v1 (store_currency, net_paid_usd)."
        ),
    }


def which_definition(task: dict, value) -> str | None:
    for d in task.get("paired_definitions") or []:
        if _close(value, d.get("value")):
            return d["id"]
    return None


def score_one(task: dict, pred: dict) -> dict:
    gold_b = task["gold_behavior"]
    pred_b = pred.get("behavior")
    pred_v = pred.get("value")
    specified = task.get("specified_definition")
    matched_def = which_definition(task, pred_v) if pred_v is not None else None

    ta = 0  # typed accuracy: behavior+value correct for this task
    dsr = 0  # definition swap: specified A, answered B's value
    far = 0  # false answer: answered a number when should refuse or clarify
    crr = 0  # correct refusal
    missed_clarify = 0
    illegal_yoy = 0
    illegal_agg = 0
    unnecessary_clarify = 0
    compute_ok = 0
    notes = []

    if gold_b == "compute":
        if pred_b == "clarify":
            unnecessary_clarify = 1
            notes.append("clarified a fully specified compute task")
        elif pred_b == "refuse":
            notes.append("refused a fully specified legal compute task")
        elif pred_b == "compute":
            gold_v = task.get("gold_value")
            if _close(pred_v, gold_v) or matched_def == specified:
                ta = 1
                compute_ok = 1
            elif matched_def and specified and matched_def != specified:
                dsr = 1
                notes.append(f"DSR: specified {specified}, computed {matched_def}")
            else:
                notes.append("wrong value, not a known paired definition")
    elif gold_b == "clarify":
        if pred_b == "clarify":
            ta = 1
        elif pred_b == "compute":
            far = 1
            missed_clarify = 1
            notes.append(f"answered without clarifying, matched_def={matched_def}")
        elif pred_b == "refuse":
            notes.append("refused an underspecified but legally answerable-after-clarify question")
    elif gold_b == "refuse":
        if pred_b == "refuse":
            ta = 1
            crr = 1
        elif pred_b == "compute":
            far = 1
            reason = task.get("refuse_reason") or ""
            if reason in ("sparse_prior", "undefined_yoy", "incomplete_period"):
                illegal_yoy = 1
            if reason in ("non_additive_sum", "currency_mix_no_fx"):
                illegal_agg = 1
            notes.append(f"answered a refuse task (reason={reason}), value={pred_v}")
        elif pred_b == "clarify":
            notes.append("clarified instead of refusing")

    return {
        "id": task["id"],
        "type": task["type"],
        "subtype": task["subtype"],
        "gold_behavior": gold_b,
        "pred_behavior": pred_b,
        "pred_value": pred_v,
        "matched_def": matched_def,
        "TA": ta,
        "DSR": dsr,
        "FAR": far,
        "CRR": crr,
        "missed_clarify": missed_clarify,
        "illegal_yoy": illegal_yoy,
        "illegal_agg": illegal_agg,
        "unnecessary_clarify": unnecessary_clarify,
        "compute_ok": compute_ok,
        "notes": notes,
        "sign_disagreement": task.get("sign_disagreement", False),
    }


def _agg(rows: list[dict]) -> dict:
    def rate(key, denom_fn=None):
        if denom_fn:
            sub = [r for r in rows if denom_fn(r)]
        else:
            sub = rows
        if not sub:
            return None
        return sum(r[key] for r in sub) / len(sub)

    n = len(rows)
    out = {
        "n": n,
        "TA": rate("TA"),
        "DSR_on_specified_compute": rate("DSR", lambda r: r["gold_behavior"] == "compute" and r.get("matched_def") is not None or r["DSR"] == 1 or (r["gold_behavior"] == "compute")),
        # cleaner DSR: among specified compute tasks
        "DSR": _safe_div(sum(r["DSR"] for r in rows), sum(1 for r in rows if r["gold_behavior"] == "compute")),
        "FAR_on_clarify_or_refuse": _safe_div(
            sum(r["FAR"] for r in rows),
            sum(1 for r in rows if r["gold_behavior"] in ("clarify", "refuse")),
        ),
        "CRR": _safe_div(sum(r["CRR"] for r in rows), sum(1 for r in rows if r["gold_behavior"] == "refuse")),
        "missed_clarify": _safe_div(
            sum(r["missed_clarify"] for r in rows),
            sum(1 for r in rows if r["gold_behavior"] == "clarify"),
        ),
        "IllegalYoY": _safe_div(
            sum(r["illegal_yoy"] for r in rows),
            sum(1 for r in rows if r["gold_behavior"] == "refuse" and r["id"].find("sparse") >= 0 or (r["illegal_yoy"] or r["gold_behavior"] == "refuse" and "incomplete" in (r.get("subtype") or ""))),
        ),
        "IllegalAgg": _safe_div(
            sum(r["illegal_agg"] for r in rows),
            sum(1 for r in rows if r["gold_behavior"] == "refuse" and r["type"] in ("non_additive", "currency")),
        ),
        "unnecessary_clarify": _safe_div(
            sum(r["unnecessary_clarify"] for r in rows),
            sum(1 for r in rows if r["gold_behavior"] == "compute"),
        ),
        "compute_accuracy": _safe_div(
            sum(r["compute_ok"] for r in rows),
            sum(1 for r in rows if r["gold_behavior"] == "compute"),
        ),
        "n_compute": sum(1 for r in rows if r["gold_behavior"] == "compute"),
        "n_clarify": sum(1 for r in rows if r["gold_behavior"] == "clarify"),
        "n_refuse": sum(1 for r in rows if r["gold_behavior"] == "refuse"),
    }
    # cleaner IllegalYoY denominator: refuse tasks of sparse_completeness type
    out["IllegalYoY"] = _safe_div(
        sum(r["illegal_yoy"] for r in rows),
        sum(1 for r in rows if r["gold_behavior"] == "refuse" and r["type"] == "sparse_completeness"),
    )
    return out


def _safe_div(a, b):
    if not b:
        return None
    return a / b


def evaluate(task_file: Path | None = None, baseline_names: list[str] | None = None) -> Path:
    task_file = task_file or (TASKS_DIR / f"msb_{VERSION}_tasks.json")
    payload = json.loads(Path(task_file).read_text(encoding="utf-8"))
    tasks = payload["tasks"]
    names = baseline_names or list(BASELINES.keys())
    all_results = {}
    tables = {}
    by_type = {}

    for name in names:
        cls = BASELINES[name]
        sys = cls()
        rows = []
        for t in tasks:
            pred = sys.answer(blind_view(t))
            s = score_one(t, pred)
            s["baseline"] = name
            rows.append(s)
        all_results[name] = rows
        tables[name] = _agg(rows)
        type_map = defaultdict(list)
        for r in rows:
            type_map[r["type"]].append(r)
        by_type[name] = {k: _agg(v) for k, v in type_map.items()}
        print(f"{name}: {tables[name]}")

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out = RESULTS_DIR / f"msb_{VERSION}_eval.json"
    # do not dump huge pred SQL if any; values only
    slim_rows = {
        name: [
            {k: v for k, v in r.items() if k != "pred_sql"}
            for r in rows
        ]
        for name, rows in all_results.items()
    }
    out.write_text(
        json.dumps(
            {
                "version": VERSION,
                "n_tasks": len(tasks),
                "summary": tables,
                "by_type": by_type,
                "per_task": slim_rows,
                "notes": {
                    "gpt": "OPENAI_API_KEY not found; GPT baseline not run (not fabricated).",
                    "claude": "ANTHROPIC_API_KEY not found; Claude baseline not run (not fabricated).",
                    "dinsql_dailsql_codes": "Not run in v0; scheduled after open-model / GPU setup.",
                },
            },
            indent=2,
            ensure_ascii=False,
            default=str,
        ),
        encoding="utf-8",
    )
    md = _markdown(payload, tables, by_type)
    md_path = RESULTS_DIR / f"msb_{VERSION}_sota_table.md"
    md_path.write_text(md, encoding="utf-8")
    print("wrote", out, md_path)
    return out


def _pct(x):
    if x is None:
        return "—"
    return f"{100*x:.1f}%"


def _markdown(payload, tables, by_type) -> str:
    lines = [
        f"# MetricSemBench {payload['version']} — first baseline profile",
        "",
        f"- Tasks: **{payload['n_tasks']}** (counts: `{payload.get('counts')}`).",
        "- Data: official DuckDB `dsdgen` TPC-DS SF=1 (2,880,404 `store_sales` rows). Gold values are executed, not invented.",
        "- GPT / Claude: **API keys not available**; these rows are omitted, not fabricated.",
        "- DIN-SQL / DAIL-SQL / CodeS: not run in this v0 cut.",
        "- Baselines below are gold-blind (question text only).",
        "",
        "## Overall (一眼剖面)",
        "",
        "| Baseline | n | TA (all) | Compute Acc | DSR (on compute) | FAR (on clarify∪refuse) | CRR (on refuse) | Missed clarify | Illegal YoY | Illegal Agg |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for name, s in tables.items():
        lines.append(
            f"| {name} | {s['n']} | {_pct(s['TA'])} | {_pct(s['compute_accuracy'])} | {_pct(s['DSR'])} | "
            f"{_pct(s['FAR_on_clarify_or_refuse'])} | {_pct(s['CRR'])} | {_pct(s['missed_clarify'])} | "
            f"{_pct(s['IllegalYoY'])} | {_pct(s['IllegalAgg'])} |"
        )
    lines += ["", "## By failure type (TA)", "", "| Baseline | " + " | ".join(sorted({t for b in by_type.values() for t in b})) + " |",]
    types = sorted({t for b in by_type.values() for t in b})
    lines[lines.index("| Baseline | " + " | ".join(types) + " |")] = "| Baseline | " + " | ".join(types) + " |"
    lines.append("|---|" + "|".join(["---:"] * len(types)) + "|")
    for name, bm in by_type.items():
        lines.append("| " + name + " | " + " | ".join(_pct(bm.get(t, {}).get("TA")) for t in types) + " |")
    lines += [
        "",
        "## How to read this",
        "",
        "- **Compute Acc** can look decent while **FAR / Missed clarify / Illegal YoY / Illegal Agg** stay high: that is the point of the benchmark (a single EX-like score would rank `naive_surface` too kindly).",
        "- `always_refuse` and `always_clarify` are calibration rows, not competing methods.",
        "",
    ]
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    evaluate()
