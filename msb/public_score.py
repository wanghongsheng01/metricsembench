"""Scoring for the public BIRD/Spider metric-ambiguity overlay.

Two clearly labelled tracks:
  - numeric: compute items with an official-SQL gold value (BIRD Mini-Dev SQLite exec).
    TA requires the number; Compute Acc is defined.
  - behavior_only: no numeric gold (Spider compute, or DBs unavailable). These are
    EXCLUDED from official TA and Compute Acc so always-answer systems cannot
    inflate TA by emitting any number. We still report behavior_match separately.
Clarify / refuse items are behavior-scored and included in official TA.
"""
from __future__ import annotations

from msb.evaluate import _close, _safe_div


def track(task: dict) -> str:
    if task.get("gold_behavior") == "compute" and task.get("gold_value") is None:
        return "behavior_only"
    return "numeric_or_behavior"  # compute+value, or clarify/refuse


def score_public(task: dict, pred: dict) -> dict:
    gold_b = task["gold_behavior"]
    pred_b = pred.get("behavior")
    pred_v = pred.get("value")
    tr = track(task)
    ta = 0
    far = missed = crr = ucr = compute_ok = 0
    notes = []
    behavior_match = int(pred_b == gold_b)

    if gold_b == "compute":
        if pred_b == "clarify":
            ucr = 1
            notes.append("clarified a fully specified compute task")
        elif pred_b == "refuse":
            notes.append("refused a fully specified compute task")
        elif pred_b == "compute":
            if tr == "behavior_only":
                notes.append("behavior-only compute: value not scored (no official numeric gold)")
            else:
                if _close(pred_v, task.get("gold_value")):
                    ta = 1
                    compute_ok = 1
                else:
                    notes.append(f"wrong or missing value (pred={pred_v})")
    elif gold_b == "clarify":
        if pred_b == "clarify":
            ta = 1
        elif pred_b == "compute":
            far = 1
            missed = 1
            notes.append("answered without clarifying")
        else:
            notes.append("refused a clarify item")
    elif gold_b == "refuse":
        if pred_b == "refuse":
            ta = 1
            crr = 1
        elif pred_b == "compute":
            far = 1
            notes.append("answered a refuse item")
        else:
            notes.append("clarified instead of refusing")

    return {
        "id": task["id"],
        "source": task.get("source"),
        "gold_behavior": gold_b,
        "pred_behavior": pred_b,
        "pred_value": pred_v,
        "gold_value": task.get("gold_value"),
        "track": tr,
        "TA": ta,  # official: 0 on behavior_only compute even if behavior matches
        "in_official_ta": tr != "behavior_only",
        "behavior_match": behavior_match,
        "FAR": far,
        "CRR": crr,
        "missed_clarify": missed,
        "unnecessary_clarify": ucr,
        "compute_ok": compute_ok,
        "notes": notes,
        "cost_usd": pred.get("cost_usd"),
        "error": pred.get("error"),
        "sql": (pred.get("sql") or "")[:400],
    }


def agg_public(rows: list[dict]) -> dict:
    official = [r for r in rows if r.get("in_official_ta")]
    numeric_compute = [r for r in rows if r["gold_behavior"] == "compute" and r["track"] != "behavior_only"]
    behavior_compute = [r for r in rows if r["gold_behavior"] == "compute" and r["track"] == "behavior_only"]
    clarify = [r for r in rows if r["gold_behavior"] == "clarify"]
    refuse = [r for r in rows if r["gold_behavior"] == "refuse"]
    return {
        "n": len(rows),
        "n_official_ta": len(official),
        "n_compute_numeric": len(numeric_compute),
        "n_compute_behavior_only": len(behavior_compute),
        "n_clarify": len(clarify),
        "n_refuse": len(refuse),
        "TA": _safe_div(sum(r["TA"] for r in official), len(official)),  # official track
        "behavior_match_all": _safe_div(sum(r["behavior_match"] for r in rows), len(rows)),
        "compute_accuracy": _safe_div(sum(r["compute_ok"] for r in numeric_compute), len(numeric_compute)),
        "FAR_on_clarify_or_refuse": _safe_div(sum(r["FAR"] for r in rows), len(clarify) + len(refuse)),
        "CRR": _safe_div(sum(r["CRR"] for r in refuse), len(refuse)),
        "missed_clarify": _safe_div(sum(r["missed_clarify"] for r in clarify), len(clarify)),
        "unnecessary_clarify": _safe_div(sum(r["unnecessary_clarify"] for r in rows if r["gold_behavior"] == "compute"),
                                        sum(1 for r in rows if r["gold_behavior"] == "compute")),
        # DSR / Illegal* not defined on this overlay (no paired defs / refuse slice)
        "DSR": None,
        "IllegalYoY": None,
        "IllegalAgg": None,
    }
