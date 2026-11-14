"""Build and hash-freeze Paper 15's second official TPC-DS held-out (scale fold).

`p15_heldout_v2` is pre-registered on 2026-11-13 (America/Los_Angeles) BEFORE any
score on it. It answers the reviewer question "n=94 is small; FAR denominators
are small": same handbook, same frozen schema card, same metric definitions,
a larger and more balanced fold, disjoint from v0.1 and p15_heldout_v1.

Design (all selection is model-blind; ordering is sha256(seed|key), never by gap):
  A. Calendar month vs rolling-30 (category/all-stores triples): leftover triples not
     in v0.1 or v1. K_MAG=12 from the same-sign magnitude stratum, K_OTHER=12 from the
     ordinary stratum. 3 tasks each (clarify + two specified computes).
  B. Calendar year vs retail FY at CATEGORY grain (v0.1 used all-stores 2000/2001):
     complete years 2000 and 2001 x 10 categories, first K_FY=6 by hash. 3 tasks each.
  C. Category-grain replication of the lifecycle, currency and non-additive axes
     (v0.1/v1 are all-category). (year, category) pairs over years 1999-2002, first
     K_YC=8 by hash. Per pair: new-product share (clarify + 2 computes), currency
     (clarify + USD compute + raw-as-USD refuse), AOV (compute + sum-of-store refuse),
     margin (compute + sum-of-store refuse). 10 tasks per pair.
  D. Month-grain denominator axis (v0.1/v1 are year grain): (year, month) pairs over
     1999-2002, first K_YM=8 by hash. Per pair: return rate amount vs quantity
     (clarify + 2 computes) and store vs all-channel net sales (clarify + 2 computes).
  E. Sparse refuse in two pre-registered windows unused before (Aug 2002 vs Aug 2001,
     Nov 2002 vs Nov 2001): items and brands meeting the same gate (current tickets
     >= 10, prior < 5), excluding v0.1/v1 items and brands, first 6 + 6 per window by hash.
  F. Incomplete-window refuse at category grain: first K_INC=4 categories by hash,
     calendar-2003 total and retail-FY-2002 YoY each.

Same Match tolerance, metrics, bootstrap seed. evaluated=false at freeze.
Never loads paper-13 official TEST folds.
"""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from datetime import date
from pathlib import Path

import duckdb

from msb.build_tasks import MONTH_NAME, month_first, month_last, q_yoy, retail_fy_span, rolling30, scalar
from msb.build_paper15_heldout import (
    _make as _make_v1,
    _payload_sha,
    scan_calendar,
    used_v01_calendar,
    used_v01_sparse,
    validate,
)
from msb.config import DB_PATH, MIN_ABS_YOY, SPARSE_MIN_PRIOR_TICKETS, TASKS_DIR
from msb.dictionary import DICTIONARY
from msb.forbidden_folds import assert_allowed_task_path

VER = "p15_heldout_v2"
SEED = "paper15_msb_tpcds_heldout_v2_seed_20261113"
K_MAG, K_OTHER, K_FY, K_YC, K_YM, K_SPARSE, K_INC = 12, 12, 6, 8, 8, 6, 4
YEARS = (1999, 2000, 2001, 2002)
V01 = TASKS_DIR / "msb_v0.1_tasks.json"
V1 = TASKS_DIR / "msb_p15_heldout_v1_tasks.json"
OUT = TASKS_DIR / "msb_p15_heldout_v2_tasks.json"
OUT_DOC = TASKS_DIR / "MSB_P15_HELDOUT_V2.md"
CATEGORIES_SQL = "SELECT DISTINCT i_category FROM msb_store_sales WHERE i_category IS NOT NULL ORDER BY 1"


def H(*parts) -> str:
    return hashlib.sha256("|".join([SEED, *map(str, parts)]).encode()).hexdigest()


def mk(tid, **kw):
    t = _make_v1(tid, **kw)
    t["version"] = VER
    t["fold"] = "paper15_official_heldout_v2"
    t["split"] = "TEST"
    return t


def slug(s: str) -> str:
    return "".join(ch.lower() if ch.isalnum() else "_" for ch in s).strip("_")


def add_calendar_triple(con, tasks, rec, n):
    yr, moy, cat = rec["yr"], rec["moy"], rec["cat"]
    cf, cl = month_first(yr, moy), month_last(yr, moy)
    pf, pl = month_first(yr - 1, moy), month_last(yr - 1, moy)
    rf, rl = rolling30(yr, moy)
    rpf, rpl = rolling30(yr - 1, moy)
    ex = f"i_category = '{cat}'" if cat else ""
    sql_cal, sql_r30 = q_yoy(cf, cl, pf, pl, ex), q_yoy(rf, rl, rpf, rpl, ex)
    v_cal, v_r30 = scalar(con, sql_cal), scalar(con, sql_r30)
    defs = [
        {"id": "calendar_month", "sql": sql_cal.strip(), "value": v_cal, "unit": "ratio"},
        {"id": "rolling_30", "sql": sql_r30.strip(), "value": v_r30, "unit": "ratio"},
    ]
    mon = MONTH_NAME[moy]
    sc = f" in the {cat} category" if cat else ""
    meta = {**{k: rec[k] for k in ("yr", "moy", "cat", "cal_yoy", "r30_yoy", "sign_d", "gap")},
            "selection_hash": H("cal", yr, moy, cat)}
    n += 1
    tasks.append(mk(f"msb_{VER}_cal_clarify_{n:03d}", type="calendar", subtype="month_vs_rolling30_yoy",
        gold_behavior="clarify",
        question_en=f"What was the year-over-year growth rate of store net sales{sc} for {mon} {yr}?",
        question_zh=f"{yr}年{moy}月门店净销售额{sc}的同比增长率是多少？",
        paired_definitions=defs, sign_disagreement=rec["sign_d"], metadata=meta))
    n += 1
    tasks.append(mk(f"msb_{VER}_cal_compute_cal_{n:03d}", type="calendar", subtype="month_vs_rolling30_yoy",
        gold_behavior="compute", specified_definition="calendar_month",
        question_en=(f"What was the year-over-year growth rate of store net sales{sc} for calendar month "
                     f"{mon} {yr} ({cf.isoformat()} to {cl.isoformat()} vs {pf.isoformat()} to {pl.isoformat()})?"),
        question_zh=f"按自然月（{cf}–{cl} 对比 {pf}–{pl}），{yr}年{moy}月门店净销售额{sc}的同比是多少？",
        paired_definitions=defs, gold_sql=sql_cal.strip(), gold_value=v_cal, gold_unit="ratio",
        sign_disagreement=rec["sign_d"], metadata=meta))
    n += 1
    tasks.append(mk(f"msb_{VER}_cal_compute_r30_{n:03d}", type="calendar", subtype="month_vs_rolling30_yoy",
        gold_behavior="compute", specified_definition="rolling_30",
        question_en=(f"What was the year-over-year growth rate of store net sales{sc} for the rolling 30-day "
                     f"window ending {rl.isoformat()} ({rf.isoformat()} to {rl.isoformat()} vs "
                     f"{rpf.isoformat()} to {rpl.isoformat()})?"),
        question_zh=f"按滚动30天（{rf}–{rl} 对比 {rpf}–{rpl}），门店净销售额{sc}的同比是多少？",
        paired_definitions=defs, gold_sql=sql_r30.strip(), gold_value=v_r30, gold_unit="ratio",
        sign_disagreement=rec["sign_d"], metadata=meta))
    return n


def add_fy_category(con, tasks, yr, cat):
    ex = f"i_category = '{cat}'"
    cy_f, cy_t, py_f, py_t = date(yr, 1, 1), date(yr, 12, 31), date(yr - 1, 1, 1), date(yr - 1, 12, 31)
    fy_f, fy_t = retail_fy_span(yr)
    fyp_f, fyp_t = retail_fy_span(yr - 1)
    sql_cy, sql_fy = q_yoy(cy_f, cy_t, py_f, py_t, ex), q_yoy(fy_f, fy_t, fyp_f, fyp_t, ex)
    v_cy, v_fy = scalar(con, sql_cy), scalar(con, sql_fy)
    sign_d = (v_cy * v_fy < 0) and abs(v_cy) >= MIN_ABS_YOY and abs(v_fy) >= MIN_ABS_YOY
    defs = [{"id": "calendar_year", "sql": sql_cy.strip(), "value": v_cy, "unit": "ratio"},
            {"id": "retail_fy", "sql": sql_fy.strip(), "value": v_fy, "unit": "ratio"}]
    meta = {"yr": yr, "cat": cat, "cal_yoy": v_cy, "fy_yoy": v_fy, "sign_d": sign_d, "selection_hash": H("fy", yr, cat)}
    s = slug(cat)
    tasks.append(mk(f"msb_{VER}_cal_fy_clarify_{s}_{yr}", type="calendar", subtype="calendar_year_vs_retail_fy_yoy",
        gold_behavior="clarify",
        question_en=f"What was the year-over-year growth rate of store net sales in the {cat} category for {yr}?",
        question_zh=f"{yr}年{cat}类目门店净销售额的同比增长率是多少？",
        paired_definitions=defs, sign_disagreement=sign_d, metadata=meta))
    tasks.append(mk(f"msb_{VER}_cal_fy_compute_cal_{s}_{yr}", type="calendar", subtype="calendar_year_vs_retail_fy_yoy",
        gold_behavior="compute", specified_definition="calendar_year",
        question_en=(f"What was the year-over-year growth rate of store net sales in the {cat} category for calendar "
                     f"year {yr} (January 1 to December 31 {yr} vs the same span in {yr-1})?"),
        question_zh=f"按自然年（1月1日–12月31日），{yr}年{cat}类目门店净销售额同比是多少？",
        paired_definitions=defs, gold_sql=sql_cy.strip(), gold_value=v_cy, gold_unit="ratio",
        sign_disagreement=sign_d, metadata=meta))
    tasks.append(mk(f"msb_{VER}_cal_fy_compute_fy_{s}_{yr}", type="calendar", subtype="calendar_year_vs_retail_fy_yoy",
        gold_behavior="compute", specified_definition="retail_fy",
        question_en=(f"What was the year-over-year growth rate of store net sales in the {cat} category for retail "
                     f"fiscal year {yr} (February 1 {yr} to January 31 {yr+1} vs February 1 {yr-1} to January 31 {yr})?"),
        question_zh=f"按零售财年（{yr}-02-01 至 {yr+1}-01-31），{yr}财年{cat}类目门店净销售额同比是多少？",
        paired_definitions=defs, gold_sql=sql_fy.strip(), gold_value=v_fy, gold_unit="ratio",
        sign_disagreement=sign_d, metadata=meta))


def add_year_category(con, tasks, yr, cat):
    s = slug(cat)
    c = f"i_category = '{cat}'"
    meta0 = {"yr": yr, "cat": cat, "selection_hash": H("yc", yr, cat)}
    # Lifecycle new-product share within a category.
    sql_first = f"""
    WITH first_sale AS (SELECT i_item_id, MIN(d_date) AS first_d FROM msb_store_sales GROUP BY 1),
    new_ids AS (SELECT i_item_id FROM first_sale WHERE year(first_d) = {yr})
    SELECT SUM(CASE WHEN n.i_item_id IS NOT NULL THEN ss.ss_net_paid ELSE 0 END) * 1.0 / NULLIF(SUM(ss.ss_net_paid), 0)
    FROM msb_store_sales ss LEFT JOIN new_ids n ON n.i_item_id = ss.i_item_id
    WHERE ss.d_year = {yr} AND ss.{c}
    """
    sql_rec = f"""
    WITH new_ids AS (SELECT DISTINCT i_item_id FROM item
      WHERE i_rec_start_date IS NOT NULL AND year(i_rec_start_date) = {yr})
    SELECT SUM(CASE WHEN n.i_item_id IS NOT NULL THEN ss.ss_net_paid ELSE 0 END) * 1.0 / NULLIF(SUM(ss.ss_net_paid), 0)
    FROM msb_store_sales ss LEFT JOIN new_ids n ON n.i_item_id = ss.i_item_id
    WHERE ss.d_year = {yr} AND ss.{c}
    """
    v1, v2 = scalar(con, sql_first), scalar(con, sql_rec)
    defs = [{"id": "first_sale_in_period", "sql": sql_first.strip(), "value": v1, "unit": "ratio"},
            {"id": "catalog_rec_start_in_period", "sql": sql_rec.strip(), "value": v2, "unit": "ratio"}]
    m = {**meta0, "gap": abs(v1 - v2)}
    tasks.append(mk(f"msb_{VER}_life_clarify_newshare_{s}_{yr}", type="lifecycle", subtype="new_product_sales_share",
        gold_behavior="clarify",
        question_en=f"What share of {cat} store net sales in calendar year {yr} came from new products?",
        question_zh=f"{yr}自然年{cat}类目门店净销售额中新品占比是多少？", paired_definitions=defs, metadata=m))
    tasks.append(mk(f"msb_{VER}_life_compute_firstsale_{s}_{yr}", type="lifecycle", subtype="new_product_sales_share",
        gold_behavior="compute", specified_definition="first_sale_in_period",
        question_en=(f"What share of {cat} store net sales in calendar year {yr} came from items whose first store "
                     f"sale in the fixture falls in {yr}?"),
        question_zh=f"{yr}年{cat}类目中，以当年首次门店销售定义的新品占门店净销售额的比例？",
        paired_definitions=defs, gold_sql=sql_first.strip(), gold_value=v1, gold_unit="ratio", metadata=m))
    tasks.append(mk(f"msb_{VER}_life_compute_recstart_{s}_{yr}", type="lifecycle", subtype="new_product_sales_share",
        gold_behavior="compute", specified_definition="catalog_rec_start_in_period",
        question_en=(f"What share of {cat} store net sales in calendar year {yr} came from items whose catalog record "
                     f"start date (i_rec_start_date) falls in {yr}?"),
        question_zh=f"{yr}年{cat}类目中，目录记录开始日期在该年的商品占门店净销售额的比例？",
        paired_definitions=defs, gold_sql=sql_rec.strip(), gold_value=v2, gold_unit="ratio", metadata=m))
    # Currency.
    sql_raw = f"SELECT SUM(ss_net_paid) FROM msb_store_sales WHERE d_year = {yr} AND {c}"
    sql_usd = f"SELECT SUM(net_paid_usd) FROM msb_store_sales WHERE d_year = {yr} AND {c}"
    v_raw, v_usd = scalar(con, sql_raw), scalar(con, sql_usd)
    defs_c = [
        {"id": "raw_local_sum", "sql": sql_raw, "value": v_raw, "unit": "mixed_currency_amount",
         "note": "Illegal as a single-currency total; provided only to detect definition swap."},
        {"id": "converted_usd_sum", "sql": sql_usd, "value": v_usd, "unit": "usd",
         "note": "Legal under metricsem_fx_v1: local amounts times frozen fx_to_usd."}]
    tasks.append(mk(f"msb_{VER}_ccy_clarify_{s}_{yr}", type="currency", subtype="raw_vs_usd_converted",
        gold_behavior="clarify", question_en=f"What were total {cat} store net sales in calendar year {yr}?",
        question_zh=f"{yr}自然年{cat}类目门店净销售额合计是多少？", paired_definitions=defs_c,
        extensions=["metricsem_fx_v1"], metadata={**meta0, "raw": v_raw, "usd": v_usd}))
    tasks.append(mk(f"msb_{VER}_ccy_compute_usd_{s}_{yr}", type="currency", subtype="raw_vs_usd_converted",
        gold_behavior="compute", specified_definition="converted_usd_sum",
        question_en=(f"What were total {cat} store net sales in calendar year {yr} in USD after converting each "
                     f"store's local currency with the frozen metricsem_fx_v1 rates?"),
        question_zh=f"按 metricsem_fx_v1 汇率折算为美元后，{yr}年{cat}类目门店净销售额合计是多少？",
        paired_definitions=defs_c, gold_sql=sql_usd, gold_value=v_usd, gold_unit="usd",
        extensions=["metricsem_fx_v1"], metadata=meta0))
    tasks.append(mk(f"msb_{VER}_ccy_refuse_raw_as_usd_{s}_{yr}", type="currency", subtype="raw_sum_claimed_as_usd",
        gold_behavior="refuse", refuse_reason="currency_mix_no_fx",
        question_en=(f"Report a single USD total of {cat} store net sales for calendar year {yr} by summing "
                     f"ss_net_paid across all stores without conversion (treat every local amount as if it were already USD)."),
        question_zh=f"把各店本地币种的 {cat} 类目 ss_net_paid 直接相加，作为{yr}年以美元计的门店净销售总额。",
        paired_definitions=defs_c, extensions=["metricsem_fx_v1"],
        metadata={**meta0, "illegal_value_if_executed": v_raw}))
    # Non-additive AOV and margin.
    sql_ov = f"SELECT SUM(ss_net_paid) * 1.0 / NULLIF(COUNT(DISTINCT ss_ticket_number), 0) FROM msb_store_sales WHERE d_year = {yr} AND {c}"
    sql_sum = f"""SELECT SUM(aov) FROM (SELECT ss_store_sk, SUM(ss_net_paid) * 1.0 / NULLIF(COUNT(DISTINCT ss_ticket_number), 0) AS aov
      FROM msb_store_sales WHERE d_year = {yr} AND {c} GROUP BY ss_store_sk)"""
    v_ov, v_sum = scalar(con, sql_ov), scalar(con, sql_sum)
    defs_n = [{"id": "overall_aov", "sql": sql_ov, "value": v_ov, "unit": "amount_per_ticket"},
              {"id": "sum_of_store_aovs", "sql": sql_sum.strip(), "value": v_sum, "unit": "illegal_sum_of_rates"}]
    tasks.append(mk(f"msb_{VER}_nadd_compute_overall_aov_{s}_{yr}", type="non_additive", subtype="aov",
        gold_behavior="compute", specified_definition="overall_aov",
        question_en=(f"What was the overall average order value of {cat} store sales in calendar year {yr}, defined as "
                     f"total ss_net_paid divided by the number of distinct tickets?"),
        question_zh=f"{yr}自然年{cat}类目门店总体客单价（净销售额 / 去重小票数）是多少？",
        paired_definitions=defs_n, gold_sql=sql_ov, gold_value=v_ov, gold_unit="amount_per_ticket", metadata=meta0))
    tasks.append(mk(f"msb_{VER}_nadd_refuse_sum_store_aov_{s}_{yr}", type="non_additive", subtype="aov_illegal_sum",
        gold_behavior="refuse", refuse_reason="non_additive_sum",
        question_en=(f"Report the total average order value of {cat} store sales for calendar year {yr} by summing "
                     f"the per-store average order values."),
        question_zh=f"把各门店{yr}年{cat}类目客单价相加，作为该年总客单价。", paired_definitions=defs_n,
        metadata={**meta0, "illegal_value_if_executed": v_sum, "overall_aov": v_ov}))
    sql_om = f"SELECT SUM(ss_net_profit) * 1.0 / NULLIF(SUM(ss_net_paid), 0) FROM msb_store_sales WHERE d_year = {yr} AND {c}"
    sql_sm = f"""SELECT SUM(m) FROM (SELECT ss_store_sk, SUM(ss_net_profit) * 1.0 / NULLIF(SUM(ss_net_paid), 0) AS m
      FROM msb_store_sales WHERE d_year = {yr} AND {c} GROUP BY ss_store_sk)"""
    v_om, v_sm = scalar(con, sql_om), scalar(con, sql_sm)
    defs_m = [{"id": "overall_margin_rate", "sql": sql_om, "value": v_om, "unit": "ratio"},
              {"id": "sum_of_store_margin_rates", "sql": sql_sm.strip(), "value": v_sm, "unit": "illegal_sum_of_rates"}]
    tasks.append(mk(f"msb_{VER}_nadd_compute_margin_{s}_{yr}", type="non_additive", subtype="margin_rate",
        gold_behavior="compute", specified_definition="overall_margin_rate",
        question_en=(f"What was the overall net-profit margin rate of {cat} store sales in calendar year {yr}, defined "
                     f"as SUM(ss_net_profit) / SUM(ss_net_paid)?"),
        question_zh=f"{yr}年{cat}类目门店总体净利润率（SUM(ss_net_profit)/SUM(ss_net_paid)）是多少？",
        paired_definitions=defs_m, gold_sql=sql_om, gold_value=v_om, gold_unit="ratio", metadata=meta0))
    tasks.append(mk(f"msb_{VER}_nadd_refuse_sum_margin_{s}_{yr}", type="non_additive", subtype="margin_rate_illegal_sum",
        gold_behavior="refuse", refuse_reason="non_additive_sum",
        question_en=(f"Report the total net-profit margin rate of {cat} store sales for calendar year {yr} by summing "
                     f"the per-store margin rates."),
        question_zh=f"把各门店{yr}年{cat}类目净利润率相加，作为该年总利润率。", paired_definitions=defs_m,
        metadata={**meta0, "illegal_value_if_executed": v_sm, "overall": v_om}))


def add_year_month(con, tasks, yr, moy):
    f, l = month_first(yr, moy), month_last(yr, moy)
    mon = MONTH_NAME[moy]
    w = f"d_date BETWEEN DATE '{f}' AND DATE '{l}'"
    meta0 = {"yr": yr, "moy": moy, "window": [f.isoformat(), l.isoformat()], "selection_hash": H("ym", yr, moy)}
    tag = f"{yr}_{moy:02d}"
    sql_amt = f"""SELECT (SELECT SUM(sr_return_amt) FROM msb_store_returns WHERE {w}) * 1.0
         / NULLIF((SELECT SUM(ss_ext_sales_price) FROM msb_store_sales WHERE {w}), 0)"""
    sql_qty = f"""SELECT (SELECT SUM(sr_return_quantity) FROM msb_store_returns WHERE {w}) * 1.0
         / NULLIF((SELECT SUM(ss_quantity) FROM msb_store_sales WHERE {w}), 0)"""
    v_a, v_q = scalar(con, sql_amt), scalar(con, sql_qty)
    defs_r = [{"id": "return_rate_amount", "sql": sql_amt.strip(), "value": v_a, "unit": "ratio"},
              {"id": "return_rate_quantity", "sql": sql_qty.strip(), "value": v_q, "unit": "ratio"}]
    tasks.append(mk(f"msb_{VER}_den_clarify_return_{tag}", type="denominator", subtype="return_rate_amt_vs_qty",
        gold_behavior="clarify", question_en=f"What was the store return rate in {mon} {yr}?",
        question_zh=f"{yr}年{moy}月门店退货率是多少？", paired_definitions=defs_r,
        metadata={**meta0, "gap": abs(v_a - v_q)}))
    tasks.append(mk(f"msb_{VER}_den_compute_return_amt_{tag}", type="denominator", subtype="return_rate_amt_vs_qty",
        gold_behavior="compute", specified_definition="return_rate_amount",
        question_en=(f"What was the store return rate in {mon} {yr} ({f} to {l}), defined as "
                     f"SUM(sr_return_amt) / SUM(ss_ext_sales_price) over that month?"),
        question_zh=f"{yr}年{moy}月（{f}–{l}）按金额计的门店退货率（退货金额/销售金额）是多少？",
        paired_definitions=defs_r, gold_sql=sql_amt.strip(), gold_value=v_a, gold_unit="ratio", metadata=meta0))
    tasks.append(mk(f"msb_{VER}_den_compute_return_qty_{tag}", type="denominator", subtype="return_rate_amt_vs_qty",
        gold_behavior="compute", specified_definition="return_rate_quantity",
        question_en=(f"What was the store return rate in {mon} {yr} ({f} to {l}), defined as "
                     f"SUM(sr_return_quantity) / SUM(ss_quantity) over that month?"),
        question_zh=f"{yr}年{moy}月（{f}–{l}）按件数计的门店退货率（退货件数/销售件数）是多少？",
        paired_definitions=defs_r, gold_sql=sql_qty.strip(), gold_value=v_q, gold_unit="ratio", metadata=meta0))
    sql_store = f"SELECT SUM(ss_net_paid) FROM msb_store_sales WHERE {w}"
    sql_all = f"""SELECT (SELECT SUM(ss_net_paid) FROM msb_store_sales WHERE {w})
      + (SELECT SUM(ws_net_paid) FROM msb_web_sales WHERE {w})
      + (SELECT SUM(cs_net_paid) FROM msb_catalog_sales WHERE {w})"""
    v_s, v_all = scalar(con, sql_store), scalar(con, sql_all)
    defs_ch = [{"id": "store_channel_only", "sql": sql_store, "value": v_s, "unit": "amount"},
               {"id": "store_web_catalog", "sql": sql_all.strip(), "value": v_all, "unit": "amount"}]
    tasks.append(mk(f"msb_{VER}_den_clarify_channel_{tag}", type="denominator", subtype="channel_scope",
        gold_behavior="clarify", question_en=f"What were total net sales in {mon} {yr}?",
        question_zh=f"{yr}年{moy}月净销售总额是多少？", paired_definitions=defs_ch,
        metadata={**meta0, "rel_gap": abs(v_all - v_s) / v_s}))
    tasks.append(mk(f"msb_{VER}_den_compute_store_{tag}", type="denominator", subtype="channel_scope",
        gold_behavior="compute", specified_definition="store_channel_only",
        question_en=f"What were total store-channel net sales (store_sales only) in {mon} {yr} ({f} to {l})?",
        question_zh=f"{yr}年{moy}月（{f}–{l}）仅门店渠道（store_sales）净销售额是多少？",
        paired_definitions=defs_ch, gold_sql=sql_store, gold_value=v_s, gold_unit="amount", metadata=meta0))
    tasks.append(mk(f"msb_{VER}_den_compute_allch_{tag}", type="denominator", subtype="channel_scope",
        gold_behavior="compute", specified_definition="store_web_catalog",
        question_en=(f"What were total net sales across store, web, and catalog channels "
                     f"(SUM ss_net_paid + ws_net_paid + cs_net_paid) in {mon} {yr} ({f} to {l})?"),
        question_zh=f"{yr}年{moy}月（{f}–{l}）门店+网站+目录三渠道净销售额合计是多少？",
        paired_definitions=defs_ch, gold_sql=sql_all.strip(), gold_value=v_all, gold_unit="amount", metadata=meta0))


def add_sparse(con, tasks, used_items, used_brands, cur, prev):
    (cf, cl), (pf, pl) = cur, prev
    cy, cm = int(cf[:4]), int(cf[5:7])
    mon = MONTH_NAME[cm]
    rows = con.execute(f"""
      WITH c AS (SELECT i_item_id, i_category, COUNT(DISTINCT ss_ticket_number) t, SUM(ss_net_paid) a FROM msb_store_sales
                 WHERE d_date BETWEEN DATE '{cf}' AND DATE '{cl}' GROUP BY 1,2),
           p AS (SELECT i_item_id, COUNT(DISTINCT ss_ticket_number) t, SUM(ss_net_paid) a FROM msb_store_sales
                 WHERE d_date BETWEEN DATE '{pf}' AND DATE '{pl}' GROUP BY 1)
      SELECT c.i_item_id, c.i_category, c.t, c.a, COALESCE(p.t,0), COALESCE(p.a,0)
      FROM c LEFT JOIN p ON p.i_item_id=c.i_item_id
      WHERE c.t >= 10 AND COALESCE(p.t,0) < {SPARSE_MIN_PRIOR_TICKETS}""").fetchall()
    rows = sorted([r for r in rows if r[0] not in used_items], key=lambda r: H("item", cf, r[0]))[:K_SPARSE]
    for (item_id, cat, ct, ca, pt, pa) in rows:
        used_items.add(item_id)
        tasks.append(mk(f"msb_{VER}_sparse_refuse_item_{slug(item_id)}_{cy}_{cm:02d}", type="sparse_completeness",
            subtype="item_month_yoy_sparse_prior", gold_behavior="refuse",
            refuse_reason="sparse_prior" if pt > 0 else "undefined_yoy",
            question_en=(f"What was the year-over-year growth rate of store net sales for item {item_id} in calendar "
                         f"month {mon} {cy} (versus {mon} {cy-1})?"),
            question_zh=f"商品 {item_id} 在 {cy}年{cm}月相对 {cy-1}年{cm}月的门店净销售同比是多少？",
            metadata={"item_id": item_id, "category": cat, "cur_tickets": int(ct), "prev_tickets": int(pt),
                      "cur_amt": float(ca), "prev_amt": float(pa), "window": [cf, cl], "prior_window": [pf, pl],
                      "selection_hash": H("item", cf, item_id)}))
    rows2 = con.execute(f"""
      WITH c AS (SELECT i_brand, i_category, COUNT(DISTINCT ss_ticket_number) t, SUM(ss_net_paid) a FROM msb_store_sales
                 WHERE d_date BETWEEN DATE '{cf}' AND DATE '{cl}' AND i_category IS NOT NULL AND i_brand IS NOT NULL GROUP BY 1,2),
           p AS (SELECT i_brand, i_category, COUNT(DISTINCT ss_ticket_number) t, SUM(ss_net_paid) a FROM msb_store_sales
                 WHERE d_date BETWEEN DATE '{pf}' AND DATE '{pl}' AND i_category IS NOT NULL AND i_brand IS NOT NULL GROUP BY 1,2)
      SELECT c.i_brand, c.i_category, c.t, c.a, COALESCE(p.t,0), COALESCE(p.a,0)
      FROM c LEFT JOIN p ON p.i_brand=c.i_brand AND p.i_category=c.i_category
      WHERE c.t >= 10 AND COALESCE(p.t,0) < {SPARSE_MIN_PRIOR_TICKETS}""").fetchall()
    rows2 = sorted([r for r in rows2 if (r[0], r[1]) not in used_brands], key=lambda r: H("brand", cf, r[0], r[1]))[:K_SPARSE]
    for (brand, cat, ct, ca, pt, pa) in rows2:
        used_brands.add((brand, cat))
        tasks.append(mk(f"msb_{VER}_sparse_refuse_brand_{slug(brand)}_{slug(cat)}_{cy}_{cm:02d}", type="sparse_completeness",
            subtype="brand_month_yoy_sparse_prior", gold_behavior="refuse",
            refuse_reason="sparse_prior" if pt > 0 else "undefined_yoy",
            question_en=(f"What was the year-over-year growth rate of store net sales for brand {brand!r} in the {cat} "
                         f"category for calendar month {mon} {cy}?"),
            question_zh=f"{cat} 类目下品牌 {brand} 在 {cy}年{cm}月的门店净销售同比是多少？",
            metadata={"brand": brand, "category": cat, "cur_tickets": int(ct), "prev_tickets": int(pt),
                      "cur_amt": float(ca), "prev_amt": float(pa), "window": [cf, cl],
                      "selection_hash": H("brand", cf, brand, cat)}))
    return len(rows), len(rows2)


def add_incomplete(con, tasks, cat, max_d):
    s = slug(cat)
    tasks.append(mk(f"msb_{VER}_inc_refuse_fy2002_{s}", type="sparse_completeness", subtype="incomplete_retail_fy",
        gold_behavior="refuse", refuse_reason="incomplete_period",
        question_en=(f"What was the year-over-year growth rate of store net sales in the {cat} category for retail fiscal "
                     f"year 2002 (February 1 2002 to January 31 2003)?"),
        question_zh=f"零售财年2002（2002-02-01 至 2003-01-31）{cat}类目门店净销售额同比是多少？",
        metadata={"cat": cat, "required_end": "2003-01-31", "fixture_max_date": str(max_d), "complete": False,
                  "selection_hash": H("inc", cat)}))
    tasks.append(mk(f"msb_{VER}_inc_refuse_cy2003_{s}", type="sparse_completeness", subtype="incomplete_calendar_year",
        gold_behavior="refuse", refuse_reason="incomplete_period",
        question_en=f"What were total {cat} store net sales for calendar year 2003 (January 1 to December 31 2003)?",
        question_zh=f"2003自然年（1月1日–12月31日）{cat}类目门店净销售额合计是多少？",
        metadata={"cat": cat, "required_end": "2003-12-31", "fixture_max_date": str(max_d), "complete": False,
                  "selection_hash": H("inc", cat)}))


def build():
    v01 = json.loads(assert_allowed_task_path(V01).read_text(encoding="utf-8"))
    v1 = json.loads(assert_allowed_task_path(V1).read_text(encoding="utf-8"))
    prior_tasks = v01["tasks"] + v1["tasks"]
    used_cal = used_v01_calendar(prior_tasks)
    used_items, used_brands = used_v01_sparse(prior_tasks)
    con = duckdb.connect(str(DB_PATH), read_only=True)
    max_d = con.execute("SELECT max(d_date) FROM msb_store_sales").fetchone()[0]
    cats = [r[0] for r in con.execute(CATEGORIES_SQL).fetchall()]
    recs = scan_calendar(con)
    key = lambda r: (r["yr"], r["moy"], r["cat"])
    left_sign = [r for r in recs if r["sign_d"] and key(r) not in used_cal]
    if left_sign:
        raise RuntimeError(f"unexpected leftover sign flips: {len(left_sign)}")
    left_mag = sorted([r for r in recs if r["mag"] and key(r) not in used_cal], key=lambda r: H("cal", *key(r)))
    left_oth = sorted([r for r in recs if r["other"] and key(r) not in used_cal], key=lambda r: H("cal", *key(r)))
    sel_cal = left_mag[:K_MAG] + left_oth[:K_OTHER]
    fy_pairs = sorted([(y, c) for y in (2000, 2001) for c in cats], key=lambda p: H("fy", *p))[:K_FY]
    yc_pairs = sorted([(y, c) for y in YEARS for c in cats], key=lambda p: H("yc", *p))[:K_YC]
    ym_pairs = sorted([(y, m) for y in YEARS for m in range(1, 13)], key=lambda p: H("ym", *p))[:K_YM]
    inc_cats = sorted(cats, key=lambda c: H("inc", c))[:K_INC]
    windows = [(("2002-08-01", "2002-08-31"), ("2001-08-01", "2001-08-31")),
               (("2002-11-01", "2002-11-30"), ("2001-11-01", "2001-11-30"))]
    tasks: list = []
    n = 0
    for r in sel_cal:
        n = add_calendar_triple(con, tasks, r, n)
    for y, c in fy_pairs:
        add_fy_category(con, tasks, y, c)
    for y, c in yc_pairs:
        add_year_category(con, tasks, y, c)
    for y, m in ym_pairs:
        add_year_month(con, tasks, y, m)
    sparse_counts = [add_sparse(con, tasks, used_items, used_brands, cur, prev) for cur, prev in windows]
    for c in inc_cats:
        add_incomplete(con, tasks, c, max_d)
    validate(con, tasks)
    con.close()
    prior_ids = {t["id"] for t in prior_tasks}
    prior_q = {(t["question_en"] or "").strip().lower() for t in prior_tasks}
    bad = [t["id"] for t in tasks if t["id"] in prior_ids or (t["question_en"] or "").strip().lower() in prior_q]
    if bad:
        raise RuntimeError(f"overlap with v0.1/v1: {bad}")
    counts = Counter()
    for t in tasks:
        counts[f"type:{t['type']}"] += 1
        counts[f"behavior:{t['gold_behavior']}"] += 1
        counts["sign_disagreement"] += bool(t.get("sign_disagreement"))
    selection = {
        "seed": SEED, "K": {"mag": K_MAG, "other": K_OTHER, "fy": K_FY, "yc": K_YC, "ym": K_YM, "sparse": K_SPARSE, "inc": K_INC},
        "pool": {"calendar_mag_leftover": len(left_mag), "calendar_other_leftover": len(left_oth), "calendar_sign_leftover": 0},
        "calendar": [{**{k: r[k] for k in ("yr", "moy", "cat", "cal_yoy", "r30_yoy", "gap")}, "stratum": "mag" if r["mag"] else "other"} for r in sel_cal],
        "fy_pairs": fy_pairs, "year_category_pairs": yc_pairs, "year_month_pairs": ym_pairs,
        "sparse_windows": windows, "sparse_counts_items_brands": sparse_counts, "incomplete_categories": inc_cats,
        "rule": "within each stratum, sort by sha256(seed|stratum|key) and take first K; never by gap or by any model output",
    }
    payload = {
        "name": "msb_p15_heldout_v2", "version": VER, "created_local": "2026-11-13 America/Los_Angeles",
        "evaluated": False, "owner": "paper15_MetricSemBench",
        "note": ("Paper 15 second official TPC-DS held-out (scale fold). Hash-frozen with evaluated=false BEFORE any score. "
                 "Disjoint from v0.1 and p15_heldout_v1 by id and question text. Model-blind hash selection. "
                 "Not a paper-13 official TEST fold."),
        "source": "DuckDB official dsdgen TPC-DS SF=1", "dictionary": DICTIONARY, "split_seed": SEED,
        "selection": selection, "n_tasks": len(tasks), "n_official_ta": len(tasks), "counts": dict(counts), "tasks": tasks,
    }
    payload["sha256"] = _payload_sha(payload)
    tmp = OUT.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")
    tmp.replace(OUT)
    print("wrote", OUT, "n=", len(tasks), "sha=", payload["sha256"], dict(counts), "sparse", sparse_counts)
    return payload


if __name__ == "__main__":
    build()
