"""Keyword-heuristic baseline. Sees only the question text (and optional dictionary), never gold labels."""
from __future__ import annotations

import re
from datetime import date

import duckdb

from msb.config import DB_PATH


MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
}


def _years(q: str) -> list[int]:
    return [int(y) for y in re.findall(r"\b(199[8-9]|200[0-3])\b", q)]


def _month(q: str) -> int | None:
    ql = q.lower()
    for name, m in MONTHS.items():
        if name in ql:
            return m
    return None


class NaiveSurfaceBaseline:
    """Always answers when it can parse a metric; never refuses; defaults to calendar grain and raw sums."""

    name = "naive_surface"

    def __init__(self, db_path=None):
        self.db_path = db_path or DB_PATH

    def answer(self, task_view: dict) -> dict:
        q = task_view["question_en"]
        ql = q.lower()
        try:
            con = duckdb.connect(str(self.db_path), read_only=True)
            sql, value = self._run(con, q, ql)
            con.close()
        except Exception as e:
            return {"behavior": "compute", "sql": None, "value": None, "error": str(e)[:300]}
        if sql is None:
            # still never refuse: fall back to a generic year sales if a year is present
            return {"behavior": "compute", "sql": None, "value": None, "note": "unparsed"}
        return {"behavior": "compute", "sql": sql, "value": value}

    def _run(self, con, q, ql):
        years = _years(q)
        moy = _month(q)
        cat = _category(q)
        brand = _brand(q)
        item = _item(q)

        # illegal requested operations that naive WILL execute
        if "summing the per-store" in ql or "summing the per-store" in ql or "sum of per-store" in ql \
           or "by summing the per-store" in ql or "by summing the per-store average" in ql:
            if "margin" in ql:
                yr = years[0] if years else 2001
                sql = f"""
                SELECT SUM(m) FROM (
                  SELECT ss_store_sk, SUM(ss_net_profit)*1.0/NULLIF(SUM(ss_net_paid),0) AS m
                  FROM msb_store_sales WHERE d_year={yr} GROUP BY ss_store_sk)
                """
                return sql, _s(con, sql)
            if "average order" in ql or "aov" in ql:
                yr = years[0] if years else 2001
                sql = f"""
                SELECT SUM(aov) FROM (
                  SELECT ss_store_sk, SUM(ss_net_paid)*1.0/NULLIF(COUNT(DISTINCT ss_ticket_number),0) AS aov
                  FROM msb_store_sales WHERE d_year={yr} GROUP BY ss_store_sk)
                """
                return sql, _s(con, sql)

        if "without conversion" in ql or "already usd" in ql or "as if it were already usd" in ql:
            yr = years[0] if years else 2001
            sql = f"SELECT SUM(ss_net_paid) FROM msb_store_sales WHERE d_year={yr}"
            return sql, _s(con, sql)

        if "year-over-year" in ql or "yoy" in ql or "year-over-year growth" in ql:
            return self._yoy(con, q, ql, years, moy, cat, brand, item)

        if "average order value" in ql or re.search(r"\baov\b", ql):
            yr = years[0] if years else 2001
            sql = (
                f"SELECT SUM(ss_net_paid)*1.0/NULLIF(COUNT(DISTINCT ss_ticket_number),0) "
                f"FROM msb_store_sales WHERE d_year={yr}"
            )
            return sql, _s(con, sql)

        if "margin rate" in ql or "net-profit margin" in ql:
            yr = years[0] if years else 2001
            sql = f"SELECT SUM(ss_net_profit)*1.0/NULLIF(SUM(ss_net_paid),0) FROM msb_store_sales WHERE d_year={yr}"
            return sql, _s(con, sql)

        if "return rate" in ql:
            yr = years[0] if years else 2001
            # default: amount-based
            sql = f"""
            SELECT (SELECT SUM(sr_return_amt) FROM msb_store_returns WHERE d_year={yr})*1.0
                 / NULLIF((SELECT SUM(ss_ext_sales_price) FROM msb_store_sales WHERE d_year={yr}),0)
            """
            if "quantity" in ql or "sr_return_quantity" in ql:
                sql = f"""
                SELECT (SELECT SUM(sr_return_quantity) FROM msb_store_returns WHERE d_year={yr})*1.0
                     / NULLIF((SELECT SUM(ss_quantity) FROM msb_store_sales WHERE d_year={yr}),0)
                """
            return sql, _s(con, sql)

        if "share of store net sales" in ql or "came from new" in ql or "new product" in ql:
            yr = years[0] if years else 2001
            # default: first sale (one arbitrary definition)
            if "catalog record start" in ql or "i_rec_start_date" in ql:
                sql = f"""
                WITH new_ids AS (
                  SELECT DISTINCT i_item_id FROM item
                  WHERE i_rec_start_date IS NOT NULL AND year(i_rec_start_date)={yr})
                SELECT SUM(CASE WHEN n.i_item_id IS NOT NULL THEN ss.ss_net_paid ELSE 0 END)*1.0
                     / NULLIF(SUM(ss.ss_net_paid),0)
                FROM msb_store_sales ss LEFT JOIN new_ids n ON n.i_item_id=ss.i_item_id
                WHERE ss.d_year={yr}
                """
            else:
                sql = f"""
                WITH first_sale AS (
                  SELECT i_item_id, MIN(d_date) AS first_d FROM msb_store_sales GROUP BY 1
                ), new_ids AS (SELECT i_item_id FROM first_sale WHERE year(first_d)={yr})
                SELECT SUM(CASE WHEN n.i_item_id IS NOT NULL THEN ss.ss_net_paid ELSE 0 END)*1.0
                     / NULLIF(SUM(ss.ss_net_paid),0)
                FROM msb_store_sales ss LEFT JOIN new_ids n ON n.i_item_id=ss.i_item_id
                WHERE ss.d_year={yr}
                """
            return sql, _s(con, sql)

        if "active-item" in ql or "fraction of items" in ql or "fraction of all item" in ql:
            yr = years[0] if years else 2001
            if "in-catalog" in ql or "i_rec_start_date" in ql:
                sql = f"""
                WITH sold AS (
                  SELECT DISTINCT i_item_id FROM msb_store_sales
                  WHERE d_date BETWEEN DATE '{yr}-01-01' AND DATE '{yr}-12-31'
                ), catalog AS (
                  SELECT DISTINCT i_item_id FROM item
                  WHERE i_rec_start_date IS NOT NULL AND i_rec_start_date <= DATE '2001-06-30'
                    AND (i_rec_end_date IS NULL OR i_rec_end_date >= DATE '2001-06-30')
                )
                SELECT (SELECT COUNT(*) FROM sold s JOIN catalog c ON s.i_item_id=c.i_item_id)*1.0
                     / NULLIF((SELECT COUNT(*) FROM catalog),0)
                """
            else:
                sql = f"""
                WITH sold AS (
                  SELECT DISTINCT i_item_id FROM msb_store_sales
                  WHERE d_date BETWEEN DATE '{yr}-01-01' AND DATE '{yr}-12-31'
                ), all_items AS (SELECT DISTINCT i_item_id FROM item)
                SELECT (SELECT COUNT(*) FROM sold)*1.0 / NULLIF((SELECT COUNT(*) FROM all_items),0)
                """
            return sql, _s(con, sql)

        # totals
        if "net sales" in ql or "net paid" in ql or "total store" in ql:
            yr = years[0] if years else 2001
            if "metricsem_fx_v1" in ql or "after converting" in ql or "in usd after" in ql:
                sql = f"SELECT SUM(net_paid_usd) FROM msb_store_sales WHERE d_year={yr}"
            elif "store, web, and catalog" in ql or "store-web-catalog" in ql or "ss_net_paid + ws_net_paid" in ql \
                 or "across store, web, and catalog" in ql:
                sql = f"""
                SELECT
                  (SELECT SUM(ss_net_paid) FROM msb_store_sales WHERE d_year={yr})
                + (SELECT SUM(ws_net_paid) FROM msb_web_sales WHERE d_year={yr})
                + (SELECT SUM(cs_net_paid) FROM msb_catalog_sales WHERE d_year={yr})
                """
            elif "store-channel" in ql or "store_sales only" in ql:
                sql = f"SELECT SUM(ss_net_paid) FROM msb_store_sales WHERE d_year={yr}"
            else:
                # default: raw store sum, no FX — will DSR/FAR on currency and channel underspec
                sql = f"SELECT SUM(ss_net_paid) FROM msb_store_sales WHERE d_year={yr}"
            return sql, _s(con, sql)

        return None, None

    def _yoy(self, con, q, ql, years, moy, cat, brand, item):
        import calendar
        from datetime import timedelta
        yr = max(years) if years else 2001
        extra = ""
        if cat:
            extra += f" AND i_category = '{cat}'"
        if brand:
            extra += f" AND i_brand = '{brand}'"
        if item:
            extra += f" AND i_item_id = '{item}'"

        def last(y, m):
            return date(y, m, calendar.monthrange(y, m)[1])

        # ISO end date in the question (e.g. "ending 2000-02-29") takes precedence.
        iso = None
        import re as _re
        m_iso = _re.search(r"ending (19|20)\d{2}-\d{2}-\d{2}", ql)
        if m_iso:
            from datetime import date as _d
            iso = _d.fromisoformat(m_iso.group(0).split()[1])

        if "rolling 30" in ql or "rolling 30-day" in ql:
            if iso is not None:
                end = iso
            elif moy:
                end = last(yr, moy)
            else:
                end = last(yr, 2)
            start = end - timedelta(days=29)
            # prior window: 30 days ending the last day of the same month last year
            end_ly = last(end.year - 1, end.month)
            start_ly = end_ly - timedelta(days=29)
            sql = _yoy_sql(start, end, start_ly, end_ly, extra)
            return sql, _s(con, sql)

        if "retail fiscal year" in ql or "retail fy" in ql:
            # year mentioned with "fiscal year Y" — prefer that Y, not a later year in the span
            m_fy = _re.search(r"fiscal year (199[8-9]|200[0-3])", ql)
            if m_fy:
                yr = int(m_fy.group(1))
            sql = _yoy_sql(date(yr, 2, 1), date(yr + 1, 1, 31), date(yr - 1, 2, 1), date(yr, 1, 31), extra)
            return sql, _s(con, sql)

        if "calendar year" in ql:
            m_cy = _re.search(r"calendar year (199[8-9]|200[0-3])", ql)
            if m_cy:
                yr = int(m_cy.group(1))
            sql = _yoy_sql(date(yr, 1, 1), date(yr, 12, 31), date(yr - 1, 1, 1), date(yr - 1, 12, 31), extra)
            return sql, _s(con, sql)

        # default: calendar month if month named, else calendar year
        if moy:
            end = last(yr, moy)
            end_ly = last(yr - 1, moy)
            sql = _yoy_sql(date(yr, moy, 1), end, date(yr - 1, moy, 1), end_ly, extra)
            return sql, _s(con, sql)
        sql = _yoy_sql(date(yr, 1, 1), date(yr, 12, 31), date(yr - 1, 1, 1), date(yr - 1, 12, 31), extra)
        return sql, _s(con, sql)


def _yoy_sql(cf, cl, pf, pl, extra):
    return f"""
    WITH cur AS (SELECT SUM(ss_net_paid) AS amt FROM msb_store_sales
                 WHERE d_date BETWEEN DATE '{cf}' AND DATE '{cl}'{extra}),
         prev AS (SELECT SUM(ss_net_paid) AS amt FROM msb_store_sales
                  WHERE d_date BETWEEN DATE '{pf}' AND DATE '{pl}'{extra})
    SELECT (cur.amt - prev.amt)*1.0/NULLIF(prev.amt,0) FROM cur, prev
    """


def _s(con, sql):
    v = con.execute(sql).fetchone()[0]
    return float(v) if v is not None else None


def _category(q):
    for c in ["Books", "Children", "Electronics", "Home", "Jewelry", "Men", "Music", "Shoes", "Sports", "Women"]:
        if re.search(rf"\b{c}\b", q):
            return c
    return None


def _brand(q):
    m = re.search(r"brand ['\"]([^'\"]+)['\"]", q)
    return m.group(1) if m else None


def _item(q):
    m = re.search(r"item ([A-Z0-9]+)", q)
    return m.group(1) if m else None
