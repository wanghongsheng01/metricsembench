"""Build MetricSemBench v0.1 tasks from official TPC-DS SF=1. Gold values are computed, not invented."""
from __future__ import annotations

import calendar
import json
from datetime import date, timedelta
from typing import Any

import duckdb

from msb.config import (
    DB_PATH,
    MIN_ABS_YOY,
    RETAIL_FY_START_MONTH,
    SPARSE_MIN_PRIOR_TICKETS,
    TASKS_DIR,
    VERSION,
)
from msb.dictionary import DICTIONARY
from msb.generate_db import generate

MONTH_NAME = {
    1: "January", 2: "February", 3: "March", 4: "April",
    5: "May", 6: "June", 7: "July", 8: "August",
    9: "September", 10: "October", 11: "November", 12: "December",
}


def month_last(y: int, m: int) -> date:
    return date(y, m, calendar.monthrange(y, m)[1])


def month_first(y: int, m: int) -> date:
    return date(y, m, 1)


def rolling30(y: int, m: int) -> tuple[date, date]:
    end = month_last(y, m)
    return end - timedelta(days=29), end


def retail_fy_span(y: int) -> tuple[date, date]:
    return date(y, RETAIL_FY_START_MONTH, 1), date(y + 1, RETAIL_FY_START_MONTH, 1) - timedelta(days=1)


def scalar(con: duckdb.DuckDBPyConnection, sql: str) -> float | None:
    v = con.execute(sql).fetchone()[0]
    if v is None:
        return None
    return float(v)


def q_amt(date_from: date, date_to: date, extra: str = "", col: str = "ss_net_paid") -> str:
    extra_sql = f" AND ({extra})" if extra else ""
    return (
        f"SELECT SUM({col}) FROM msb_store_sales "
        f"WHERE d_date BETWEEN DATE '{date_from.isoformat()}' AND DATE '{date_to.isoformat()}'{extra_sql}"
    )


def q_yoy(cur_from, cur_to, prev_from, prev_to, extra: str = "", col: str = "ss_net_paid") -> str:
    e = f" AND ({extra})" if extra else ""
    return f"""
    WITH cur AS (
      SELECT SUM({col}) AS amt FROM msb_store_sales
      WHERE d_date BETWEEN DATE '{cur_from}' AND DATE '{cur_to}'{e}
    ),
    prev AS (
      SELECT SUM({col}) AS amt FROM msb_store_sales
      WHERE d_date BETWEEN DATE '{prev_from}' AND DATE '{prev_to}'{e}
    )
    SELECT (cur.amt - prev.amt) * 1.0 / NULLIF(prev.amt, 0) FROM cur, prev
    """


def q_tickets(d_from, d_to, extra: str = "") -> str:
    e = f" AND ({extra})" if extra else ""
    return (
        f"SELECT COUNT(DISTINCT ss_ticket_number) FROM msb_store_sales "
        f"WHERE d_date BETWEEN DATE '{d_from}' AND DATE '{d_to}'{e}"
    )


def make_task(tid: str, **kw) -> dict[str, Any]:
    t = {
        "id": tid,
        "version": VERSION,
        "source": "tpcds_sf1_dsdgen_official",
        "extensions": [],
        "type": kw.pop("type"),
        "subtype": kw.pop("subtype"),
        "gold_behavior": kw.pop("gold_behavior"),
        "question_en": kw.pop("question_en"),
        "question_zh": kw.pop("question_zh", ""),
        "paired_definitions": kw.pop("paired_definitions", []),
        "specified_definition": kw.pop("specified_definition", None),
        "gold_sql": kw.pop("gold_sql", None),
        "gold_value": kw.pop("gold_value", None),
        "gold_unit": kw.pop("gold_unit", None),
        "refuse_reason": kw.pop("refuse_reason", None),
        "sign_disagreement": kw.pop("sign_disagreement", False),
        "metadata": kw.pop("metadata", {}),
    }
    t.update(kw)
    return t


def _period_complete(con, start: date, end: date) -> bool:
    mx = con.execute("SELECT max(d_date), min(d_date) FROM msb_store_sales").fetchone()
    max_d, min_d = mx[0], mx[1]
    return min_d <= start and max_d >= end


def build_calendar(con, tasks: list) -> None:
    # Scan overall (cat is NULL = all categories) and by category.
    rows_overall = con.execute(
        """
        WITH daily AS (
          SELECT d_date AS dt, d_year, d_moy, SUM(ss_net_paid) AS amt
          FROM msb_store_sales
          GROUP BY 1,2,3
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
        SELECT c.yr, c.moy, NULL AS cat, c.cal_amt, r.r30_amt,
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
          FROM msb_store_sales
          WHERE i_category IS NOT NULL
          GROUP BY 1,2,3,4
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
        SELECT c.yr, c.moy, c.cat, c.cal_amt, r.r30_amt,
               c2.cal_amt AS cal_ly, r2.r30_amt AS r30_ly
        FROM cal c
        JOIN r30 r ON c.yr=r.yr AND c.moy=r.moy AND c.cat IS NOT DISTINCT FROM r.cat
        JOIN cal c2 ON c2.yr=c.yr-1 AND c2.moy=c.moy AND c2.cat IS NOT DISTINCT FROM c.cat
        JOIN r30 r2 ON r2.yr=c.yr-1 AND r2.moy=c.moy AND r2.cat IS NOT DISTINCT FROM r.cat
        WHERE c.yr BETWEEN 1999 AND 2002 AND c2.cal_amt > 0 AND r2.r30_amt > 0
        """
    ).fetchall()
    rows = list(rows_overall) + list(rows_cat)

    flagship = []
    magnitude = []
    for yr, moy, cat, cal, r30, cal_ly, r30_ly in rows:
        cal, r30, cal_ly, r30_ly = map(float, (cal, r30, cal_ly, r30_ly))
        cal_yoy = (cal - cal_ly) / cal_ly
        r30_yoy = (r30 - r30_ly) / r30_ly
        sign_d = (cal - cal_ly) * (r30 - r30_ly) < 0 and abs(cal_yoy) >= MIN_ABS_YOY and abs(r30_yoy) >= MIN_ABS_YOY
        rec = dict(yr=int(yr), moy=int(moy), cat=cat, cal_yoy=cal_yoy, r30_yoy=r30_yoy,
                   sign_d=sign_d, gap=abs(cal_yoy - r30_yoy))
        if sign_d:
            flagship.append(rec)
        elif rec["gap"] >= 0.02 and abs(cal_yoy) >= MIN_ABS_YOY:
            magnitude.append(rec)

    flagship.sort(key=lambda r: -abs(r["cal_yoy"] - r["r30_yoy"]))
    magnitude.sort(key=lambda r: -r["gap"])

    def extra(cat):
        return f"i_category = '{cat}'" if cat else ""

    def scope(cat):
        return f" in the {cat} category" if cat else ""

    n = 0
    selected = flagship + magnitude[:8]
    seen = set()
    for rec in selected:
        key = (rec["yr"], rec["moy"], rec["cat"])
        if key in seen:
            continue
        seen.add(key)
        yr, moy, cat = rec["yr"], rec["moy"], rec["cat"]
        cf, cl = month_first(yr, moy), month_last(yr, moy)
        pf, pl = month_first(yr - 1, moy), month_last(yr - 1, moy)
        rf, rl = rolling30(yr, moy)
        rpf, rpl = rolling30(yr - 1, moy)
        ex = extra(cat)
        sql_cal = q_yoy(cf, cl, pf, pl, ex)
        sql_r30 = q_yoy(rf, rl, rpf, rpl, ex)
        v_cal = scalar(con, sql_cal)
        v_r30 = scalar(con, sql_r30)
        assert v_cal is not None and v_r30 is not None
        defs = [
            {"id": "calendar_month", "sql": sql_cal.strip(), "value": v_cal, "unit": "ratio"},
            {"id": "rolling_30", "sql": sql_r30.strip(), "value": v_r30, "unit": "ratio"},
        ]
        mon = MONTH_NAME[moy]
        sc = scope(cat)
        meta = {**rec, "calendar_span": [cf.isoformat(), cl.isoformat()],
                "rolling30_span": [rf.isoformat(), rl.isoformat()]}

        # Underspecified: must clarify.
        n += 1
        tasks.append(make_task(
            f"msb_{VERSION}_cal_clarify_{n:03d}",
            type="calendar", subtype="month_vs_rolling30_yoy",
            gold_behavior="clarify",
            question_en=(
                f"What was the year-over-year growth rate of store net sales{sc} for {mon} {yr}?"
            ),
            question_zh=f"{yr}年{moy}月门店净销售额{sc}的同比增长率是多少？",
            paired_definitions=defs,
            sign_disagreement=rec["sign_d"],
            metadata=meta,
        ))
        # Specified calendar: compute A
        n += 1
        tasks.append(make_task(
            f"msb_{VERSION}_cal_compute_cal_{n:03d}",
            type="calendar", subtype="month_vs_rolling30_yoy",
            gold_behavior="compute",
            specified_definition="calendar_month",
            question_en=(
                f"What was the year-over-year growth rate of store net sales{sc} "
                f"for calendar month {mon} {yr} "
                f"({cf.isoformat()} to {cl.isoformat()} vs {pf.isoformat()} to {pl.isoformat()})?"
            ),
            question_zh=f"按自然月（{cf}–{cl} 对比 {pf}–{pl}），{yr}年{moy}月门店净销售额{sc}的同比是多少？",
            paired_definitions=defs,
            gold_sql=sql_cal.strip(),
            gold_value=v_cal,
            gold_unit="ratio",
            sign_disagreement=rec["sign_d"],
            metadata=meta,
        ))
        # Specified rolling 30: compute B
        n += 1
        tasks.append(make_task(
            f"msb_{VERSION}_cal_compute_r30_{n:03d}",
            type="calendar", subtype="month_vs_rolling30_yoy",
            gold_behavior="compute",
            specified_definition="rolling_30",
            question_en=(
                f"What was the year-over-year growth rate of store net sales{sc} "
                f"for the rolling 30-day window ending {rl.isoformat()} "
                f"({rf.isoformat()} to {rl.isoformat()} vs {rpf.isoformat()} to {rpl.isoformat()})?"
            ),
            question_zh=f"按滚动30天（{rf}–{rl} 对比 {rpf}–{rpl}），门店净销售额{sc}的同比是多少？",
            paired_definitions=defs,
            gold_sql=sql_r30.strip(),
            gold_value=v_r30,
            gold_unit="ratio",
            sign_disagreement=rec["sign_d"],
            metadata=meta,
        ))

    # Calendar year vs retail FY for complete years only (2000, 2001; FY 2002 is incomplete).
    for yr in (2000, 2001):
        cy_f, cy_t = date(yr, 1, 1), date(yr, 12, 31)
        py_f, py_t = date(yr - 1, 1, 1), date(yr - 1, 12, 31)
        fy_f, fy_t = retail_fy_span(yr)
        fyp_f, fyp_t = retail_fy_span(yr - 1)
        if not all(_period_complete(con, a, b) for a, b in [(cy_f, cy_t), (py_f, py_t), (fy_f, fy_t), (fyp_f, fyp_t)]):
            continue
        sql_cy = q_yoy(cy_f, cy_t, py_f, py_t)
        sql_fy = q_yoy(fy_f, fy_t, fyp_f, fyp_t)
        v_cy, v_fy = scalar(con, sql_cy), scalar(con, sql_fy)
        defs = [
            {"id": "calendar_year", "sql": sql_cy.strip(), "value": v_cy, "unit": "ratio"},
            {"id": "retail_fy", "sql": sql_fy.strip(), "value": v_fy, "unit": "ratio"},
        ]
        sign_d = v_cy is not None and v_fy is not None and (v_cy * v_fy < 0) and abs(v_cy) >= MIN_ABS_YOY and abs(v_fy) >= MIN_ABS_YOY
        meta = {"yr": yr, "sign_d": sign_d, "cal_yoy": v_cy, "fy_yoy": v_fy,
                "fy_span": [fy_f.isoformat(), fy_t.isoformat()]}
        tasks.append(make_task(
            f"msb_{VERSION}_cal_fy_clarify_{yr}",
            type="calendar", subtype="calendar_year_vs_retail_fy_yoy",
            gold_behavior="clarify",
            question_en=f"What was the year-over-year growth rate of store net sales for {yr}?",
            question_zh=f"{yr}年门店净销售额的同比增长率是多少？",
            paired_definitions=defs,
            sign_disagreement=sign_d,
            metadata=meta,
        ))
        tasks.append(make_task(
            f"msb_{VERSION}_cal_fy_compute_cal_{yr}",
            type="calendar", subtype="calendar_year_vs_retail_fy_yoy",
            gold_behavior="compute", specified_definition="calendar_year",
            question_en=(
                f"What was the year-over-year growth rate of store net sales "
                f"for calendar year {yr} (January 1 to December 31 {yr} vs the same span in {yr-1})?"
            ),
            question_zh=f"按自然年（1月1日–12月31日），{yr}年门店净销售额同比是多少？",
            paired_definitions=defs, gold_sql=sql_cy.strip(), gold_value=v_cy, gold_unit="ratio",
            sign_disagreement=sign_d, metadata=meta,
        ))
        tasks.append(make_task(
            f"msb_{VERSION}_cal_fy_compute_fy_{yr}",
            type="calendar", subtype="calendar_year_vs_retail_fy_yoy",
            gold_behavior="compute", specified_definition="retail_fy",
            question_en=(
                f"What was the year-over-year growth rate of store net sales for retail fiscal year {yr} "
                f"(February 1 {yr} to January 31 {yr+1} vs February 1 {yr-1} to January 31 {yr})?"
            ),
            question_zh=f"按零售财年（{yr}-02-01 至 {yr+1}-01-31），{yr}财年门店净销售额同比是多少？",
            paired_definitions=defs, gold_sql=sql_fy.strip(), gold_value=v_fy, gold_unit="ratio",
            sign_disagreement=sign_d, metadata=meta,
        ))

    # Completeness: retail FY 2002 needs 2003-01-31; fixture max date is 2003-01-02.
    fy_f, fy_t = retail_fy_span(2002)
    complete = _period_complete(con, fy_f, fy_t)
    max_d = con.execute("SELECT max(d_date) FROM msb_store_sales").fetchone()[0]
    assert not complete, "FY 2002 unexpectedly complete; revisit refuse task"
    tasks.append(make_task(
        f"msb_{VERSION}_cal_refuse_incomplete_fy2002",
        type="sparse_completeness", subtype="incomplete_retail_fy",
        gold_behavior="refuse",
        refuse_reason="incomplete_period",
        question_en=(
            "What was the year-over-year growth rate of store net sales for retail fiscal year 2002 "
            "(February 1 2002 to January 31 2003)?"
        ),
        question_zh="零售财年2002（2002-02-01 至 2003-01-31）门店净销售额同比是多少？",
        metadata={"required_end": fy_t.isoformat(), "fixture_max_date": str(max_d), "complete": False},
    ))
    tasks.append(make_task(
        f"msb_{VERSION}_cal_refuse_incomplete_cy2003",
        type="sparse_completeness", subtype="incomplete_calendar_year",
        gold_behavior="refuse",
        refuse_reason="incomplete_period",
        question_en="What were total store net sales for calendar year 2003 (January 1 to December 31 2003)?",
        question_zh="2003自然年（1月1日–12月31日）门店净销售额合计是多少？",
        metadata={"required_end": "2003-12-31", "fixture_max_date": str(max_d), "complete": False},
    ))


def build_lifecycle(con, tasks: list) -> None:
    # New-product sales share: first-sale-in-year vs i_rec_start_date in year, for 2000 and 2001.
    for yr in (2000, 2001):
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
          WHERE i_rec_start_date IS NOT NULL
            AND year(i_rec_start_date) = {yr}
        )
        SELECT
          SUM(CASE WHEN n.i_item_id IS NOT NULL THEN ss.ss_net_paid ELSE 0 END) * 1.0
          / NULLIF(SUM(ss.ss_net_paid), 0)
        FROM msb_store_sales ss
        LEFT JOIN new_ids n ON n.i_item_id = ss.i_item_id
        WHERE ss.d_year = {yr}
        """
        v1, v2 = scalar(con, sql_first), scalar(con, sql_rec)
        if v1 is None or v2 is None or abs(v1 - v2) < 1e-4:
            # still record if they differ at all; skip only if identical or null
            if v1 is None or v2 is None:
                continue
        defs = [
            {"id": "first_sale_in_period", "sql": sql_first.strip(), "value": v1, "unit": "ratio"},
            {"id": "catalog_rec_start_in_period", "sql": sql_rec.strip(), "value": v2, "unit": "ratio"},
        ]
        meta = {"yr": yr, "gap": abs(v1 - v2)}
        tasks.append(make_task(
            f"msb_{VERSION}_life_clarify_newshare_{yr}",
            type="lifecycle", subtype="new_product_sales_share",
            gold_behavior="clarify",
            question_en=f"What share of store net sales in calendar year {yr} came from new products?",
            question_zh=f"{yr}自然年新品销售占门店净销售额的比例是多少？",
            paired_definitions=defs, metadata=meta,
        ))
        tasks.append(make_task(
            f"msb_{VERSION}_life_compute_firstsale_{yr}",
            type="lifecycle", subtype="new_product_sales_share",
            gold_behavior="compute", specified_definition="first_sale_in_period",
            question_en=(
                f"What share of store net sales in calendar year {yr} came from items whose "
                f"first-ever store sale occurred in {yr}?"
            ),
            question_zh=f"{yr}年，首次门店销售发生在该年的商品，占当年门店净销售额的比例？",
            paired_definitions=defs, gold_sql=sql_first.strip(), gold_value=v1, gold_unit="ratio",
            metadata=meta,
        ))
        tasks.append(make_task(
            f"msb_{VERSION}_life_compute_recstart_{yr}",
            type="lifecycle", subtype="new_product_sales_share",
            gold_behavior="compute", specified_definition="catalog_rec_start_in_period",
            question_en=(
                f"What share of store net sales in calendar year {yr} came from items whose "
                f"catalog record start date (i_rec_start_date) falls in {yr}?"
            ),
            question_zh=f"{yr}年，目录记录开始日期在该年的商品，占当年门店净销售额的比例？",
            paired_definitions=defs, gold_sql=sql_rec.strip(), gold_value=v2, gold_unit="ratio",
            metadata=meta,
        ))

    # Active-item rate: selling items / in-catalog vs selling / all items, year 2001, mid-year snapshot date 2001-06-30.
    snap = date(2001, 6, 30)
    yr = 2001
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
    defs = [
        {"id": "denominator_in_catalog", "sql": sql_den_catalog.strip(), "value": v_cat, "unit": "ratio"},
        {"id": "denominator_all_items", "sql": sql_den_all.strip(), "value": v_all, "unit": "ratio"},
    ]
    tasks.append(make_task(
        f"msb_{VERSION}_life_clarify_activerate_{yr}",
        type="lifecycle", subtype="active_item_rate_denominator",
        gold_behavior="clarify",
        question_en=f"What was the active-item rate of the catalog in calendar year {yr}?",
        question_zh=f"{yr}年的动销率是多少？",
        paired_definitions=defs,
        metadata={"yr": yr, "snapshot": snap.isoformat(), "gap": abs((v_cat or 0) - (v_all or 0))},
    ))
    tasks.append(make_task(
        f"msb_{VERSION}_life_compute_activerate_catalog_{yr}",
        type="lifecycle", subtype="active_item_rate_denominator",
        gold_behavior="compute", specified_definition="denominator_in_catalog",
        question_en=(
            f"What fraction of items in-catalog on {snap.isoformat()} "
            f"(i_rec_start_date <= snapshot and i_rec_end_date is null or >= snapshot) "
            f"had at least one store sale in calendar year {yr}?"
        ),
        question_zh=f"以{snap}在档商品为分母，{yr}年至少有一笔门店销售的动销率是多少？",
        paired_definitions=defs, gold_sql=sql_den_catalog.strip(), gold_value=v_cat, gold_unit="ratio",
        metadata={"yr": yr, "snapshot": snap.isoformat()},
    ))
    tasks.append(make_task(
        f"msb_{VERSION}_life_compute_activerate_all_{yr}",
        type="lifecycle", subtype="active_item_rate_denominator",
        gold_behavior="compute", specified_definition="denominator_all_items",
        question_en=(
            f"What fraction of all item IDs in the item table had at least one store sale "
            f"in calendar year {yr}?"
        ),
        question_zh=f"以商品表全部商品为分母，{yr}年至少有一笔门店销售的比例是多少？",
        paired_definitions=defs, gold_sql=sql_den_all.strip(), gold_value=v_all, gold_unit="ratio",
        metadata={"yr": yr},
    ))


def build_currency(con, tasks: list) -> None:
    for yr in (2000, 2001):
        sql_raw = f"SELECT SUM(ss_net_paid) FROM msb_store_sales WHERE d_year = {yr}"
        sql_usd = f"SELECT SUM(net_paid_usd) FROM msb_store_sales WHERE d_year = {yr}"
        v_raw, v_usd = scalar(con, sql_raw), scalar(con, sql_usd)
        defs = [
            {"id": "raw_local_sum", "sql": sql_raw, "value": v_raw, "unit": "mixed_currency_amount",
             "note": "Illegal as a single-currency total; provided only to detect definition swap."},
            {"id": "converted_usd_sum", "sql": sql_usd, "value": v_usd, "unit": "usd",
             "note": "Legal under metricsem_fx_v1: local amounts times frozen fx_to_usd."},
        ]
        tasks.append(make_task(
            f"msb_{VERSION}_ccy_clarify_{yr}",
            type="currency", subtype="raw_vs_usd_converted",
            gold_behavior="clarify",
            question_en=f"What were total store net sales in calendar year {yr}?",
            question_zh=f"{yr}自然年门店净销售额合计是多少？",
            paired_definitions=defs,
            extensions=["metricsem_fx_v1"],
            metadata={"yr": yr, "raw": v_raw, "usd": v_usd, "rel_gap": abs(v_raw - v_usd) / v_usd},
        ))
        tasks.append(make_task(
            f"msb_{VERSION}_ccy_compute_usd_{yr}",
            type="currency", subtype="raw_vs_usd_converted",
            gold_behavior="compute", specified_definition="converted_usd_sum",
            question_en=(
                f"What were total store net sales in calendar year {yr} in USD after converting "
                f"each store's local currency with the frozen metricsem_fx_v1 rates?"
            ),
            question_zh=f"按 metricsem_fx_v1 汇率折算为美元后，{yr}年门店净销售额合计是多少？",
            paired_definitions=defs, gold_sql=sql_usd, gold_value=v_usd, gold_unit="usd",
            extensions=["metricsem_fx_v1"],
            metadata={"yr": yr},
        ))
        tasks.append(make_task(
            f"msb_{VERSION}_ccy_refuse_raw_as_usd_{yr}",
            type="currency", subtype="raw_sum_claimed_as_usd",
            gold_behavior="refuse",
            refuse_reason="currency_mix_no_fx",
            question_en=(
                f"Report a single USD total of store net sales for calendar year {yr} "
                f"by summing ss_net_paid across all stores without conversion "
                f"(treat every local amount as if it were already USD)."
            ),
            question_zh=f"把各店本地币种的 ss_net_paid 直接相加，作为{yr}年以美元计的门店净销售总额。",
            paired_definitions=defs,
            extensions=["metricsem_fx_v1"],
            metadata={"yr": yr, "illegal_value_if_executed": v_raw},
        ))


def build_non_additive(con, tasks: list) -> None:
    for yr in (2000, 2001):
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
        defs = [
            {"id": "overall_aov", "sql": sql_overall.strip(), "value": v_ov, "unit": "amount_per_ticket"},
            {"id": "sum_of_store_aovs", "sql": sql_sum_store.strip(), "value": v_sum, "unit": "illegal_sum_of_rates"},
        ]
        tasks.append(make_task(
            f"msb_{VERSION}_nadd_compute_overall_aov_{yr}",
            type="non_additive", subtype="aov",
            gold_behavior="compute", specified_definition="overall_aov",
            question_en=(
                f"What was the overall average order value of store sales in calendar year {yr}, "
                f"defined as total ss_net_paid divided by the number of distinct tickets?"
            ),
            question_zh=f"{yr}自然年门店总体客单价（净销售额 / 去重小票数）是多少？",
            paired_definitions=defs, gold_sql=sql_overall.strip(), gold_value=v_ov,
            gold_unit="amount_per_ticket", metadata={"yr": yr},
        ))
        tasks.append(make_task(
            f"msb_{VERSION}_nadd_refuse_sum_store_aov_{yr}",
            type="non_additive", subtype="aov_illegal_sum",
            gold_behavior="refuse",
            refuse_reason="non_additive_sum",
            question_en=(
                f"Report the total average order value for calendar year {yr} "
                f"by summing the per-store average order values."
            ),
            question_zh=f"把各门店{yr}年客单价相加，作为该年总客单价。",
            paired_definitions=defs,
            metadata={"yr": yr, "illegal_value_if_executed": v_sum, "overall_aov": v_ov},
        ))
        # margin rate illegal sum across stores
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
        tasks.append(make_task(
            f"msb_{VERSION}_nadd_compute_margin_{yr}",
            type="non_additive", subtype="margin_rate",
            gold_behavior="compute", specified_definition="overall_margin_rate",
            question_en=(
                f"What was the overall net-profit margin rate of store sales in calendar year {yr}, "
                f"defined as SUM(ss_net_profit) / SUM(ss_net_paid)?"
            ),
            question_zh=f"{yr}年门店总体净利润率（SUM(ss_net_profit)/SUM(ss_net_paid)）是多少？",
            paired_definitions=defs_m, gold_sql=sql_overall_m.strip(), gold_value=v_om, gold_unit="ratio",
            metadata={"yr": yr},
        ))
        tasks.append(make_task(
            f"msb_{VERSION}_nadd_refuse_sum_margin_{yr}",
            type="non_additive", subtype="margin_rate_illegal_sum",
            gold_behavior="refuse",
            refuse_reason="non_additive_sum",
            question_en=(
                f"Report the total net-profit margin rate for calendar year {yr} "
                f"by summing the per-store margin rates."
            ),
            question_zh=f"把各门店{yr}年净利润率相加，作为该年总利润率。",
            paired_definitions=defs_m,
            metadata={"yr": yr, "illegal_value_if_executed": v_sm, "overall": v_om},
        ))


def build_denominator(con, tasks: list) -> None:
    # Return rate: amount-based vs quantity-based, years 2000-2001.
    for yr in (2000, 2001):
        sql_amt = f"""
        SELECT (SELECT SUM(sr_return_amt) FROM msb_store_returns WHERE d_year = {yr}) * 1.0
             / NULLIF((SELECT SUM(ss_ext_sales_price) FROM msb_store_sales WHERE d_year = {yr}), 0)
        """
        sql_qty = f"""
        SELECT (SELECT SUM(sr_return_quantity) FROM msb_store_returns WHERE d_year = {yr}) * 1.0
             / NULLIF((SELECT SUM(ss_quantity) FROM msb_store_sales WHERE d_year = {yr}), 0)
        """
        v_a, v_q = scalar(con, sql_amt), scalar(con, sql_qty)
        defs = [
            {"id": "return_rate_amount", "sql": sql_amt.strip(), "value": v_a, "unit": "ratio"},
            {"id": "return_rate_quantity", "sql": sql_qty.strip(), "value": v_q, "unit": "ratio"},
        ]
        tasks.append(make_task(
            f"msb_{VERSION}_den_clarify_return_{yr}",
            type="denominator", subtype="return_rate_amt_vs_qty",
            gold_behavior="clarify",
            question_en=f"What was the store return rate in calendar year {yr}?",
            question_zh=f"{yr}年门店退货率是多少？",
            paired_definitions=defs, metadata={"yr": yr, "gap": abs((v_a or 0) - (v_q or 0))},
        ))
        tasks.append(make_task(
            f"msb_{VERSION}_den_compute_return_amt_{yr}",
            type="denominator", subtype="return_rate_amt_vs_qty",
            gold_behavior="compute", specified_definition="return_rate_amount",
            question_en=(
                f"What was the store return rate in calendar year {yr}, defined as "
                f"SUM(sr_return_amt) / SUM(ss_ext_sales_price)?"
            ),
            question_zh=f"{yr}年按金额计的退货率（退货金额/销售金额）是多少？",
            paired_definitions=defs, gold_sql=sql_amt.strip(), gold_value=v_a, gold_unit="ratio",
            metadata={"yr": yr},
        ))
        tasks.append(make_task(
            f"msb_{VERSION}_den_compute_return_qty_{yr}",
            type="denominator", subtype="return_rate_amt_vs_qty",
            gold_behavior="compute", specified_definition="return_rate_quantity",
            question_en=(
                f"What was the store return rate in calendar year {yr}, defined as "
                f"SUM(sr_return_quantity) / SUM(ss_quantity)?"
            ),
            question_zh=f"{yr}年按件数计的退货率（退货件数/销售件数）是多少？",
            paired_definitions=defs, gold_sql=sql_qty.strip(), gold_value=v_q, gold_unit="ratio",
            metadata={"yr": yr},
        ))

    # Channel scope: store-only vs store+web+catalog for "total sales" 2001.
    yr = 2001
    sql_store = f"SELECT SUM(ss_net_paid) FROM msb_store_sales WHERE d_year = {yr}"
    sql_allch = f"""
    SELECT
      (SELECT SUM(ss_net_paid) FROM msb_store_sales WHERE d_year = {yr})
    + (SELECT SUM(ws_net_paid) FROM msb_web_sales WHERE d_year = {yr})
    + (SELECT SUM(cs_net_paid) FROM msb_catalog_sales WHERE d_year = {yr})
    """
    v_s, v_a = scalar(con, sql_store), scalar(con, sql_allch)
    defs = [
        {"id": "store_channel_only", "sql": sql_store, "value": v_s, "unit": "amount"},
        {"id": "store_web_catalog", "sql": sql_allch.strip(), "value": v_a, "unit": "amount"},
    ]
    tasks.append(make_task(
        f"msb_{VERSION}_den_clarify_channel_{yr}",
        type="denominator", subtype="channel_scope",
        gold_behavior="clarify",
        question_en=f"What were total net sales in calendar year {yr}?",
        question_zh=f"{yr}年净销售总额是多少？",
        paired_definitions=defs, metadata={"yr": yr, "rel_gap": abs(v_a - v_s) / v_s},
    ))
    tasks.append(make_task(
        f"msb_{VERSION}_den_compute_store_{yr}",
        type="denominator", subtype="channel_scope",
        gold_behavior="compute", specified_definition="store_channel_only",
        question_en=f"What were total store-channel net sales (store_sales only) in calendar year {yr}?",
        question_zh=f"{yr}年仅门店渠道（store_sales）净销售额是多少？",
        paired_definitions=defs, gold_sql=sql_store, gold_value=v_s, gold_unit="amount",
        metadata={"yr": yr},
    ))
    tasks.append(make_task(
        f"msb_{VERSION}_den_compute_allch_{yr}",
        type="denominator", subtype="channel_scope",
        gold_behavior="compute", specified_definition="store_web_catalog",
        question_en=(
            f"What were total net sales across store, web, and catalog channels "
            f"(SUM ss_net_paid + ws_net_paid + cs_net_paid) in calendar year {yr}?"
        ),
        question_zh=f"{yr}年门店+网站+目录三渠道净销售额合计是多少？",
        paired_definitions=defs, gold_sql=sql_allch.strip(), gold_value=v_a, gold_unit="amount",
        metadata={"yr": yr},
    ))


def build_sparse(con, tasks: list) -> None:
    # Item-level YoY with zero prior tickets (undefined) or prior tickets < SPARSE_MIN.
    # Pick a handful of real items, deterministic order.
    rows = con.execute(
        f"""
        WITH cur AS (
          SELECT i_item_id, i_category, COUNT(DISTINCT ss_ticket_number) AS tickets, SUM(ss_net_paid) AS amt
          FROM msb_store_sales
          WHERE d_date BETWEEN DATE '2001-10-01' AND DATE '2001-10-31'
          GROUP BY 1,2
        ),
        prev AS (
          SELECT i_item_id, COUNT(DISTINCT ss_ticket_number) AS tickets, SUM(ss_net_paid) AS amt
          FROM msb_store_sales
          WHERE d_date BETWEEN DATE '2000-10-01' AND DATE '2000-10-31'
          GROUP BY 1
        )
        SELECT c.i_item_id, c.i_category, c.tickets, c.amt,
               COALESCE(p.tickets, 0) AS prev_tickets, COALESCE(p.amt, 0) AS prev_amt
        FROM cur c
        LEFT JOIN prev p ON p.i_item_id = c.i_item_id
        WHERE c.tickets >= 10
          AND COALESCE(p.tickets, 0) < {SPARSE_MIN_PRIOR_TICKETS}
        ORDER BY COALESCE(p.tickets, 0), c.tickets DESC, c.i_item_id
        LIMIT 8
        """
    ).fetchall()
    for i, (item_id, cat, cur_t, cur_a, prev_t, prev_a) in enumerate(rows, 1):
        reason = "sparse_prior" if prev_t > 0 else "undefined_yoy"
        tasks.append(make_task(
            f"msb_{VERSION}_sparse_refuse_item_{i:03d}",
            type="sparse_completeness", subtype="item_month_yoy_sparse_prior",
            gold_behavior="refuse",
            refuse_reason=reason,
            question_en=(
                f"What was the year-over-year growth rate of store net sales for item {item_id} "
                f"in calendar month October 2001 (versus October 2000)?"
            ),
            question_zh=f"商品 {item_id} 在 2001年10月相对 2000年10月的门店净销售同比是多少？",
            metadata={
                "item_id": item_id, "category": cat,
                "cur_tickets": int(cur_t), "prev_tickets": int(prev_t),
                "cur_amt": float(cur_a), "prev_amt": float(prev_a),
                "sparse_min_prior_tickets": SPARSE_MIN_PRIOR_TICKETS,
            },
        ))

    # Category + tight filter that yields sparse prior: high-price items in a small brand? Use a real filter
    # with prior tickets below threshold at the filtered grain.
    rows2 = con.execute(
        f"""
        WITH cur AS (
          SELECT i_brand, i_category, COUNT(DISTINCT ss_ticket_number) AS tickets, SUM(ss_net_paid) AS amt
          FROM msb_store_sales
          WHERE d_date BETWEEN DATE '2001-02-01' AND DATE '2001-02-28'
            AND i_category IS NOT NULL AND i_brand IS NOT NULL
          GROUP BY 1,2
        ),
        prev AS (
          SELECT i_brand, i_category, COUNT(DISTINCT ss_ticket_number) AS tickets, SUM(ss_net_paid) AS amt
          FROM msb_store_sales
          WHERE d_date BETWEEN DATE '2000-02-01' AND DATE '2000-02-29'
            AND i_category IS NOT NULL AND i_brand IS NOT NULL
          GROUP BY 1,2
        )
        SELECT c.i_brand, c.i_category, c.tickets, c.amt,
               COALESCE(p.tickets, 0), COALESCE(p.amt, 0)
        FROM cur c LEFT JOIN prev p ON p.i_brand=c.i_brand AND p.i_category=c.i_category
        WHERE c.tickets >= 10 AND COALESCE(p.tickets, 0) < {SPARSE_MIN_PRIOR_TICKETS}
        ORDER BY COALESCE(p.tickets,0), c.tickets DESC, c.i_brand
        LIMIT 4
        """
    ).fetchall()
    for i, (brand, cat, cur_t, cur_a, prev_t, prev_a) in enumerate(rows2, 1):
        # escape quotes in names
        tasks.append(make_task(
            f"msb_{VERSION}_sparse_refuse_brand_{i:03d}",
            type="sparse_completeness", subtype="brand_month_yoy_sparse_prior",
            gold_behavior="refuse",
            refuse_reason="sparse_prior" if prev_t > 0 else "undefined_yoy",
            question_en=(
                f"What was the year-over-year growth rate of store net sales for brand {brand!r} "
                f"in the {cat} category for calendar month February 2001?"
            ),
            question_zh=f"{cat} 类目下品牌 {brand} 在 2001年2月的门店净销售同比是多少？",
            metadata={
                "brand": brand, "category": cat,
                "cur_tickets": int(cur_t), "prev_tickets": int(prev_t),
                "cur_amt": float(cur_a), "prev_amt": float(prev_a),
            },
        ))


def validate_and_dump(con, tasks: list) -> Path:
    # Re-run every gold_sql and paired sql; ensure compute values match.
    errors = []
    for t in tasks:
        for d in t.get("paired_definitions") or []:
            if not d.get("sql"):
                continue
            v = scalar(con, d["sql"])
            if v is None:
                errors.append(f"{t['id']} def {d['id']} returned NULL")
                continue
            if abs(v - d["value"]) > max(1e-6, 1e-8 * abs(d["value"])):
                errors.append(f"{t['id']} def {d['id']} value drift {d['value']} vs {v}")
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

    TASKS_DIR.mkdir(parents=True, exist_ok=True)
    out = TASKS_DIR / f"msb_{VERSION}_tasks.json"
    payload = {
        "version": VERSION,
        "source": "DuckDB official dsdgen TPC-DS SF=1",
        "dictionary": DICTIONARY,
        "n_tasks": len(tasks),
        "counts": _counts(tasks),
        "tasks": tasks,
    }
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    # slim index without long SQL for README
    index = {
        "version": VERSION,
        "n_tasks": len(tasks),
        "counts": _counts(tasks),
        "tasks": [
            {
                "id": t["id"], "type": t["type"], "subtype": t["subtype"],
                "gold_behavior": t["gold_behavior"], "sign_disagreement": t.get("sign_disagreement"),
                "refuse_reason": t.get("refuse_reason"),
                "question_en": t["question_en"],
            }
            for t in tasks
        ],
    }
    (TASKS_DIR / f"msb_{VERSION}_index.json").write_text(
        json.dumps(index, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print("wrote", out, "n=", len(tasks), "counts=", _counts(tasks))
    return out


def _counts(tasks):
    from collections import Counter
    c = Counter()
    for t in tasks:
        c[f"type:{t['type']}"] += 1
        c[f"behavior:{t['gold_behavior']}"] += 1
        if t.get("sign_disagreement"):
            c["sign_disagreement"] += 1
    return dict(c)


def build() -> Path:
    generate(force=False)
    con = duckdb.connect(str(DB_PATH), read_only=True)
    tasks: list[dict] = []
    build_calendar(con, tasks)
    build_lifecycle(con, tasks)
    build_currency(con, tasks)
    build_non_additive(con, tasks)
    build_denominator(con, tasks)
    build_sparse(con, tasks)
    path = validate_and_dump(con, tasks)
    con.close()
    return path


if __name__ == "__main__":
    build()
