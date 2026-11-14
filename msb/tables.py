"""SOTA tables: bold best, underline second, W/T/L vs our method."""
from __future__ import annotations

from typing import Any

HIGHER = {"TA", "compute_accuracy", "CRR"}
LOWER = {
    "FAR_on_clarify_or_refuse",
    "missed_clarify",
    "IllegalYoY",
    "IllegalAgg",
    "DSR",
    "unnecessary_clarify",
}
METRICS = [
    "TA",
    "compute_accuracy",
    "FAR_on_clarify_or_refuse",
    "CRR",
    "missed_clarify",
    "unnecessary_clarify",
    "DSR",
    "IllegalYoY",
    "IllegalAgg",
]
LABEL = {
    "TA": "TA",
    "compute_accuracy": "Compute Acc",
    "FAR_on_clarify_or_refuse": "FAR",
    "CRR": "CRR",
    "missed_clarify": "Missed clarify",
    "unnecessary_clarify": "UCR",
    "DSR": "DSR",
    "IllegalYoY": "Illegal YoY",
    "IllegalAgg": "Illegal Agg",
}


def _pct(x) -> str:
    if x is None:
        return "—"
    return f"{100.0 * float(x):.1f}%"


def _better(metric: str, a, b) -> int:
    """1 if a better than b, 0 if equal, -1 if worse. None is skipped as n/a."""
    if a is None or b is None:
        return 0 if a is None and b is None else 0
    if a == b:
        return 0
    if metric in HIGHER:
        return 1 if a > b else -1
    return 1 if a < b else -1


def compare(ours: dict, other: dict) -> dict:
    wins = ties = losses = n_a = 0
    per = {}
    for m in METRICS:
        a, b = ours.get(m), other.get(m)
        if a is None or b is None:
            per[m] = "n/a"
            n_a += 1
            continue
        r = _better(m, a, b)
        if r == 1:
            per[m] = "win"
            wins += 1
        elif r == -1:
            per[m] = "lose"
            losses += 1
        else:
            per[m] = "tie"
            ties += 1
    per["_wins"], per["_ties"], per["_losses"], per["_na"] = wins, ties, losses, n_a
    return per


def _rank_values(summaries: dict, metric: str) -> tuple[float | None, float | None]:
    """Return (best, second) raw values, considering direction. Ties share best."""
    vals = []
    for s in summaries.values():
        if s and s.get(metric) is not None:
            vals.append(float(s[metric]))
    if not vals:
        return None, None
    if metric in HIGHER:
        uniq = sorted(set(vals), reverse=True)
    else:
        uniq = sorted(set(vals))
    best = uniq[0]
    second = uniq[1] if len(uniq) > 1 else None
    return best, second


def _fmt_cell(val, best, second, tol=1e-12) -> str:
    if val is None:
        return "—"
    text = _pct(val)
    if best is not None and abs(val - best) <= tol:
        return f"**{text}**"
    if second is not None and abs(val - second) <= tol:
        return f"<u>{text}</u>"
    return text


def md_sota(
    summaries: dict,
    title: str,
    ours: str,
    extra_lines: list[str] | None = None,
    order: list[str] | None = None,
) -> str:
    names = order or ([ours] + [k for k in summaries if k != ours])
    names = [n for n in names if summaries.get(n)]
    best = {m: _rank_values(summaries, m)[0] for m in METRICS}
    second = {m: _rank_values(summaries, m)[1] for m in METRICS}

    lines = [
        f"# {title}",
        "",
        *(extra_lines or []),
        "",
        "Best per column is **bold**, second is <u>underlined</u> (ties share the mark). "
        "Higher is better for TA / Compute Acc / CRR; lower is better for FAR / Missed clarify / UCR / DSR / Illegal*. "
        "The W/T/L column and the last row count wins–ties–losses of **our method vs that system** (or, in the last row, the column-wise best-count is not used; see W/T/L row).",
        "",
        "| System | n | " + " | ".join(LABEL[m] for m in METRICS) + " | W/T/L vs " + ours + " |",
        "|---|---:|" + "|".join(["---:"] * len(METRICS)) + "|---:|",
    ]
    ours_s = summaries.get(ours) or {}
    wtl_wins = wtl_ties = wtl_losses = 0
    for name in names:
        s = summaries[name]
        cells = [_fmt_cell(s.get(m), best[m], second[m]) for m in METRICS]
        if name == ours:
            wtl = "—"
        else:
            c = compare(ours_s, s)
            wtl = f"{c['_wins']}–{c['_ties']}–{c['_losses']}"
            wtl_wins += c["_wins"]
            wtl_ties += c["_ties"]
            wtl_losses += c["_losses"]
        lines.append(f"| {name} | {s.get('n','')} | " + " | ".join(cells) + f" | {wtl} |")

    # W/T/L count row: aggregate vs all other systems
    n_other = sum(1 for n in names if n != ours)
    lines.append(
        f"| **W/T/L total** (vs {n_other} systems) | — | "
        + " | ".join("—" for _ in METRICS)
        + f" | **{wtl_wins}–{wtl_ties}–{wtl_losses}** |"
    )
    # Per-metric W/T/L vs each system counted already; also a per-metric best identity note is optional.
    return "\n".join(lines) + "\n"


def md_winlose(summaries: dict, title: str, ours: str, explanations: str | None = None) -> str:
    ours_s = summaries[ours]
    lines = [
        f"# {title}",
        "",
        f"Our method: `{ours}`. Win = strictly better (higher TA/Compute Acc/CRR; lower FAR/Missed clarify/UCR/DSR/Illegal*). Tie = equal. Lose = strictly worse. n/a = undefined (empty denominator).",
        "",
        "| Baseline | " + " | ".join(LABEL[m] for m in METRICS) + " | W | T | L |",
        "|---|" + "|".join(["---"] * len(METRICS)) + "|---:|---:|---:|",
    ]
    tw = tt = tl = 0
    losses_detail = []
    for name, s in summaries.items():
        if name == ours or not s:
            continue
        c = compare(ours_s, s)
        cells = " | ".join(c[m] for m in METRICS)
        lines.append(f"| {name} | {cells} | {c['_wins']} | {c['_ties']} | {c['_losses']} |")
        tw += c["_wins"]
        tt += c["_ties"]
        tl += c["_losses"]
        for m in METRICS:
            if c[m] == "lose":
                losses_detail.append(
                    f"- **Lose `{LABEL[m]}` vs `{name}`**: ours={_pct(ours_s.get(m))} vs {_pct(s.get(m))}."
                )
    lines.append(f"| **W/T/L total** | " + " | ".join("—" for _ in METRICS) + f" | **{tw}** | **{tt}** | **{tl}** |")
    lines += ["", "## Where a baseline wins (precise explanation)", ""]
    if explanations:
        lines.append(explanations)
    elif losses_detail:
        lines.extend(losses_detail)
    else:
        lines.append(
            "No baseline strictly wins any reported metric against our method on this set. "
            "Ties are at the ceiling or floor (e.g. DSR=0), or vs a previous in-family binder on the templates it was fitted to."
        )
    return "\n".join(lines) + "\n"
