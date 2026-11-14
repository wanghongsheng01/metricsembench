"""Decision-flip atlas: population prevalence of YoY sign disagreement between two legal
metric contracts, on official TPC-DS SF=1, across axes and all three sales channels.

Complete populations (no sampling, no model). Gates are the pre-registered ones of the
paper: sign disagreement = opposite signs and both |YoY| >= 1 pp; magnitude = |gap| >= 2 pp
with |first-contract YoY| >= 1 pp (sign flips included). Store / calendar-vs-rolling-30
reproduces the published 528-triple population exactly (checked).
"""
from __future__ import annotations

import calendar
import json
from datetime import date, timedelta

import duckdb
import numpy as np
import pandas as pd

from msb.config import DB_PATH, MIN_ABS_YOY, RESULTS_DIR

YEARS = range(1999, 2003)
CH = {
    "store": ("store_sales", "ss_sold_date_sk", "ss_item_sk", "ss_net_paid", "ss_ext_sales_price", "ss_quantity"),
    "web": ("web_sales", "ws_sold_date_sk", "ws_item_sk", "ws_net_paid", "ws_ext_sales_price", "ws_quantity"),
    "catalog": ("catalog_sales", "cs_sold_date_sk", "cs_item_sk", "cs_net_paid", "cs_ext_sales_price", "cs_quantity"),
}
RET = {
    "store": ("store_returns", "sr_returned_date_sk", "sr_return_amt", "sr_return_quantity"),
    "web": ("web_returns", "wr_returned_date_sk", "wr_return_amt", "wr_return_quantity"),
    "catalog": ("catalog_returns", "cr_returned_date_sk", "cr_return_amount", "cr_return_quantity"),
}


def daily(con, ch):
    t, dk, ik, paid, ext, qty = CH[ch]
    usd = "SUM(s.ss_net_paid * fx.fx_to_usd)" if ch == "store" else "NULL"
    fxj = ("JOIN msb_store_currency sc ON sc.s_store_sk = s.ss_store_sk JOIN msb_fx_to_usd fx ON fx.currency = sc.currency"
           if ch == "store" else "")
    df = con.execute(f"""
      SELECT d.d_date AS dt, i.i_category AS cat, SUM(s.{paid}) AS paid, {usd} AS usd,
             SUM(s.{ext}) AS ext, SUM(s.{qty}) AS qty
      FROM {t} s JOIN date_dim d ON d.d_date_sk = s.{dk} JOIN item i ON i.i_item_sk = s.{ik} {fxj}
      GROUP BY 1, 2""").df()
    df["dt"] = pd.to_datetime(df["dt"])
    return df


def returns_daily(con, ch):
    t, dk, amt, qty = RET[ch]
    df = con.execute(f"""SELECT d.d_date AS dt, SUM({amt}) AS ramt, SUM({qty}) AS rqty
      FROM {t} r JOIN date_dim d ON d.d_date_sk = r.{dk} GROUP BY 1""").df()
    df["dt"] = pd.to_datetime(df["dt"])
    return df


def win(s: pd.Series, a: date, b: date) -> float:
    return float(s.loc[pd.Timestamp(a):pd.Timestamp(b)].sum())


def mspan(y, m):
    return date(y, m, 1), date(y, m, calendar.monthrange(y, m)[1])


def r30(y, m):
    e = mspan(y, m)[1]
    return e - timedelta(days=29), e


def yoy(cur, prev):
    return (cur - prev) / prev if prev else None


def classify(a, b):
    if a is None or b is None:
        return None
    sign = a * b < 0 and abs(a) >= MIN_ABS_YOY and abs(b) >= MIN_ABS_YOY
    mag = abs(a - b) >= 0.02 and abs(a) >= MIN_ABS_YOY  # as in the paper: includes sign flips
    return sign, mag


def tally(recs):
    recs = [r for r in recs if r is not None]
    n = len(recs)
    s = sum(1 for r in recs if r[0])
    m = sum(1 for r in recs if r[1])
    return {"n": n, "sign": s, "sign_rate": s / n if n else None, "mag": m, "mag_rate": m / n if n else None}


def series(df, col, cat=None):
    d = df if cat is None else df[df["cat"] == cat]
    return d.groupby("dt")[col].sum().sort_index()


def main():
    con = duckdb.connect(str(DB_PATH), read_only=True)
    cats = [c for c in con.execute("SELECT DISTINCT i_category FROM item WHERE i_category IS NOT NULL ORDER BY 1").fetchall()]
    cats = [c[0] for c in cats]
    D = {ch: daily(con, ch) for ch in CH}
    R = {ch: returns_daily(con, ch) for ch in RET}
    out, flips = {}, []
    # A. calendar month vs rolling-30, per channel, all + categories
    for ch in CH:
        recs = []
        for cat in [None] + cats:
            s = series(D[ch], "paid", cat)
            for y in YEARS:
                for m in range(1, 13):
                    cf, cl = mspan(y, m); pf, pl = mspan(y - 1, m)
                    rf, rl = r30(y, m); rpf, rpl = r30(y - 1, m)
                    a = yoy(win(s, cf, cl), win(s, pf, pl)); b = yoy(win(s, rf, rl), win(s, rpf, rpl))
                    c = classify(a, b)
                    recs.append(c)
                    if c and c[0]:
                        flips.append({"axis": "calendar_month_vs_rolling30", "channel": ch, "cat": cat, "yr": y, "moy": m, "a": a, "b": b})
        out[f"A_calendar_month_vs_r30__{ch}"] = tally(recs)
    # B. calendar year vs retail FY (Feb 1), complete years 2000 and 2001
    for ch in CH:
        recs = []
        for cat in [None] + cats:
            s = series(D[ch], "paid", cat)
            for y in (2000, 2001):
                a = yoy(win(s, date(y, 1, 1), date(y, 12, 31)), win(s, date(y - 1, 1, 1), date(y - 1, 12, 31)))
                b = yoy(win(s, date(y, 2, 1), date(y + 1, 1, 31)), win(s, date(y - 1, 2, 1), date(y, 1, 31)))
                c = classify(a, b); recs.append(c)
                if c and c[0]:
                    flips.append({"axis": "calendar_year_vs_retail_fy", "channel": ch, "cat": cat, "yr": y, "a": a, "b": b})
        out[f"B_calendar_year_vs_retail_fy__{ch}"] = tally(recs)
    # C. currency: raw mixed-currency vs USD-converted monthly YoY (store; overlay is store-based)
    recs = []
    for cat in [None] + cats:
        sr, su = series(D["store"], "paid", cat), series(D["store"], "usd", cat)
        for y in YEARS:
            for m in range(1, 13):
                cf, cl = mspan(y, m); pf, pl = mspan(y - 1, m)
                a = yoy(win(su, cf, cl), win(su, pf, pl)); b = yoy(win(sr, cf, cl), win(sr, pf, pl))
                c = classify(a, b); recs.append(c)
                if c and c[0]:
                    flips.append({"axis": "usd_vs_raw_mixed", "channel": "store", "cat": cat, "yr": y, "moy": m, "a": a, "b": b})
    out["C_usd_vs_raw_mixed__store"] = tally(recs)
    # D. channel scope: store-only vs store+web+catalog monthly YoY
    recs = []
    for cat in [None] + cats:
        ss = series(D["store"], "paid", cat)
        sa = ss.add(series(D["web"], "paid", cat), fill_value=0).add(series(D["catalog"], "paid", cat), fill_value=0)
        for y in YEARS:
            for m in range(1, 13):
                cf, cl = mspan(y, m); pf, pl = mspan(y - 1, m)
                a = yoy(win(ss, cf, cl), win(ss, pf, pl)); b = yoy(win(sa, cf, cl), win(sa, pf, pl))
                c = classify(a, b); recs.append(c)
                if c and c[0]:
                    flips.append({"axis": "store_only_vs_all_channels", "channel": "all", "cat": cat, "yr": y, "moy": m, "a": a, "b": b})
    out["D_store_only_vs_all_channels"] = tally(recs)
    # E. return rate on amount vs on quantity: YoY change of the rate, per channel, monthly
    for ch in CH:
        recs = []
        se, sq = series(D[ch], "ext", None), series(D[ch], "qty", None)
        ra, rq = R[ch].set_index("dt")["ramt"].sort_index(), R[ch].set_index("dt")["rqty"].sort_index()
        for y in YEARS:
            for m in range(1, 13):
                cf, cl = mspan(y, m); pf, pl = mspan(y - 1, m)
                ia, ip = win(ra, cf, cl) / win(se, cf, cl), win(ra, pf, pl) / win(se, pf, pl)
                qa, qp = win(rq, cf, cl) / win(sq, cf, cl), win(rq, pf, pl) / win(sq, pf, pl)
                a, b = yoy(ia, ip), yoy(qa, qp)
                c = classify(a, b); recs.append(c)
                if c and c[0]:
                    flips.append({"axis": "return_rate_amount_vs_quantity", "channel": ch, "cat": None, "yr": y, "moy": m, "a": a, "b": b})
        out[f"E_return_rate_amt_vs_qty__{ch}"] = tally(recs)
    tot = {"n": sum(v["n"] for v in out.values()), "sign": sum(v["sign"] for v in out.values()), "mag": sum(v["mag"] for v in out.values())}
    tot["sign_rate"], tot["mag_rate"] = tot["sign"] / tot["n"], tot["mag"] / tot["n"]
    res = {"populations": out, "total": tot, "flips": flips,
           "gates": {"sign": "opposite signs, both |YoY| >= 1 pp", "magnitude": "|gap| >= 2 pp and |first| >= 1 pp (includes sign flips, as in Table 3)"}}
    (RESULTS_DIR / "paper15_official" / "prevalence_atlas.json").write_text(json.dumps(res, indent=2, default=str))
    for k, v in out.items():
        print(f"{k:45s} n={v['n']:5d} sign={v['sign']:3d} ({100*v['sign_rate']:.2f}%) mag={v['mag']:4d} ({100*v['mag_rate']:.2f}%)")
    print("TOTAL", tot)


if __name__ == "__main__":
    main()
