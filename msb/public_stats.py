"""Bootstrap 95% CIs and paired tests for official public-overlay scores.

Wins must not be decided by 1–2 questions. Official tables should report
a bootstrap 95% CI for each rate and a paired test for the headline
TA / Compute / FAR contrasts.
"""
from __future__ import annotations

import math
from typing import Any, Iterable

import numpy as np

LOWER_IS_BETTER = {
    "FAR_on_clarify_or_refuse",
    "missed_clarify",
    "unnecessary_clarify",
}


def _as_arr(xs: Iterable) -> np.ndarray:
    return np.asarray(list(xs), dtype=float)


def bootstrap_ci(
    indicators: Iterable[float],
    n_boot: int = 10000,
    alpha: float = 0.05,
    seed: int = 20261112,
) -> dict[str, float | None]:
    """Percentile bootstrap CI for a mean (a rate). Empty input → None."""
    x = _as_arr(indicators)
    if x.size == 0:
        return {"n": 0, "mean": None, "ci_low": None, "ci_high": None, "n_boot": n_boot}
    rng = np.random.default_rng(seed)
    means = np.empty(n_boot, dtype=float)
    n = x.size
    for i in range(n_boot):
        means[i] = rng.choice(x, size=n, replace=True).mean()
    lo, hi = np.quantile(means, [alpha / 2, 1 - alpha / 2])
    return {
        "n": int(n),
        "mean": float(x.mean()),
        "ci_low": float(lo),
        "ci_high": float(hi),
        "n_boot": n_boot,
        "seed": seed,
    }


def mcnemar_midp(ours_ok: Iterable[bool], other_ok: Iterable[bool]) -> dict[str, Any]:
    """McNemar mid-p test on paired binary outcomes (e.g. official TA)."""
    a = np.asarray(list(ours_ok), dtype=bool)
    b = np.asarray(list(other_ok), dtype=bool)
    if a.size != b.size or a.size == 0:
        return {"n": int(a.size), "b01": None, "b10": None, "p_mid": None}
    # b01: ours 0 other 1; b10: ours 1 other 0
    b01 = int((~a & b).sum())
    b10 = int((a & ~b).sum())
    n_disc = b01 + b10
    if n_disc == 0:
        p = 1.0
    else:
        # two-sided mid-p: 2 * (0.5 * Binom(n, k_min) + sum_{i=0}^{k_min-1} Binom)
        k = min(b01, b10)
        # P(X <= k) with X~Binom(n_disc, 0.5), mid-p subtracts half the equality term
        # Use exact binomial via scipy if present, else a simple recurrence.
        def binom_cdf_le(k, n):
            # sum_{i=0}^k C(n,i) / 2^n
            # compute in log space iteratively
            # C(n,0)=1
            term = 1.0
            s = term
            for i in range(1, k + 1):
                term *= (n - i + 1) / i
                s += term
            return s / (2 ** n)

        if k == 0:
            p_le = 1.0 / (2 ** n_disc)
            p = min(1.0, 2 * (0.5 * p_le))  # mid-p for k=0 is just binom pmf
            # mid-p two-sided: 2 * (cdf(k) - 0.5*pmf(k))
        p_cdf = binom_cdf_le(k, n_disc)
        # pmf(k)
        term = 1.0
        for i in range(1, k + 1):
            term *= (n_disc - i + 1) / i
        pmf = term / (2 ** n_disc)
        p = min(1.0, 2 * (p_cdf - 0.5 * pmf))
    return {
        "n": int(a.size),
        "b01": b01,
        "b10": b10,
        "n_discordant": n_disc,
        "p_mid": float(p),
        "ours_minus_other": float(a.mean() - b.mean()),
    }


def paired_bootstrap_diff(
    ours: Iterable[float],
    other: Iterable[float],
    n_boot: int = 10000,
    alpha: float = 0.05,
    seed: int = 20261112,
    lower_better: bool = False,
) -> dict[str, Any]:
    """Bootstrap CI for mean(ours) - mean(other). Paired item-level resample."""
    a = _as_arr(ours)
    b = _as_arr(other)
    if a.size != b.size or a.size == 0:
        return {"n": int(a.size), "diff": None, "ci_low": None, "ci_high": None, "p_boot": None}
    d = a - b
    rng = np.random.default_rng(seed)
    n = d.size
    boots = np.empty(n_boot, dtype=float)
    for i in range(n_boot):
        boots[i] = rng.choice(d, size=n, replace=True).mean()
    lo, hi = np.quantile(boots, [alpha / 2, 1 - alpha / 2])
    # one-sided-ish two-sided p: fraction of bootstrap diffs on the other side of 0, *2
    # If lower is better, a win is negative diff.
    if lower_better:
        p = 2 * min((boots >= 0).mean(), (boots <= 0).mean())
    else:
        p = 2 * min((boots <= 0).mean(), (boots >= 0).mean())
    p = float(min(1.0, p))
    return {
        "n": int(n),
        "diff": float(d.mean()),
        "ci_low": float(lo),
        "ci_high": float(hi),
        "p_boot": p,
        "n_boot": n_boot,
        "seed": seed,
        "ci_excludes_zero": bool(lo > 0 or hi < 0),
        "lower_better": lower_better,
    }


def indicators_from_rows(rows: list[dict], metric: str) -> list[float]:
    """Extract a binary/continuous indicator list aligned with scoring rules."""
    out = []
    if metric == "TA":
        for r in rows:
            if r.get("in_official_ta"):
                out.append(1.0 if r.get("TA") else 0.0)
    elif metric == "compute_accuracy":
        for r in rows:
            if r.get("gold_behavior") == "compute" and r.get("in_official_ta"):
                out.append(1.0 if r.get("compute_ok") or r.get("TA") else 0.0)
    elif metric == "FAR_on_clarify_or_refuse":
        for r in rows:
            if r.get("gold_behavior") in {"clarify", "refuse"}:
                # FAR: predicted compute on gold clarify/refuse
                far = r.get("FAR")
                if far is None:
                    far = 1.0 if r.get("pred_behavior") == "compute" or r.get("missed_clarify") else 0.0
                out.append(1.0 if far else 0.0)
    elif metric == "missed_clarify":
        for r in rows:
            if r.get("gold_behavior") == "clarify":
                m = r.get("missed_clarify")
                if m is None:
                    m = 1.0 if r.get("pred_behavior") == "compute" else 0.0
                out.append(1.0 if m else 0.0)
    elif metric == "unnecessary_clarify":
        for r in rows:
            if r.get("gold_behavior") == "compute":
                u = r.get("unnecessary_clarify")
                if u is None:
                    u = 1.0 if r.get("pred_behavior") == "clarify" else 0.0
                out.append(1.0 if u else 0.0)
    else:
        raise ValueError(metric)
    return out


def summarize_system(rows: list[dict], n_boot: int = 10000) -> dict[str, Any]:
    out = {}
    for m in ["TA", "compute_accuracy", "FAR_on_clarify_or_refuse", "missed_clarify", "unnecessary_clarify"]:
        xs = indicators_from_rows(rows, m)
        out[m] = bootstrap_ci(xs, n_boot=n_boot)
    return out


def contrast(ours_rows: list[dict], other_rows: list[dict], metric: str, n_boot: int = 10000) -> dict[str, Any]:
    a = indicators_from_rows(ours_rows, metric)
    b = indicators_from_rows(other_rows, metric)
    lower = metric in LOWER_IS_BETTER
    boot = paired_bootstrap_diff(a, b, n_boot=n_boot, lower_better=lower)
    rec: dict[str, Any] = {"metric": metric, "bootstrap": boot}
    if metric in {"TA", "compute_accuracy"}:
        rec["mcnemar"] = mcnemar_midp([bool(x) for x in a], [bool(x) for x in b])
    return rec


def fmt_ci(rec: dict) -> str:
    if rec.get("mean") is None:
        return "—"
    return f"{100*rec['mean']:.1f}% [{100*rec['ci_low']:.1f}, {100*rec['ci_high']:.1f}]"
