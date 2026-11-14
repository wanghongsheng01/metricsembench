"""Build and hash-freeze Paper 15's official TPC-DS held-out TEST.

Pre-registered, model-blind, disjoint from the v0.1 diagnostic fixture.
Does NOT use paper-13 public-overlay official TEST folds, and does not
look at any model prediction when selecting items.

Selection rule (frozen before any paper-15 official score):
  Seed string: paper15_msb_tpcds_heldout_v1_seed_20261112
  Calendar triples: leftover complete (year, month, category) windows that
    are NOT in v0.1. There are ZERO leftover sign-disagreement triples
    (all three population flips are already in v0.1); the held-out is
    therefore drawn from (a) leftover same-sign magnitude-gap (>=2 pp)
    triples and (b) leftover ordinary complete decision-relevant triples.
    Within each stratum, items are sorted by sha256(seed|yr|moy|cat) and
    the first K are taken — NOT by maximizing the gap (no cherry-picking).
    K_mag = 8, K_other = 8. Each triple yields three tasks (clarify + two
    specified computes), same protocol as v0.1.
  Other axes: calendar years 1999 and 2002 (v0.1 used 2000 and 2001),
    same gold-SQL templates, values re-executed on official TPC-DS SF=1.
    Active-item snapshot is 30 June of that year. Channel-scope uses both
    years. Sparse refuse uses May 2002 vs May 2001, excluding item ids
    and brands already in v0.1.

evaluated=false at freeze. Official scoring happens in a later commit.
"""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from datetime import date
from pathlib import Path

import duckdb

from msb.build_tasks import (
    MONTH_NAME,
    make_task as _make_task_v01,
    month_first,
    month_last,
    q_yoy,
    rolling30,
    scalar,
    validate_and_dump as _unused,  # noqa: F401 — we reimplement dump
)
from msb.config import (
    DB_PATH,
    MIN_ABS_YOY,
    RESULTS_DIR,
    SPARSE_MIN_PRIOR_TICKETS,
    TASKS_DIR,
)
from msb.dictionary import DICTIONARY
from msb.forbidden_folds import assert_allowed_task_path

P15_VERSION = "p15_heldout_v1"
SEED = "paper15_msb_tpcds_heldout_v1_seed_20261112"
K_MAG = 8
K_OTHER = 8
V01 = TASKS_DIR / "msb_v0.1_tasks.json"
OUT = TASKS_DIR / "msb_p15_heldout_v1_tasks.json"
DOC = Path(__file__).resolve().parents[2] / "实验协议_与冻结折_p15_heldout_v1.md"
# also a data-side manifesto next to the JSON
OUT_DOC = TASKS_DIR / "MSB_P15_HELDOUT_V1.md"


def _make(tid: str, **kw):
    # Reuse v0.1 make_task then override version. make_task pops required keys.
    t = _make_task_v01(tid, **kw)
    t["version"] = P15_VERSION
    t["fold"] = "paper15_official_heldout_v1"
    t["split"] = "TEST"
    return t


def _sha_item(yr, moy, cat) -> str:
    s = f"{SEED}|{yr}|{moy}|{cat}"
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def _payload_sha(payload: dict) -> str:
    body = {k: v for k, v in payload.items() if k != "sha256"}
    return hashlib.sha256(
        (json.dumps(body, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n").encode()
    ).hexdigest()


def used_v01_calendar(tasks) -> set:
    used = set()
    for t in tasks:
        if t.get("subtype") == "month_vs_rolling30_yoy":
            m = t.get("metadata") or {}
            used.add((m.get("yr"), m.get("moy"), m.get("cat")))
    return used


def used_v01_sparse(tasks):
    items, brands = set(), set()
    for t in tasks:
        m = t.get("metadata") or {}
        if t.get("subtype") == "item_month_yoy_sparse_prior" and m.get("item_id"):
            items.add(m["item_id"])
        if t.get("subtype") == "brand_month_yoy_sparse_prior" and m.get("brand") is not None:
            brands.add((m.get("brand"), m.get("category")))
    return items, brands


def scan_calendar(con):
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
               c2.cal_amt, r2.r30_amt
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
    recs = []
    for yr, moy, cat, cal, r30, cal_ly, r30_ly in list(rows_overall) + list(rows_cat):
        cal, r30, cal_ly, r30_ly = map(float, (cal, r30, cal_ly, r30_ly))
        cal_yoy = (cal - cal_ly) / cal_ly
        r30_yoy = (r30 - r30_ly) / r30_ly
        sign_d = (cal - cal_ly) * (r30 - r30_ly) < 0 and abs(cal_yoy) >= MIN_ABS_YOY and abs(r30_yoy) >= MIN_ABS_YOY
        gap = abs(cal_yoy - r30_yoy)
        recs.append(
            dict(
                yr=int(yr), moy=int(moy), cat=cat, cal_yoy=cal_yoy, r30_yoy=r30_yoy,
                sign_d=sign_d, gap=gap,
                mag=(gap >= 0.02 and abs(cal_yoy) >= MIN_ABS_YOY and not sign_d),
                other=(
                    (abs(cal_yoy) >= MIN_ABS_YOY or abs(r30_yoy) >= MIN_ABS_YOY)
                    and not sign_d
                    and not (gap >= 0.02 and abs(cal_yoy) >= MIN_ABS_YOY)
                ),
            )
        )
    return recs


def add_calendar_triple(con, tasks, rec, n_start: int) -> int:
    yr, moy, cat = rec["yr"], rec["moy"], rec["cat"]
    cf, cl = month_first(yr, moy), month_last(yr, moy)
    pf, pl = month_first(yr - 1, moy), month_last(yr - 1, moy)
    rf, rl = rolling30(yr, moy)
    rpf, rpl = rolling30(yr - 1, moy)
    ex = f"i_category = '{cat}'" if cat else ""
    sql_cal = q_yoy(cf, cl, pf, pl, ex)
    sql_r30 = q_yoy(rf, rl, rpf, rpl, ex)
    v_cal, v_r30 = scalar(con, sql_cal), scalar(con, sql_r30)
    assert v_cal is not None and v_r30 is not None
    defs = [
        {"id": "calendar_month", "sql": sql_cal.strip(), "value": v_cal, "unit": "ratio"},
        {"id": "rolling_30", "sql": sql_r30.strip(), "value": v_r30, "unit": "ratio"},
    ]
    mon = MONTH_NAME[moy]
    sc = f" in the {cat} category" if cat else ""
    meta = {
        **{k: rec[k] for k in ("yr", "moy", "cat", "cal_yoy", "r30_yoy", "sign_d", "gap")},
        "calendar_span": [cf.isoformat(), cl.isoformat()],
        "rolling30_span": [rf.isoformat(), rl.isoformat()],
        "selection_hash": _sha_item(yr, moy, cat),
    }
    n = n_start
    n += 1
    tasks.append(_make(
        f"msb_{P15_VERSION}_cal_clarify_{n:03d}",
        type="calendar", subtype="month_vs_rolling30_yoy", gold_behavior="clarify",
        question_en=f"What was the year-over-year growth rate of store net sales{sc} for {mon} {yr}?",
        question_zh=f"{yr}年{moy}月门店净销售额{sc}的同比增长率是多少？",
        paired_definitions=defs, sign_disagreement=rec["sign_d"], metadata=meta,
    ))
    n += 1
    tasks.append(_make(
        f"msb_{P15_VERSION}_cal_compute_cal_{n:03d}",
        type="calendar", subtype="month_vs_rolling30_yoy", gold_behavior="compute",
        specified_definition="calendar_month",
        question_en=(
            f"What was the year-over-year growth rate of store net sales{sc} "
            f"for calendar month {mon} {yr} "
            f"({cf.isoformat()} to {cl.isoformat()} vs {pf.isoformat()} to {pl.isoformat()})?"
        ),
        question_zh=f"按自然月（{cf}–{cl} 对比 {pf}–{pl}），{yr}年{moy}月门店净销售额{sc}的同比是多少？",
        paired_definitions=defs, gold_sql=sql_cal.strip(), gold_value=v_cal, gold_unit="ratio",
        sign_disagreement=rec["sign_d"], metadata=meta,
    ))
    n += 1
    tasks.append(_make(
        f"msb_{P15_VERSION}_cal_compute_r30_{n:03d}",
        type="calendar", subtype="month_vs_rolling30_yoy", gold_behavior="compute",
        specified_definition="rolling_30",
        question_en=(
            f"What was the year-over-year growth rate of store net sales{sc} "
            f"for the rolling 30-day window ending {rl.isoformat()} "
            f"({rf.isoformat()} to {rl.isoformat()} vs {rpf.isoformat()} to {rpl.isoformat()})?"
        ),
        question_zh=f"按滚动30天（{rf}–{rl} 对比 {rpf}–{rpl}），门店净销售额{sc}的同比是多少？",
        paired_definitions=defs, gold_sql=sql_r30.strip(), gold_value=v_r30, gold_unit="ratio",
        sign_disagreement=rec["sign_d"], metadata=meta,
    ))
    return n


def add_other_axes(con, tasks, years=(1999, 2002)):
    # Lifecycle new-product share, currency, non-additive, return-rate, channel, active-item.
    for yr in years:
        sql_first = f"""
        WITH first_sale AS (
          SELECT i_item_id, MIN(d_date) AS first_d
          FROM msb_store_sales GROUP BY 1
        ),
        new_ids AS (SELECT i_item_id FROM first_sale WHERE year(first_d) = {yr})
        SELECT
          SUM(CASE WHEN n.i_item_id IS NOT NULL THEN ss.ss_net_paid ELSE 0 END) * 1.0
          / NULLIF(SUM(ss.ss_net_paid), 0)
        FROM msb_store_sales ss
        LEFT JOIN new_ids n ON n.i_item_id = ss.i_item_id
        WHERE ss.d_year = {yr}
        """
        sql_rec = f"""
        WITH new_ids AS (
          SELECT DISTINCT i_item_id FROM item
          WHERE i_rec_start_date IS NOT NULL AND year(i_rec_start_date) = {yr}
        )
        SELECT
          SUM(CASE WHEN n.i_item_id IS NOT NULL THEN ss.ss_net_paid ELSE 0 END) * 1.0
          / NULLIF(SUM(ss.ss_net_paid), 0)
        FROM msb_store_sales ss
        LEFT JOIN new_ids n ON n.i_item_id = ss.i_item_id
        WHERE ss.d_year = {yr}
        """
        v1, v2 = scalar(con, sql_first), scalar(con, sql_rec)
        if v1 is None or v2 is None:
            raise RuntimeError(f"lifecycle gold NULL for year {yr}")
        defs = [
            {"id": "first_sale_in_period", "sql": sql_first.strip(), "value": v1, "unit": "ratio"},
            {"id": "catalog_rec_start_in_period", "sql": sql_rec.strip(), "value": v2, "unit": "ratio"},
        ]
        meta = {"yr": yr, "gap": abs(v1 - v2)}
        tasks.append(_make(
            f"msb_{P15_VERSION}_life_clarify_newshare_{yr}",
            type="lifecycle", subtype="new_product_sales_share", gold_behavior="clarify",
            question_en=f"What share of store net sales in calendar year {yr} came from new products?",
            question_zh=f"{yr}自然年新品销售占门店净销售额的比例是多少？",
            paired_definitions=defs, metadata=meta,
        ))
        tasks.append(_make(
            f"msb_{P15_VERSION}_life_compute_firstsale_{yr}",
            type="lifecycle", subtype="new_product_sales_share", gold_behavior="compute",
            specified_definition="first_sale_in_period",
            question_en=(
                f"What share of store net sales in calendar year {yr} came from items whose "
                f"first store sale in the fixture falls in {yr}?"
            ),
            question_zh=f"{yr}年，以当年首次门店销售定义的新品，占门店净销售额的比例？",
            paired_definitions=defs, gold_sql=sql_first.strip(), gold_value=v1, gold_unit="ratio",
            metadata=meta,
        ))
        tasks.append(_make(
            f"msb_{P15_VERSION}_life_compute_recstart_{yr}",
            type="lifecycle", subtype="new_product_sales_share", gold_behavior="compute",
            specified_definition="catalog_rec_start_in_period",
            question_en=(
                f"What share of store net sales in calendar year {yr} came from items whose "
                f"catalog record start date (i_rec_start_date) falls in {yr}?"
            ),
            question_zh=f"{yr}年，目录记录开始日期在该年的商品，占当年门店净销售额的比例？",
            paired_definitions=defs, gold_sql=sql_rec.strip(), gold_value=v2, gold_unit="ratio",
            metadata=meta,
        ))

        snap = date(yr, 6, 30)
        sql_den_catalog = f"""
        WITH sold AS (
          SELECT DISTINCT i_item_id FROM msb_store_sales
          WHERE d_date BETWEEN DATE '{yr}-01-01' AND DATE '{yr}-12-31'
        ),
        catalog AS (
          SELECT DISTINCT i_item_id FROM item
          WHERE i_rec_start_date IS NOT NULL AND i_rec_start_date <= DATE '{snap}'
            AND (i_rec_end_date IS NULL OR i_rec_end_date >= DATE '{snap}')
        )
        SELECT (SELECT COUNT(*) FROM sold s JOIN catalog c ON s.i_item_id=c.i_item_id) * 1.0
             / NULLIF((SELECT COUNT(*) FROM catalog), 0)
        """
        sql_den_all = f"""
        WITH sold AS (
          SELECT DISTINCT i_item_id FROM msb_store_sales
          WHERE d_date BETWEEN DATE '{yr}-01-01' AND DATE '{yr}-12-31'
        ),
        all_items AS (SELECT DISTINCT i_item_id FROM item)
        SELECT (SELECT COUNT(*) FROM sold) * 1.0 / NULLIF((SELECT COUNT(*) FROM all_items), 0)
        """
        v_cat, v_all = scalar(con, sql_den_catalog), scalar(con, sql_den_all)
        if v_cat is None or v_all is None:
            raise RuntimeError(f"activerate gold NULL for year {yr}")
        defs_a = [
            {"id": "denominator_in_catalog", "sql": sql_den_catalog.strip(), "value": v_cat, "unit": "ratio"},
            {"id": "denominator_all_items", "sql": sql_den_all.strip(), "value": v_all, "unit": "ratio"},
        ]
        tasks.append(_make(
            f"msb_{P15_VERSION}_life_clarify_activerate_{yr}",
            type="lifecycle", subtype="active_item_rate_denominator", gold_behavior="clarify",
            question_en=f"What was the active-item rate of the catalog in calendar year {yr}?",
            question_zh=f"{yr}年的动销率是多少？",
            paired_definitions=defs_a,
            metadata={"yr": yr, "snapshot": snap.isoformat(), "gap": abs(v_cat - v_all)},
        ))
        tasks.append(_make(
            f"msb_{P15_VERSION}_life_compute_activerate_catalog_{yr}",
            type="lifecycle", subtype="active_item_rate_denominator", gold_behavior="compute",
            specified_definition="denominator_in_catalog",
            question_en=(
                f"What fraction of items in-catalog on {snap.isoformat()} "
                f"(i_rec_start_date <= snapshot and i_rec_end_date is null or >= snapshot) "
                f"had at least one store sale in calendar year {yr}?"
            ),
            question_zh=f"以{snap}在档商品为分母，{yr}年至少有一笔门店销售的动销率是多少？",
            paired_definitions=defs_a, gold_sql=sql_den_catalog.strip(), gold_value=v_cat, gold_unit="ratio",
            metadata={"yr": yr, "snapshot": snap.isoformat()},
        ))
        tasks.append(_make(
            f"msb_{P15_VERSION}_life_compute_activerate_all_{yr}",
            type="lifecycle", subtype="active_item_rate_denominator", gold_behavior="compute",
            specified_definition="denominator_all_items",
            question_en=(
                f"What fraction of all item IDs in the item table had at least one store sale "
                f"in calendar year {yr}?"
            ),
            question_zh=f"以商品表全部商品为分母，{yr}年至少有一笔门店销售的比例是多少？",
            paired_definitions=defs_a, gold_sql=sql_den_all.strip(), gold_value=v_all, gold_unit="ratio",
            metadata={"yr": yr},
        ))

        sql_raw = f"SELECT SUM(ss_net_paid) FROM msb_store_sales WHERE d_year = {yr}"
        sql_usd = f"SELECT SUM(net_paid_usd) FROM msb_store_sales WHERE d_year = {yr}"
        v_raw, v_usd = scalar(con, sql_raw), scalar(con, sql_usd)
        defs_c = [
            {"id": "raw_local_sum", "sql": sql_raw, "value": v_raw, "unit": "mixed_currency_amount",
             "note": "Illegal as a single-currency total; provided only to detect definition swap."},
            {"id": "converted_usd_sum", "sql": sql_usd, "value": v_usd, "unit": "usd",
             "note": "Legal under metricsem_fx_v1: local amounts times frozen fx_to_usd."},
        ]
        tasks.append(_make(
            f"msb_{P15_VERSION}_ccy_clarify_{yr}",
            type="currency", subtype="raw_vs_usd_converted", gold_behavior="clarify",
            question_en=f"What were total store net sales in calendar year {yr}?",
            question_zh=f"{yr}自然年门店净销售额合计是多少？",
            paired_definitions=defs_c, extensions=["metricsem_fx_v1"],
            metadata={"yr": yr, "raw": v_raw, "usd": v_usd, "rel_gap": abs(v_raw - v_usd) / v_usd},
        ))
        tasks.append(_make(
            f"msb_{P15_VERSION}_ccy_compute_usd_{yr}",
            type="currency", subtype="raw_vs_usd_converted", gold_behavior="compute",
            specified_definition="converted_usd_sum",
            question_en=(
                f"What were total store net sales in calendar year {yr} in USD after converting "
                f"each store's local currency with the frozen metricsem_fx_v1 rates?"
            ),
            question_zh=f"按 metricsem_fx_v1 汇率折算为美元后，{yr}年门店净销售额合计是多少？",
            paired_definitions=defs_c, gold_sql=sql_usd, gold_value=v_usd, gold_unit="usd",
            extensions=["metricsem_fx_v1"], metadata={"yr": yr},
        ))
        tasks.append(_make(
            f"msb_{P15_VERSION}_ccy_refuse_raw_as_usd_{yr}",
            type="currency", subtype="raw_sum_claimed_as_usd", gold_behavior="refuse",
            refuse_reason="currency_mix_no_fx",
            question_en=(
                f"Report a single USD total of store net sales for calendar year {yr} "
                f"by summing ss_net_paid across all stores without conversion "
                f"(treat every local amount as if it were already USD)."
            ),
            question_zh=f"把各店本地币种的 ss_net_paid 直接相加，作为{yr}年以美元计的门店净销售总额。",
            paired_definitions=defs_c, extensions=["metricsem_fx_v1"],
            metadata={"yr": yr, "illegal_value_if_executed": v_raw},
        ))

        sql_overall = f"""
        SELECT SUM(ss_net_paid) * 1.0 / NULLIF(COUNT(DISTINCT ss_ticket_number), 0)
        FROM msb_store_sales WHERE d_year = {yr}
        """
        sql_sum_store = f"""
        SELECT SUM(aov) FROM (
          SELECT ss_store_sk,
                 SUM(ss_net_paid) * 1.0 / NULLIF(COUNT(DISTINCT ss_ticket_number), 0) AS aov
          FROM msb_store_sales WHERE d_year = {yr}
          GROUP BY ss_store_sk
        )
        """
        v_ov, v_sum = scalar(con, sql_overall), scalar(con, sql_sum_store)
        defs_n = [
            {"id": "overall_aov", "sql": sql_overall.strip(), "value": v_ov, "unit": "amount_per_ticket"},
            {"id": "sum_of_store_aovs", "sql": sql_sum_store.strip(), "value": v_sum, "unit": "illegal_sum_of_rates"},
        ]
        tasks.append(_make(
            f"msb_{P15_VERSION}_nadd_compute_overall_aov_{yr}",
            type="non_additive", subtype="aov", gold_behavior="compute",
            specified_definition="overall_aov",
            question_en=(
                f"What was the overall average order value of store sales in calendar year {yr}, "
                f"defined as total ss_net_paid divided by the number of distinct tickets?"
            ),
            question_zh=f"{yr}自然年门店总体客单价（净销售额 / 去重小票数）是多少？",
            paired_definitions=defs_n, gold_sql=sql_overall.strip(), gold_value=v_ov,
            gold_unit="amount_per_ticket", metadata={"yr": yr},
        ))
        tasks.append(_make(
            f"msb_{P15_VERSION}_nadd_refuse_sum_store_aov_{yr}",
            type="non_additive", subtype="aov_illegal_sum", gold_behavior="refuse",
            refuse_reason="non_additive_sum",
            question_en=(
                f"Report the total average order value for calendar year {yr} "
                f"by summing the per-store average order values."
            ),
            question_zh=f"把各门店{yr}年客单价相加，作为该年总客单价。",
            paired_definitions=defs_n,
            metadata={"yr": yr, "illegal_value_if_executed": v_sum, "overall_aov": v_ov},
        ))
        sql_overall_m = f"""
        SELECT SUM(ss_net_profit) * 1.0 / NULLIF(SUM(ss_net_paid), 0)
        FROM msb_store_sales WHERE d_year = {yr}
        """
        sql_sum_m = f"""
        SELECT SUM(m) FROM (
          SELECT ss_store_sk, SUM(ss_net_profit) * 1.0 / NULLIF(SUM(ss_net_paid), 0) AS m
          FROM msb_store_sales WHERE d_year = {yr} GROUP BY ss_store_sk
        )
        """
        v_om, v_sm = scalar(con, sql_overall_m), scalar(con, sql_sum_m)
        defs_m = [
            {"id": "overall_margin_rate", "sql": sql_overall_m.strip(), "value": v_om, "unit": "ratio"},
            {"id": "sum_of_store_margin_rates", "sql": sql_sum_m.strip(), "value": v_sm, "unit": "illegal_sum_of_rates"},
        ]
        tasks.append(_make(
            f"msb_{P15_VERSION}_nadd_compute_margin_{yr}",
            type="non_additive", subtype="margin_rate", gold_behavior="compute",
            specified_definition="overall_margin_rate",
            question_en=(
                f"What was the overall net-profit margin rate of store sales in calendar year {yr}, "
                f"defined as SUM(ss_net_profit) / SUM(ss_net_paid)?"
            ),
            question_zh=f"{yr}年门店总体净利润率（SUM(ss_net_profit)/SUM(ss_net_paid)）是多少？",
            paired_definitions=defs_m, gold_sql=sql_overall_m.strip(), gold_value=v_om, gold_unit="ratio",
            metadata={"yr": yr},
        ))
        tasks.append(_make(
            f"msb_{P15_VERSION}_nadd_refuse_sum_margin_{yr}",
            type="non_additive", subtype="margin_rate_illegal_sum", gold_behavior="refuse",
            refuse_reason="non_additive_sum",
            question_en=(
                f"Report the total net-profit margin rate for calendar year {yr} "
                f"by summing the per-store margin rates."
            ),
            question_zh=f"把各门店{yr}年净利润率相加，作为该年总利润率。",
            paired_definitions=defs_m,
            metadata={"yr": yr, "illegal_value_if_executed": v_sm, "overall": v_om},
        ))

        sql_amt = f"""
        SELECT (SELECT SUM(sr_return_amt) FROM msb_store_returns WHERE d_year = {yr}) * 1.0
             / NULLIF((SELECT SUM(ss_ext_sales_price) FROM msb_store_sales WHERE d_year = {yr}), 0)
        """
        sql_qty = f"""
        SELECT (SELECT SUM(sr_return_quantity) FROM msb_store_returns WHERE d_year = {yr}) * 1.0
             / NULLIF((SELECT SUM(ss_quantity) FROM msb_store_sales WHERE d_year = {yr}), 0)
        """
        v_a, v_q = scalar(con, sql_amt), scalar(con, sql_qty)
        defs_r = [
            {"id": "return_rate_amount", "sql": sql_amt.strip(), "value": v_a, "unit": "ratio"},
            {"id": "return_rate_quantity", "sql": sql_qty.strip(), "value": v_q, "unit": "ratio"},
        ]
        tasks.append(_make(
            f"msb_{P15_VERSION}_den_clarify_return_{yr}",
            type="denominator", subtype="return_rate_amt_vs_qty", gold_behavior="clarify",
            question_en=f"What was the store return rate in calendar year {yr}?",
            question_zh=f"{yr}年门店退货率是多少？",
            paired_definitions=defs_r, metadata={"yr": yr, "gap": abs((v_a or 0) - (v_q or 0))},
        ))
        tasks.append(_make(
            f"msb_{P15_VERSION}_den_compute_return_amt_{yr}",
            type="denominator", subtype="return_rate_amt_vs_qty", gold_behavior="compute",
            specified_definition="return_rate_amount",
            question_en=(
                f"What was the store return rate in calendar year {yr}, defined as "
                f"SUM(sr_return_amt) / SUM(ss_ext_sales_price)?"
            ),
            question_zh=f"{yr}年按金额计的退货率（退货金额/销售金额）是多少？",
            paired_definitions=defs_r, gold_sql=sql_amt.strip(), gold_value=v_a, gold_unit="ratio",
            metadata={"yr": yr},
        ))
        tasks.append(_make(
            f"msb_{P15_VERSION}_den_compute_return_qty_{yr}",
            type="denominator", subtype="return_rate_amt_vs_qty", gold_behavior="compute",
            specified_definition="return_rate_quantity",
            question_en=(
                f"What was the store return rate in calendar year {yr}, defined as "
                f"SUM(sr_return_quantity) / SUM(ss_quantity)?"
            ),
            question_zh=f"{yr}年按件数计的退货率（退货件数/销售件数）是多少？",
            paired_definitions=defs_r, gold_sql=sql_qty.strip(), gold_value=v_q, gold_unit="ratio",
            metadata={"yr": yr},
        ))

        sql_store = f"SELECT SUM(ss_net_paid) FROM msb_store_sales WHERE d_year = {yr}"
        sql_allch = f"""
        SELECT
          (SELECT SUM(ss_net_paid) FROM msb_store_sales WHERE d_year = {yr})
        + (SELECT SUM(ws_net_paid) FROM msb_web_sales WHERE d_year = {yr})
        + (SELECT SUM(cs_net_paid) FROM msb_catalog_sales WHERE d_year = {yr})
        """
        v_s, v_ac = scalar(con, sql_store), scalar(con, sql_allch)
        defs_ch = [
            {"id": "store_channel_only", "sql": sql_store, "value": v_s, "unit": "amount"},
            {"id": "store_web_catalog", "sql": sql_allch.strip(), "value": v_ac, "unit": "amount"},
        ]
        tasks.append(_make(
            f"msb_{P15_VERSION}_den_clarify_channel_{yr}",
            type="denominator", subtype="channel_scope", gold_behavior="clarify",
            question_en=f"What were total net sales in calendar year {yr}?",
            question_zh=f"{yr}年净销售总额是多少？",
            paired_definitions=defs_ch, metadata={"yr": yr, "rel_gap": abs(v_ac - v_s) / v_s},
        ))
        tasks.append(_make(
            f"msb_{P15_VERSION}_den_compute_store_{yr}",
            type="denominator", subtype="channel_scope", gold_behavior="compute",
            specified_definition="store_channel_only",
            question_en=f"What were total store-channel net sales (store_sales only) in calendar year {yr}?",
            question_zh=f"{yr}年仅门店渠道（store_sales）净销售额是多少？",
            paired_definitions=defs_ch, gold_sql=sql_store, gold_value=v_s, gold_unit="amount",
            metadata={"yr": yr},
        ))
        tasks.append(_make(
            f"msb_{P15_VERSION}_den_compute_allch_{yr}",
            type="denominator", subtype="channel_scope", gold_behavior="compute",
            specified_definition="store_web_catalog",
            question_en=(
                f"What were total net sales across store, web, and catalog channels "
                f"(SUM ss_net_paid + ws_net_paid + cs_net_paid) in calendar year {yr}?"
            ),
            question_zh=f"{yr}年门店+网站+目录三渠道净销售额合计是多少？",
            paired_definitions=defs_ch, gold_sql=sql_allch.strip(), gold_value=v_ac, gold_unit="amount",
            metadata={"yr": yr},
        ))


def add_sparse(con, tasks, used_items, used_brands):
    # May 2002 vs May 2001 — a month unused by v0.1 sparse (which used Oct 2001 and Feb 2001).
    rows = con.execute(
        f"""
        WITH cur AS (
          SELECT i_item_id, i_category, COUNT(DISTINCT ss_ticket_number) AS tickets, SUM(ss_net_paid) AS amt
          FROM msb_store_sales
          WHERE d_date BETWEEN DATE '2002-05-01' AND DATE '2002-05-31'
          GROUP BY 1,2
        ),
        prev AS (
          SELECT i_item_id, COUNT(DISTINCT ss_ticket_number) AS tickets, SUM(ss_net_paid) AS amt
          FROM msb_store_sales
          WHERE d_date BETWEEN DATE '2001-05-01' AND DATE '2001-05-31'
          GROUP BY 1
        )
        SELECT c.i_item_id, c.i_category, c.tickets, c.amt,
               COALESCE(p.tickets, 0) AS prev_tickets, COALESCE(p.amt, 0) AS prev_amt
        FROM cur c
        LEFT JOIN prev p ON p.i_item_id = c.i_item_id
        WHERE c.tickets >= 10
          AND COALESCE(p.tickets, 0) < {SPARSE_MIN_PRIOR_TICKETS}
        ORDER BY COALESCE(p.tickets, 0), c.tickets DESC, c.i_item_id
        """
    ).fetchall()
    kept = [r for r in rows if r[0] not in used_items][:8]
    # Pre-registered window is May 2002 vs May 2001 (unused by v0.1 sparse).
    # Take every leftover item that meets the sparsity gate, capped at 8; do not
    # shop for another month to inflate n.
    if not kept:
        raise RuntimeError("no leftover sparse items in the pre-registered May 2002 window")
    for i, (item_id, cat, cur_t, cur_a, prev_t, prev_a) in enumerate(kept, 1):
        reason = "sparse_prior" if prev_t > 0 else "undefined_yoy"
        tasks.append(_make(
            f"msb_{P15_VERSION}_sparse_refuse_item_{i:03d}",
            type="sparse_completeness", subtype="item_month_yoy_sparse_prior",
            gold_behavior="refuse", refuse_reason=reason,
            question_en=(
                f"What was the year-over-year growth rate of store net sales for item {item_id} "
                f"in calendar month May 2002 (versus May 2001)?"
            ),
            question_zh=f"商品 {item_id} 在 2002年5月相对 2001年5月的门店净销售同比是多少？",
            metadata={
                "item_id": item_id, "category": cat,
                "cur_tickets": int(cur_t), "prev_tickets": int(prev_t),
                "cur_amt": float(cur_a), "prev_amt": float(prev_a),
                "sparse_min_prior_tickets": SPARSE_MIN_PRIOR_TICKETS,
                "window": ["2002-05-01", "2002-05-31"],
                "prior_window": ["2001-05-01", "2001-05-31"],
            },
        ))

    rows2 = con.execute(
        f"""
        WITH cur AS (
          SELECT i_brand, i_category, COUNT(DISTINCT ss_ticket_number) AS tickets, SUM(ss_net_paid) AS amt
          FROM msb_store_sales
          WHERE d_date BETWEEN DATE '2002-05-01' AND DATE '2002-05-31'
            AND i_category IS NOT NULL AND i_brand IS NOT NULL
          GROUP BY 1,2
        ),
        prev AS (
          SELECT i_brand, i_category, COUNT(DISTINCT ss_ticket_number) AS tickets, SUM(ss_net_paid) AS amt
          FROM msb_store_sales
          WHERE d_date BETWEEN DATE '2001-05-01' AND DATE '2001-05-31'
            AND i_category IS NOT NULL AND i_brand IS NOT NULL
          GROUP BY 1,2
        )
        SELECT c.i_brand, c.i_category, c.tickets, c.amt,
               COALESCE(p.tickets, 0), COALESCE(p.amt, 0)
        FROM cur c LEFT JOIN prev p ON p.i_brand=c.i_brand AND p.i_category=c.i_category
        WHERE c.tickets >= 10 AND COALESCE(p.tickets, 0) < {SPARSE_MIN_PRIOR_TICKETS}
        ORDER BY COALESCE(p.tickets,0), c.tickets DESC, c.i_brand
        """
    ).fetchall()
    kept2 = [r for r in rows2 if (r[0], r[1]) not in used_brands][:4]
    if not kept2:
        raise RuntimeError("no leftover sparse brands in the pre-registered May 2002 window")
    for i, (brand, cat, cur_t, cur_a, prev_t, prev_a) in enumerate(kept2, 1):
        tasks.append(_make(
            f"msb_{P15_VERSION}_sparse_refuse_brand_{i:03d}",
            type="sparse_completeness", subtype="brand_month_yoy_sparse_prior",
            gold_behavior="refuse",
            refuse_reason="sparse_prior" if prev_t > 0 else "undefined_yoy",
            question_en=(
                f"What was the year-over-year growth rate of store net sales for brand {brand!r} "
                f"in the {cat} category for calendar month May 2002?"
            ),
            question_zh=f"{cat} 类目下品牌 {brand} 在 2002年5月的门店净销售同比是多少？",
            metadata={
                "brand": brand, "category": cat,
                "cur_tickets": int(cur_t), "prev_tickets": int(prev_t),
                "cur_amt": float(cur_a), "prev_amt": float(prev_a),
                "window": ["2002-05-01", "2002-05-31"],
            },
        ))


def validate(con, tasks):
    errors = []
    ids = [t["id"] for t in tasks]
    if len(ids) != len(set(ids)):
        errors.append("duplicate ids")
    for t in tasks:
        for d in t.get("paired_definitions") or []:
            if not d.get("sql"):
                continue
            v = scalar(con, d["sql"])
            if v is None:
                errors.append(f"{t['id']} def {d['id']} NULL")
                continue
            if abs(v - d["value"]) > max(1e-6, 1e-8 * abs(d["value"])):
                errors.append(f"{t['id']} def {d['id']} drift {d['value']} vs {v}")
        if t["gold_behavior"] == "compute":
            if t.get("gold_sql") is None or t.get("gold_value") is None:
                errors.append(f"{t['id']} compute missing gold")
            else:
                v = scalar(con, t["gold_sql"])
                if v is None or abs(v - t["gold_value"]) > max(1e-6, 1e-8 * abs(t["gold_value"])):
                    errors.append(f"{t['id']} gold_sql drift {t['gold_value']} vs {v}")
        if t["gold_behavior"] == "refuse" and not t.get("refuse_reason"):
            errors.append(f"{t['id']} refuse missing reason")
        if t["gold_behavior"] == "clarify" and len(t.get("paired_definitions") or []) < 2:
            errors.append(f"{t['id']} clarify needs two definitions")
    if errors:
        raise RuntimeError("validation failed:\n" + "\n".join(errors))


def _counts(tasks):
    c = Counter()
    for t in tasks:
        c[f"type:{t['type']}"] += 1
        c[f"behavior:{t['gold_behavior']}"] += 1
        if t.get("sign_disagreement"):
            c["sign_disagreement"] += 1
    return dict(c)


def build():
    assert_allowed_task_path(V01)
    v01 = json.loads(V01.read_text(encoding="utf-8"))
    v01_tasks = v01["tasks"]
    used_cal = used_v01_calendar(v01_tasks)
    used_items, used_brands = used_v01_sparse(v01_tasks)

    con = duckdb.connect(str(DB_PATH), read_only=True)
    recs = scan_calendar(con)
    leftover_sign = [r for r in recs if r["sign_d"] and (r["yr"], r["moy"], r["cat"]) not in used_cal]
    leftover_mag = [r for r in recs if r["mag"] and (r["yr"], r["moy"], r["cat"]) not in used_cal]
    leftover_other = [r for r in recs if r["other"] and (r["yr"], r["moy"], r["cat"]) not in used_cal]
    if leftover_sign:
        raise RuntimeError(
            f"unexpected leftover sign flips ({len(leftover_sign)}); "
            "revisit selection — population analysis claimed zero leftover flips"
        )
    leftover_mag.sort(key=lambda r: _sha_item(r["yr"], r["moy"], r["cat"]))
    leftover_other.sort(key=lambda r: _sha_item(r["yr"], r["moy"], r["cat"]))
    selected_mag = leftover_mag[:K_MAG]
    selected_other = leftover_other[:K_OTHER]
    selection_log = {
        "seed": SEED,
        "K_mag": K_MAG,
        "K_other": K_OTHER,
        "n_leftover_sign": 0,
        "n_leftover_mag": len(leftover_mag),
        "n_leftover_other": len(leftover_other),
        "selected_mag": [
            {k: r[k] for k in ("yr", "moy", "cat", "cal_yoy", "r30_yoy", "gap")} | {"hash": _sha_item(r["yr"], r["moy"], r["cat"])}
            for r in selected_mag
        ],
        "selected_other": [
            {k: r[k] for k in ("yr", "moy", "cat", "cal_yoy", "r30_yoy", "gap")} | {"hash": _sha_item(r["yr"], r["moy"], r["cat"])}
            for r in selected_other
        ],
        "rule": "within stratum, sort by sha256(seed|yr|moy|cat), take first K; not by gap",
    }

    tasks = []
    n = 0
    for rec in selected_mag + selected_other:
        n = add_calendar_triple(con, tasks, rec, n)
    add_other_axes(con, tasks, years=(1999, 2002))
    add_sparse(con, tasks, used_items, used_brands)
    validate(con, tasks)
    con.close()

    # Overlap checks vs v0.1
    v01_ids = {t["id"] for t in v01_tasks}
    v01_q = {(t["question_en"] or "").strip().lower() for t in v01_tasks}
    overlap_id = [t["id"] for t in tasks if t["id"] in v01_ids]
    overlap_q = [t["id"] for t in tasks if (t["question_en"] or "").strip().lower() in v01_q]
    if overlap_id or overlap_q:
        raise RuntimeError(f"overlap with v0.1: ids={overlap_id} questions={overlap_q}")

    counts = _counts(tasks)
    payload = {
        "name": "msb_p15_heldout_v1",
        "version": P15_VERSION,
        "created_local": "2026-11-12 America/Los_Angeles",
        "evaluated": False,
        "owner": "paper15_MetricSemBench",
        "note": (
            "Paper 15 official TPC-DS held-out TEST. Hash-frozen with evaluated=false "
            "BEFORE any paper-15 official score. Disjoint from v0.1 by (year, month, category) "
            "for calendar tasks, by year (1999/2002 vs 2000/2001) for other axes, and by "
            "item/brand plus month (May 2002) for sparse refuse. Selection is model-blind "
            "and hash-based (seed paper15_msb_tpcds_heldout_v1_seed_20261112). "
            "Not a paper-13 official TEST fold; v4 (dacc85f) and v5 (7945db0) were not used."
        ),
        "source": "DuckDB official dsdgen TPC-DS SF=1",
        "dictionary": DICTIONARY,
        "split_seed": SEED,
        "selection": selection_log,
        "parent_v01_n": v01["n_tasks"],
        "n_tasks": len(tasks),
        "n_official_ta": len(tasks),
        "counts": counts,
        "tasks": tasks,
    }
    sha = _payload_sha(payload)
    payload["sha256"] = sha
    # confirm
    assert _payload_sha(payload) == sha

    TASKS_DIR.mkdir(parents=True, exist_ok=True)
    # write atomically
    tmp = OUT.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")
    tmp.replace(OUT)
    # The sha is over payload with indent=2 sort_keys=True, which may differ from
    # the file as written (insertion order, no sort). Record both. Official sha is
    # the sort_keys canonical form stored in the sha256 field (same convention as v4).
    assert_allowed_task_path(OUT)

    n_comp = counts.get("behavior:compute", 0)
    n_cl = counts.get("behavior:clarify", 0)
    n_rf = counts.get("behavior:refuse", 0)
    doc = f"""# Paper 15 official TPC-DS held-out TEST (`{P15_VERSION}`)

**Date:** 2026-11-12, America/Los_Angeles. **Hashed before any paper-15 official score.**
SHA-256 `{sha}`. `evaluated=false` at freeze.
n={len(tasks)} (compute {n_comp} / clarify {n_cl} / refuse {n_rf}). Official TA denominator = {len(tasks)}.

## Why this fold

- The v0.1 85-item fixture is a **diagnostic / template** set: it preferentially includes the
  three population sign-flips, and a dictionary-grounded reference protocol reaches TA 100%
  on it. Those numbers are reported, with CIs, but they are not a held-out generalization claim.
- This fold is Paper 15's **own official TEST**. It is disjoint from v0.1, model-blind, and
  hash-frozen before any official score. It does **not** use, slice, or rescore paper-13
  official public-overlay TEST folds (v2 TEST `e021e41e…`, v3 `06c70d29…`, v4 `3f595525…` /
  commit dacc85f, v5 FALLBACK `d57a673f…` / commit 7945db0).
- There are **zero leftover sign-disagreement triples** after v0.1 (population: 3 of 528
  complete triples). Claiming a held-out "full of sign flips" would require inventing them.
  The held-out is therefore drawn from leftover *same-sign* magnitude-gap months and
  ordinary complete months, plus leftover years (1999, 2002) on the other semantic axes.
  Sign-flip *prevalence* is a first-class population result, reported separately.

## Selection (pre-registered)

Seed: `{SEED}`.

Calendar: leftover complete (year, month, category) triples not in v0.1. Within the
magnitude stratum (gap ≥ 2 pp, same sign, |calendar YoY| ≥ 1 pp) and the ordinary
decision-relevant stratum, items are sorted by `sha256(seed|yr|moy|cat)` and the first
{K_MAG} / {K_OTHER} are taken. **Not** sorted by gap. Leftover pool: magnitude {len(leftover_mag)}, ordinary {len(leftover_other)}, sign 0.

Other axes: years 1999 and 2002 (v0.1 used 2000 and 2001). Gold SQL is re-executed on
official TPC-DS SF=1; values are not invented. Sparse refuse uses May 2002 vs May 2001
and excludes v0.1 item ids and brands.

## Scoring (required)

Official tables **must** report bootstrap 95% CIs (10,000 resamples, seed `20261112`)
and paired McNemar mid-p / paired bootstrap for headline contrasts (`msb.public_stats`
and `msb.paper15_stats`). Best bold, second underlined, W/T/L.

Paper 15 is an EA&B benchmark: the "gate" is whether the diagnostic claims hold on
this held-out and on the public overlay (EX ranking inversion; compute-vs-clarify-vs-refuse
profiles of strong published systems and frontier LLMs), not whether a sister-paper
method is #1.

## What this is not

- Not a second pass on v0.1, and not a paper-13 official TEST.
- Not to be used for prompt or threshold tuning after this freeze. Develop only on
  DEV (v0.1 + already-collected public overlay v1 DEV-style analyses). Evaluate this
  fold **once** after the protocol (including frontier-model prompts and reasoning
  settings) is frozen.
"""
    OUT_DOC.write_text(doc, encoding="utf-8")
    print("wrote", OUT, "n=", len(tasks), "sha=", sha, "counts=", counts)
    print("selection mag:", selection_log["selected_mag"])
    print("selection other:", selection_log["selected_other"])
    return OUT, sha, payload


if __name__ == "__main__":
    build()
