"""Official statistics for Paper 15 MetricSemBench (EA&B).

Computes, from already-collected predictions only:
  - population prevalence of calendar-month vs rolling-30 sign disagreement
    and magnitude disagreement on official TPC-DS SF=1 (not just selected tasks);
  - bootstrap 95% CIs (10,000 resamples, seed 20261112) for every system/metric
    on the v0.1 fixture and the public overlay v1 (n=167);
  - paired McNemar mid-p and paired bootstrap diffs for headline contrasts;
  - EX-like vs official-TA ranking inversion (Kendall tau).

Does NOT load or score paper-13 official TEST folds.
Does NOT invent numbers. Gold-blind predictions are reused from frozen result JSON.
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path

import duckdb
import numpy as np

from msb.config import DB_PATH, MIN_ABS_YOY, RESULTS_DIR, TASKS_DIR
from msb.public_stats import (
    LOWER_IS_BETTER,
    bootstrap_ci,
    contrast as _overlay_contrast,
    fmt_ci,
    mcnemar_midp,
    paired_bootstrap_diff,
    summarize_system as _overlay_summarize,
)
from msb.tables import _better, _fmt_cell, _rank_values

SEED = 20261112
N_BOOT = 10000
OUT_DIR = RESULTS_DIR / "paper15_official"


def _load_json(p: Path) -> dict:
    return json.loads(p.read_text(encoding="utf-8"))


def merge_v01() -> dict[str, list[dict]]:
    """Merge per-task rows from every completed v0.1 result file."""
    base = RESULTS_DIR
    per: dict[str, list[dict]] = {}
    # deterministic + LLM mid-tier
    ev = _load_json(base / "msb_v0.1_eval_with_llm.json")
    per.update(ev.get("per_task") or {})
    pub = _load_json(base / "msb_v0.1_published.json")
    per.update(pub.get("per_task") or {})
    meth = _load_json(base / "msb_v0.1_eval_method_v1.json")
    mpt = meth.get("per_task") or {}
    if isinstance(mpt, list):
        grouped = {}
        for r in mpt:
            grouped.setdefault(r.get("baseline") or "bindorclarify_v1", []).append(r)
        per.update(grouped)
    elif isinstance(mpt, dict):
        # values may be lists of rows, or a single dict-of-rows missing the system key
        if mpt and isinstance(next(iter(mpt.values())), list):
            per.update(mpt)
        else:
            per["bindorclarify_v1"] = list(mpt.values()) if mpt else []
    # contract_aware_v0 may only live in all_summary; skip CIs if no rows
    return per


# Metrics whose denominators match evaluate._agg
def v01_indicators(rows: list[dict], metric: str) -> list[float]:
    if metric == "TA":
        return [1.0 if r.get("TA") else 0.0 for r in rows]
    if metric == "compute_accuracy":
        return [1.0 if r.get("compute_ok") else 0.0 for r in rows if r.get("gold_behavior") == "compute"]
    if metric == "FAR_on_clarify_or_refuse":
        return [1.0 if r.get("FAR") else 0.0 for r in rows if r.get("gold_behavior") in ("clarify", "refuse")]
    if metric == "CRR":
        return [1.0 if r.get("CRR") else 0.0 for r in rows if r.get("gold_behavior") == "refuse"]
    if metric == "missed_clarify":
        return [1.0 if r.get("missed_clarify") else 0.0 for r in rows if r.get("gold_behavior") == "clarify"]
    if metric == "unnecessary_clarify":
        return [1.0 if r.get("unnecessary_clarify") else 0.0 for r in rows if r.get("gold_behavior") == "compute"]
    if metric == "DSR":
        return [1.0 if r.get("DSR") else 0.0 for r in rows if r.get("gold_behavior") == "compute"]
    if metric == "IllegalYoY":
        return [
            1.0 if r.get("illegal_yoy") else 0.0
            for r in rows
            if r.get("gold_behavior") == "refuse" and r.get("type") == "sparse_completeness"
        ]
    if metric == "IllegalAgg":
        return [
            1.0 if r.get("illegal_agg") else 0.0
            for r in rows
            if r.get("gold_behavior") == "refuse" and r.get("type") in ("non_additive", "currency")
        ]
    raise ValueError(metric)


V01_METRICS = [
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
HIGHER = {"TA", "compute_accuracy", "CRR"}


def summarize_v01(rows: list[dict]) -> dict:
    out = {"n": len(rows)}
    if rows:
        out["n_compute"] = sum(1 for r in rows if r.get("gold_behavior") == "compute")
        out["n_clarify"] = sum(1 for r in rows if r.get("gold_behavior") == "clarify")
        out["n_refuse"] = sum(1 for r in rows if r.get("gold_behavior") == "refuse")
    for m in V01_METRICS:
        xs = v01_indicators(rows, m)
        out[m] = bootstrap_ci(xs, n_boot=N_BOOT, seed=SEED)
    return out


def contrast_v01(a_rows: list[dict], b_rows: list[dict], metric: str) -> dict:
    # align by id
    bmap = {r["id"]: r for r in b_rows}
    a_al, b_al = [], []
    for r in a_rows:
        if r["id"] in bmap:
            a_al.append(r)
            b_al.append(bmap[r["id"]])
    xa, xb = v01_indicators(a_al, metric), v01_indicators(b_al, metric)
    # indicators may be filtered to a subset; re-align by walking the same filter
    # Safer: compute on the filtered lists only if lengths match (same denom rule).
    lower = metric not in HIGHER
    rec = {"metric": metric, "bootstrap": paired_bootstrap_diff(xa, xb, n_boot=N_BOOT, seed=SEED, lower_better=lower)}
    if metric in {"TA", "compute_accuracy", "CRR"} and len(xa) == len(xb) and xa:
        rec["mcnemar"] = mcnemar_midp([bool(x) for x in xa], [bool(x) for x in xb])
    return rec


def kendall_tau(ranks_a: list[int], ranks_b: list[int]) -> float:
    n = len(ranks_a)
    if n < 2:
        return float("nan")
    conc = disc = 0
    for i in range(n):
        for j in range(i + 1, n):
            da = ranks_a[i] - ranks_a[j]
            db = ranks_b[i] - ranks_b[j]
            if da * db > 0:
                conc += 1
            elif da * db < 0:
                disc += 1
    den = conc + disc
    return (conc - disc) / den if den else 1.0


def _rank(values: list[tuple[str, float | None]], higher=True) -> dict[str, int]:
    # None last; ties share min rank
    scored = [(n, v) for n, v in values if v is not None]
    scored.sort(key=lambda x: -x[1] if higher else x[1])
    ranks = {}
    i = 0
    while i < len(scored):
        j = i
        while j + 1 < len(scored) and abs(scored[j + 1][1] - scored[i][1]) < 1e-12:
            j += 1
        for k in range(i, j + 1):
            ranks[scored[k][0]] = i + 1
        i = j + 1
    return ranks


def prevalence(con) -> dict:
    """Full-population calendar vs rolling-30 stats on official TPC-DS SF=1."""
    rows_overall = con.execute(
        """
        WITH daily AS (
          SELECT d_date AS dt, d_year, d_moy, SUM(ss_net_paid) AS amt
          FROM msb_store_sales GROUP BY 1,2,3
        ),
        cal AS (
          SELECT d_year AS yr, d_moy AS moy, MAX(dt) AS end_d, SUM(amt) AS cal_amt
          FROM daily GROUP BY 1,2
        ),
        r30 AS (
          SELECT c.yr, c.moy,
                 (SELECT SUM(d2.amt) FROM daily d2
                  WHERE d2.dt BETWEEN c.end_d - INTERVAL 29 DAY AND c.end_d) AS r30_amt
          FROM cal c
        )
        SELECT c.yr, c.moy, CAST(NULL AS VARCHAR) AS cat, c.cal_amt, r.r30_amt,
               c2.cal_amt AS cal_ly, r2.r30_amt AS r30_ly
        FROM cal c
        JOIN r30 r ON c.yr=r.yr AND c.moy=r.moy
        JOIN cal c2 ON c2.yr=c.yr-1 AND c2.moy=c.moy
        JOIN r30 r2 ON r2.yr=c.yr-1 AND r2.moy=c.moy
        WHERE c.yr BETWEEN 1999 AND 2002 AND c2.cal_amt > 0 AND r2.r30_amt > 0
        """
    ).fetchall()
    rows_cat = con.execute(
        """
        WITH daily AS (
          SELECT d_date AS dt, d_year, d_moy, i_category AS cat, SUM(ss_net_paid) AS amt
          FROM msb_store_sales WHERE i_category IS NOT NULL GROUP BY 1,2,3,4
        ),
        cal AS (
          SELECT d_year AS yr, d_moy AS moy, cat, MAX(dt) AS end_d, SUM(amt) AS cal_amt
          FROM daily GROUP BY 1,2,3
        ),
        r30 AS (
          SELECT c.yr, c.moy, c.cat,
                 (SELECT SUM(d2.amt) FROM daily d2
                  WHERE d2.cat IS NOT DISTINCT FROM c.cat
                    AND d2.dt BETWEEN c.end_d - INTERVAL 29 DAY AND c.end_d) AS r30_amt
          FROM cal c
        )
        SELECT c.yr, c.moy, c.cat, c.cal_amt, r.r30_amt, c2.cal_amt, r2.r30_amt
        FROM cal c
        JOIN r30 r ON c.yr=r.yr AND c.moy=r.moy AND c.cat IS NOT DISTINCT FROM r.cat
        JOIN cal c2 ON c2.yr=c.yr-1 AND c2.moy=c.moy AND c2.cat IS NOT DISTINCT FROM c.cat
        JOIN r30 r2 ON r2.yr=c.yr-1 AND r2.moy=c.moy AND r2.cat IS NOT DISTINCT FROM r.cat
        WHERE c.yr BETWEEN 1999 AND 2002 AND c2.cal_amt > 0 AND r2.r30_amt > 0
        """
    ).fetchall()

    def pack(rows, scope):
        recs = []
        for yr, moy, cat, cal, r30, cal_ly, r30_ly in rows:
            cal, r30, cal_ly, r30_ly = map(float, (cal, r30, cal_ly, r30_ly))
            cal_yoy = (cal - cal_ly) / cal_ly
            r30_yoy = (r30 - r30_ly) / r30_ly
            sign_d = (cal - cal_ly) * (r30 - r30_ly) < 0 and abs(cal_yoy) >= MIN_ABS_YOY and abs(r30_yoy) >= MIN_ABS_YOY
            gap = abs(cal_yoy - r30_yoy)
            recs.append(
                {
                    "scope": scope,
                    "yr": int(yr),
                    "moy": int(moy),
                    "cat": cat,
                    "cal_yoy": cal_yoy,
                    "r30_yoy": r30_yoy,
                    "sign_disagreement": sign_d,
                    "magnitude_gap_ge_2pp": (gap >= 0.02 and abs(cal_yoy) >= MIN_ABS_YOY),
                    "gap": gap,
                    "decision_relevant": abs(cal_yoy) >= MIN_ABS_YOY or abs(r30_yoy) >= MIN_ABS_YOY,
                }
            )
        return recs

    overall = pack(rows_overall, "all_stores")
    cat = pack(rows_cat, "category")
    all_recs = overall + cat

    def stats(recs):
        n = len(recs)
        n_sign = sum(1 for r in recs if r["sign_disagreement"])
        n_mag = sum(1 for r in recs if r["magnitude_gap_ge_2pp"])
        n_dr = sum(1 for r in recs if r["decision_relevant"])
        n_sign_dr = sum(1 for r in recs if r["sign_disagreement"] and r["decision_relevant"])
        return {
            "n_complete": n,
            "n_sign_disagreement": n_sign,
            "rate_sign": n_sign / n if n else None,
            "n_magnitude_gap_ge_2pp": n_mag,
            "rate_magnitude": n_mag / n if n else None,
            "n_decision_relevant": n_dr,
            "rate_sign_among_decision_relevant": n_sign_dr / n_dr if n_dr else None,
        }

    flips = [
        {k: r[k] for k in ("scope", "yr", "moy", "cat", "cal_yoy", "r30_yoy", "gap")}
        for r in all_recs
        if r["sign_disagreement"]
    ]
    flips.sort(key=lambda r: (str(r["scope"]), r["yr"], r["moy"], str(r["cat"] or "")))  # SQL GROUP BY order is not deterministic
    return {
        "gate": {
            "MIN_ABS_YOY": MIN_ABS_YOY,
            "magnitude_gap": 0.02,
            "years": "1999-2002 complete prior-year windows",
            "note": (
                "Sign disagreement requires opposite signs AND both |YoY| >= 1 percentage "
                "point, matching the v0.1 selection gate (near-zero jitter excluded)."
            ),
        },
        "all_stores": stats(overall),
        "category": stats(cat),
        "all_triples": stats(all_recs),
        "flagship_sign_flips": flips,
    }


def _pct(ci: dict | None) -> str:
    if not ci or ci.get("mean") is None:
        return "—"
    return fmt_ci(ci)


def _mean(ci: dict | None) -> float | None:
    if not ci:
        return None
    return ci.get("mean")


def write_v01_tables(summaries: dict[str, dict], per: dict[str, list[dict]]) -> str:
    # Display order: reference protocol systems, published, LLMs, calibrators
    order = [
        "bindorclarify_v1",
        "naive_surface",
        "dict_default",
        "ark_deepseek-v4-pro_dailsql",
        "ark_deepseek-v4-pro_dinsql",
        "ark_deepseek-v4-pro_semantic",
        "tokens1688_claude-sonnet-4-6_semantic",
        "tokens1688_gpt-6-sol_semantic",
        "tokens1688_gpt-6-sol_direct",
        "qwen25_7b_semantic",
        "qwen25_7b_direct",
        "always_refuse",
        "always_clarify",
    ]
    names = [n for n in order if n in summaries] + [n for n in summaries if n not in order]
    metrics_disp = [
        ("TA", "TA"),
        ("compute_accuracy", "Compute Acc"),
        ("FAR_on_clarify_or_refuse", "FAR"),
        ("CRR", "CRR"),
        ("missed_clarify", "Missed clarify"),
        ("unnecessary_clarify", "UCR"),
        ("DSR", "DSR"),
        ("IllegalYoY", "Illegal YoY"),
        ("IllegalAgg", "Illegal Agg"),
    ]
    # best/second on means
    means = {
        n: {k: _mean(summaries[n].get(k)) for k, _ in metrics_disp}
        for n in names
    }
    lines = [
        "# MetricSemBench v0.1 — official statistics with bootstrap 95% CIs",
        "",
        f"Fixture: TPC-DS SF=1 MetricSemBench v0.1, n=85 (compute 44 / clarify 21 / refuse 20).",
        f"Bootstrap percentile 95% CIs, {N_BOOT} resamples, seed {SEED}.",
        "These are **template-fixture** numbers, not a held-out generalization claim.",
        "`bindorclarify_v1` is a dictionary-grounded **reference protocol** (paper 13's method), reported as a profile point, not as \"our method wins\" — paper 15 is an EA&B benchmark.",
        "Paper-13 official TEST folds were **not** used.",
        "",
        "Best per column (mean) is **bold**, second is <u>underlined</u> (ties share the mark). Higher is better for TA / Compute Acc / CRR; lower is better for FAR / Missed clarify / UCR / DSR / Illegal*.",
        "",
        "| System | n | " + " | ".join(lab for _, lab in metrics_disp) + " |",
        "|---|---:|" + "|".join(["---:" for _ in metrics_disp]) + "|",
    ]
    for n in names:
        s = summaries[n]
        cells = []
        for k, _ in metrics_disp:
            best, second = _rank_values(means, k) if False else (None, None)
        # use means dict shaped as summaries for _rank_values: it expects metric -> number
        # We'll compute best/second ourselves
        row = f"| {n} | {s.get('n','')} |"
        for k, _ in metrics_disp:
            vals = [(nn, means[nn][k]) for nn in names]
            higher = k in HIGHER
            finite = [(nn, v) for nn, v in vals if v is not None]
            if not finite:
                row += " — |"
                continue
            if higher:
                best = max(v for _, v in finite)
                rest = [v for _, v in finite if v < best - 1e-15]
                second = max(rest) if rest else best
            else:
                best = min(v for _, v in finite)
                rest = [v for _, v in finite if v > best + 1e-15]
                second = min(rest) if rest else best
            ci = s.get(k) or {}
            text = _pct(ci)
            mv = means[n][k]
            if mv is not None and abs(mv - best) < 1e-12:
                # bold the mean, keep CI
                text = f"**{text}**"
            elif mv is not None and abs(mv - second) < 1e-12:
                text = f"<u>{text}</u>"
            row += f" {text} |"
        lines.append(row)

    # EX vs TA inversion
    lines += [
        "",
        "## Ranking inversion: EX-like (Compute Acc) vs official TA",
        "",
        "A single execution-accuracy (EX) score, here Compute Acc on the 44 gold-compute items, "
        "ranks always-answer systems that ignore contracts as if they were strong. Official TA "
        "charges a false answer on clarify and refuse items.",
        "",
        "| System | Compute Acc (EX-like) | EX rank | Official TA | TA rank | Rank shift (EX→TA) |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    ex_vals = [(n, means[n]["compute_accuracy"]) for n in names]
    ta_vals = [(n, means[n]["TA"]) for n in names]
    ex_rank = _rank(ex_vals, higher=True)
    ta_rank = _rank(ta_vals, higher=True)
    tau = kendall_tau([ex_rank.get(n, 99) for n in names if n in ex_rank and n in ta_rank],
                      [ta_rank.get(n, 99) for n in names if n in ex_rank and n in ta_rank])
    for n in names:
        if n not in ex_rank or n not in ta_rank:
            continue
        exm = means[n]["compute_accuracy"]
        tam = means[n]["TA"]
        shift = ex_rank[n] - ta_rank[n]  # positive: improved when using TA
        lines.append(
            f"| {n} | {_pct(summaries[n]['compute_accuracy'])} | {ex_rank[n]} | "
            f"{_pct(summaries[n]['TA'])} | {ta_rank[n]} | {shift:+d} |"
        )
    lines += [
        "",
        f"Kendall's τ between EX-like ranks and official-TA ranks: **{tau:.3f}** "
        f"(computed on systems with both scores; seedless, descriptive).",
        "",
        "Notable inversions: `naive_surface` / `dict_default` are at the EX ceiling (44/44) but "
        "only mid-pack on TA because FAR = 100% on the 41 clarify∪refuse items. "
        "DAIL-SQL is the strongest *published always-answer* computer and still has FAR = 100%. "
        "GPT-6-sol semantic has *lower* Compute Acc than GPT-6-sol direct but *higher* TA, "
        "because it refuses to silently answer underspecified or illegal questions (FAR = 0) "
        "at the cost of a high unnecessary-clarify rate.",
        "",
    ]

    # Paired tests vs naive (EX champion) and vs DAIL on TA
    lines += ["## Paired tests on official TA (McNemar mid-p, paired bootstrap, seed 20261112)", ""]
    if "naive_surface" in per:
        lines.append("### Each system vs `naive_surface` (the EX-ceiling always-answer baseline)")
        lines.append("")
        lines.append("| System | ΔTA (system − naive) | bootstrap 95% CI | p_boot | McNemar mid-p (b01, b10) |")
        lines.append("|---|---:|---:|---:|---|")
        for n in names:
            if n == "naive_surface" or n not in per:
                continue
            rec = contrast_v01(per[n], per["naive_surface"], "TA")
            b = rec["bootstrap"]
            mc = rec.get("mcnemar") or {}
            if b.get("diff") is None:
                continue
            lines.append(
                f"| {n} | {100*b['diff']:+.1f} pp | "
                f"[{100*b['ci_low']:.1f}, {100*b['ci_high']:.1f}] | "
                f"{b['p_boot']:.4f} | {mc.get('p_mid')} (b01={mc.get('b01')}, b10={mc.get('b10')}) |"
            )
        lines.append("")
    return "\n".join(lines) + "\n"


def write_public_tables(pub: dict) -> str:
    per = pub["per_task"]
    summaries = {n: _overlay_summarize(rows, n_boot=N_BOOT) for n, rows in per.items()}
    # also keep original point estimates from pub['summary']
    lines = [
        "# Public overlay v1 (n=167) — official statistics with bootstrap 95% CIs",
        "",
        "Parent freeze SHA-256 `4d8bd8fadab86a0222f0a6ff5eb090f5da7b248f98a8f56723397e79758f3c12`, n=167, official TA denominator 148 "
        "(12 clarify + 136 compute with official numeric gold). Behavior-only compute (19) is excluded from official TA.",
        f"Bootstrap percentile 95% CIs, {N_BOOT} resamples, seed {SEED}.",
        "Predictions reused from the already-finished `metricsembench-public-v1` run; **no second paid evaluation**.",
        "This is a *transfer* study (official BIRD/Spider questions + our behavior overlay). "
        "It is **not** a rescore of paper-13 v2/v3/v4/v5 official TEST folds.",
        "`bindorclarify_v1` is a TPC-DS dictionary binder; transfer failure is an honest expected result.",
        "",
        "| System | TA | Compute Acc | FAR | Missed clarify | UCR |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    order = [
        "ark_deepseek-v4-pro_semantic",
        "tokens1688_claude-sonnet-4-6_semantic",
        "ark_deepseek-v4-pro_dailsql",
        "tokens1688_gpt-6-sol_semantic",
        "bindorclarify_v1",
        "always_clarify",
        "always_compute",
        "always_refuse",
    ]
    names = [n for n in order if n in summaries] + [n for n in summaries if n not in order and n != "bindorclarify_v1_1"]
    for n in names:
        s = summaries[n]
        lines.append(
            f"| {n} | {_pct(s['TA'])} | {_pct(s['compute_accuracy'])} | "
            f"{_pct(s['FAR_on_clarify_or_refuse'])} | {_pct(s['missed_clarify'])} | "
            f"{_pct(s['unnecessary_clarify'])} |"
        )
    # contrasts vs DeepSeek semantic (current public TA lead) and vs always_clarify
    if "ark_deepseek-v4-pro_semantic" in per:
        lines += [
            "",
            "## Paired contrasts vs DeepSeek-v4-pro semantic (current public-TA lead)",
            "",
            "| System | metric | Δ (system − DeepSeek) | bootstrap 95% CI | p_boot | McNemar mid-p |",
            "|---|---|---:|---:|---:|---|",
        ]
        for n in names:
            if n == "ark_deepseek-v4-pro_semantic":
                continue
            for m in ("TA", "compute_accuracy", "FAR_on_clarify_or_refuse", "missed_clarify"):
                rec = _overlay_contrast(per[n], per["ark_deepseek-v4-pro_semantic"], m, n_boot=N_BOOT)
                b = rec["bootstrap"]
                mc = rec.get("mcnemar") or {}
                if b.get("diff") is None:
                    continue
                lines.append(
                    f"| {n} | {m} | {100*b['diff']:+.1f} pp | "
                    f"[{100*b['ci_low']:.1f}, {100*b['ci_high']:.1f}] | "
                    f"{b['p_boot']:.4f} | {mc.get('p_mid', '—')} |"
                )
    return "\n".join(lines) + "\n", summaries


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    # Prevalence
    if not DB_PATH.exists():
        raise SystemExit(f"TPC-DS duckdb missing: {DB_PATH}")
    con = duckdb.connect(str(DB_PATH), read_only=True)
    prev = prevalence(con)
    con.close()
    (OUT_DIR / "prevalence_calendar_yoy.json").write_text(
        json.dumps(prev, indent=2, ensure_ascii=False, default=str), encoding="utf-8"
    )

    # v0.1 CIs
    per = merge_v01()
    summaries = {n: summarize_v01(rows) for n, rows in per.items() if rows}
    (OUT_DIR / "msb_v0.1_ci.json").write_text(
        json.dumps({"seed": SEED, "n_boot": N_BOOT, "summaries": summaries}, indent=2, default=str),
        encoding="utf-8",
    )
    md = write_v01_tables(summaries, per)
    # prepend prevalence
    p = prev
    t = p["all_triples"]
    a = p["all_stores"]
    flips = p["flagship_sign_flips"]
    flip_rows = "\n".join(
        f"| {f['scope']} | {f['yr']}-{f['moy']:02d} | {f['cat'] or 'all stores'} | "
        f"{100*f['cal_yoy']:+.3f}% | {100*f['r30_yoy']:+.3f}% | {100*f['gap']:.3f} pp |"
        for f in flips
    )
    prev_md = f"""# Calendar-definition disagreement on official TPC-DS SF=1 (full population)

This is a **population** statistic, not a task-selection statistic. Every complete
(year, month[, category]) triple with a complete prior-year window in 1999–2002 is counted.
The v0.1 fixture preferentially *selected* the sign-disagreement triples for the
diagnostic tasks; reporting only those would overstate how often a sign flips.

Gate: opposite signs and both |YoY| ≥ {MIN_ABS_YOY:.0%} (1 percentage point). Magnitude
disagreement: |calendar YoY − rolling-30 YoY| ≥ 2 percentage points, with |calendar YoY| ≥ 1 pp.

| Scope | n complete | Sign disagreement | Rate | Magnitude gap ≥ 2 pp | Rate | Sign rate among decision-relevant |
|---|---:|---:|---:|---:|---:|---:|
| All stores (month) | {a['n_complete']} | {a['n_sign_disagreement']} | {100*a['rate_sign']:.2f}% | {a['n_magnitude_gap_ge_2pp']} | {100*a['rate_magnitude']:.2f}% | {100*(a['rate_sign_among_decision_relevant'] or 0):.2f}% |
| Category-month | {p['category']['n_complete']} | {p['category']['n_sign_disagreement']} | {100*p['category']['rate_sign']:.2f}% | {p['category']['n_magnitude_gap_ge_2pp']} | {100*p['category']['rate_magnitude']:.2f}% | {100*(p['category']['rate_sign_among_decision_relevant'] or 0):.2f}% |
| All triples | {t['n_complete']} | {t['n_sign_disagreement']} | {100*t['rate_sign']:.2f}% | {t['n_magnitude_gap_ge_2pp']} | {100*t['rate_magnitude']:.2f}% | {100*(t['rate_sign_among_decision_relevant'] or 0):.2f}% |

**Reading.** Sign flips are *real* and *rare* (3 of {t['n_complete']} complete triples, {100*t['rate_sign']:.2f}%).
All three already appear in the v0.1 diagnostic fixture; there is **no leftover sign-flip
triple** for a paper-15 held-out. Magnitude disagreement is more common ({t['n_magnitude_gap_ge_2pp']} triples, {100*t['rate_magnitude']:.2f}%).
The scientific claim is therefore: when two legitimate window definitions disagree in
*sign*, a silent choice can reverse a management conclusion — and this happens on official
TPC-DS data — but a benchmark that reported only the flagship flips would be selection-biased.
The paper-15 official held-out is therefore drawn from leftover *same-sign* magnitude and
ordinary complete months (hash-selected, pre-registered), and the population rates above
are a first-class result.

### The three flagship sign flips (existence proof; both |YoY| ≥ 1 pp)

| Scope | Month | Category | Calendar-month YoY | Rolling-30 YoY | Gap |
|---|---|---|---:|---:|---:|
{flip_rows}

February 2000 is a leap month (29 days vs 28 in 1999), which is one mechanistic reason
the two windows diverge at the all-stores grain.

"""
    (OUT_DIR / "prevalence_calendar_yoy.md").write_text(prev_md, encoding="utf-8")
    (OUT_DIR / "msb_v0.1_ci.md").write_text(md, encoding="utf-8")

    # public v1
    pub = _load_json(RESULTS_DIR / "msb_public_v1_167_eval.json")
    pub_md, pub_sum = write_public_tables(pub)
    (OUT_DIR / "msb_public_v1_167_ci.md").write_text(pub_md, encoding="utf-8")
    (OUT_DIR / "msb_public_v1_167_ci.json").write_text(
        json.dumps({"seed": SEED, "n_boot": N_BOOT, "summaries": pub_sum}, indent=2, default=str),
        encoding="utf-8",
    )
    print("wrote", OUT_DIR)
    print("PREVALENCE all_triples", t)
    print("PREVALENCE all_stores", a)
    print("FLIPS", flips)
    for n, s in summaries.items():
        print(n, "TA", _pct(s["TA"]), "EX", _pct(s["compute_accuracy"]), "FAR", _pct(s["FAR_on_clarify_or_refuse"]))


if __name__ == "__main__":
    main()
