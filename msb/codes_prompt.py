"""Official-style CodeS prompt for MetricSemBench DEV (always-answer).

Prompt format follows RUCKBReasoning/codes:
  schema_sequence + "\\n" + content_sequence + "\\n" + text + "\\n"
where schema_sequence is get_db_schema_sequence(), content_sequence is
matched contents or "matched contents : None", and text is the question
(no evidence; Spider-SFT checkpoint).

We expose the compact MetricSemBench views (the same surface as SCHEMA_CARD),
not raw TPC-DS 24 tables, and we do NOT wrap CodeS in compute/clarify/refuse
instructions. Column comments document units and the FX overlay, analogous
to official column comments. This is a DEV profile only.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

# Frozen compact schema for CodeS. Types and comments are fixture facts.
# Sample values: two representatives, as in CodeS get_column_contents (LIMIT 2).
SCHEMA_ITEMS = [
    {
        "table_name": "msb_store_sales",
        "table_comment": "store_sales joined to date, store, item, and metricsem_fx_v1",
        "columns": [
            ("ss_net_paid", "decimal", "native TPC-DS net paid, already in the store's local currency under the FX overlay"),
            ("ss_net_profit", "decimal", "native TPC-DS net profit"),
            ("ss_quantity", "bigint", "item quantity"),
            ("ss_ext_sales_price", "decimal", "extended sales price"),
            ("ss_ticket_number", "bigint", "store ticket id"),
            ("ss_store_sk", "bigint", "store key"),
            ("ss_item_sk", "bigint", "item key"),
            ("d_date", "date", "sale date; fixture range 1998-01-02 to 2003-01-02"),
            ("d_year", "bigint", "calendar year"),
            ("d_moy", "bigint", "calendar month 1-12"),
            ("d_dom", "bigint", "day of month"),
            ("retail_fy", "integer", "retail fiscal year starting February 1; FY Y is Feb 1 Y through Jan 31 Y+1"),
            ("retail_fy_month", "bigint", "month within the retail FY"),
            ("i_item_id", "varchar", "item id"),
            ("i_category", "varchar", "item category"),
            ("i_brand", "varchar", "item brand"),
            ("i_rec_start_date", "date", "catalog record start date"),
            ("i_rec_end_date", "date", "catalog record end date, nullable"),
            ("store_currency", "varchar", "USD / EUR / GBP / CAD assigned deterministically by store_sk"),
            ("fx_to_usd", "decimal", "frozen fixture FX rate to USD"),
            ("net_paid_usd", "decimal", "ss_net_paid * fx_to_usd; use this for a single-currency USD total"),
        ],
        "contents": {
            "i_category": ["Sports", "Books"],
            "store_currency": ["USD", "EUR"],
            "d_year": ["1998", "2001"],
        },
    },
    {
        "table_name": "msb_web_sales",
        "table_comment": "web_sales joined to date and item",
        "columns": [
            ("ws_net_paid", "decimal", "web net paid"),
            ("d_date", "date", "sale date"),
            ("d_year", "bigint", "calendar year"),
            ("d_moy", "bigint", "calendar month"),
            ("retail_fy", "integer", "retail fiscal year starting February 1"),
            ("i_item_id", "varchar", "item id"),
            ("i_category", "varchar", "item category"),
        ],
        "contents": {"i_category": ["Sports", "Books"]},
    },
    {
        "table_name": "msb_catalog_sales",
        "table_comment": "catalog_sales joined to date and item",
        "columns": [
            ("cs_net_paid", "decimal", "catalog net paid"),
            ("d_date", "date", "sale date"),
            ("d_year", "bigint", "calendar year"),
            ("d_moy", "bigint", "calendar month"),
            ("retail_fy", "integer", "retail fiscal year starting February 1"),
            ("i_item_id", "varchar", "item id"),
            ("i_category", "varchar", "item category"),
        ],
        "contents": {"i_category": ["Sports", "Books"]},
    },
    {
        "table_name": "msb_store_returns",
        "table_comment": "store_returns joined to date",
        "columns": [
            ("sr_return_amt", "decimal", "return amount"),
            ("sr_return_quantity", "bigint", "return quantity"),
            ("d_date", "date", "return date"),
            ("d_year", "bigint", "calendar year"),
            ("d_moy", "bigint", "calendar month"),
        ],
        "contents": {},
    },
    {
        "table_name": "item",
        "table_comment": "TPC-DS item dimension",
        "columns": [
            ("i_item_id", "varchar", "item id"),
            ("i_rec_start_date", "date", "catalog record start"),
            ("i_rec_end_date", "date", "catalog record end, nullable"),
            ("i_category", "varchar", "category"),
            ("i_brand", "varchar", "brand"),
        ],
        "contents": {"i_category": ["Sports", "Books"]},
    },
]


def schema_sequence() -> str:
    lines = ["database schema :"]
    for t in SCHEMA_ITEMS:
        cols = []
        for name, typ, comment in t["columns"]:
            bits = [typ]
            if comment:
                bits.append("comment : " + comment)
            samples = t.get("contents", {}).get(name) or []
            if samples:
                bits.append("values : " + " , ".join(str(s) for s in samples))
            cols.append(f"{t['table_name']}.{name} ( " + " | ".join(bits) + " )")
        lines.append("table " + t["table_name"] + " , columns = [ " + " , ".join(cols) + " ]")
    lines.append("foreign keys : None")
    return "\n".join(lines)


def matched_contents(question: str) -> str:
    """Lightweight content match: tokens from the question that are known values.

    Official CodeS uses Lucene; we do exact case-insensitive matches against
    known dimension values (categories, currencies, years, months). Frozen
    before seeing scores; not tuned afterwards.
    """
    known = {
        "msb_store_sales.i_category": [
            "Sports", "Books", "Jewelry", "Children", "Men", "Home",
            "Shoes", "Women", "Electronics", "Music",
        ],
        "msb_store_sales.store_currency": ["USD", "EUR", "GBP", "CAD"],
        "msb_store_sales.d_year": [str(y) for y in range(1998, 2004)],
    }
    q = question
    hits = {}
    for tc, vals in known.items():
        found = [v for v in vals if re.search(r"(?<![A-Za-z0-9])" + re.escape(v) + r"(?![A-Za-z0-9])", q, re.I)]
        if found:
            hits[tc] = found
    if not hits:
        return "matched contents : None"
    lines = ["matched contents :"]
    for tc, vals in hits.items():
        lines.append(tc + " ( " + " , ".join(vals) + " )")
    return "\n".join(lines)


def prefix_for(question: str) -> str:
    return schema_sequence() + "\n" + matched_contents(question) + "\n" + question + "\n"


def dump_blind_prompts(tasks_path: Path, out_path: Path) -> None:
    raw = json.loads(tasks_path.read_text())
    rows = []
    for t in raw["tasks"]:
        rows.append({
            "id": t["id"],
            "question_en": t["question_en"],
            "prefix": prefix_for(t["question_en"]),
        })
    out_path.write_text(json.dumps({"fold": "v0.1", "n": len(rows), "system": "codes-7b-spider", "rows": rows}, indent=2, ensure_ascii=False))
    print("wrote", out_path, "n", len(rows), "prefix_chars", len(rows[0]["prefix"]))


if __name__ == "__main__":
    from msb.config import TASKS_DIR, RESULTS_DIR
    dest = RESULTS_DIR / "codes" / "v0.1_codes_prompts.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dump_blind_prompts(TASKS_DIR / "msb_v0.1_tasks.json", dest)
