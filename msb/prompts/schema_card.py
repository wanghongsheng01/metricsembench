"""Compact public schema card for LLM baselines. No gold labels."""

SCHEMA_CARD = """
Database: official TPC-DS SF=1 loaded in DuckDB, plus MetricSemBench views.

Facts and views you may query:
- msb_store_sales: store_sales joined to date, store, item, and FX overlay.
  Key columns: ss_net_paid, ss_net_profit, ss_quantity, ss_ext_sales_price,
  ss_ticket_number, ss_store_sk, ss_item_sk,
  d_date, d_year, d_moy, retail_fy, retail_fy_month,
  i_item_id, i_category, i_brand, i_rec_start_date, i_rec_end_date,
  store_currency (USD/EUR/GBP/CAD assigned by store_sk),
  fx_to_usd (frozen fixture rates), net_paid_usd (= ss_net_paid * fx_to_usd).
- msb_web_sales: ws_net_paid, d_date, d_year, i_item_id, i_category.
- msb_catalog_sales: cs_net_paid, d_date, d_year.
- msb_store_returns: sr_return_amt, sr_return_quantity, d_date, d_year.
- item: i_item_id, i_rec_start_date, i_rec_end_date, i_category, i_brand.
- date_dim / msb_date: d_date, d_year, d_moy, retail_fy.
  NOTE: TPC-DS d_fy_year equals d_year (unusable). Retail FY starts February 1:
  retail FY Y =  Y-02-01 through (Y+1)-01-31.

Fixture completeness: MIN(d_date) on store_sales is 1998-01-02,
MAX(d_date) is 2003-01-02. Calendar year 2003 and retail FY 2002 are INCOMPLETE.

FX overlay metricsem_fx_v1: ss_net_paid is reinterpreted as already in the store's
local currency. A single-currency USD total MUST use SUM(net_paid_usd).
Summing ss_net_paid across stores is a mixed-currency total, not USD.

Non-additive metrics: average order value = SUM(ss_net_paid)/COUNT(DISTINCT ss_ticket_number);
margin rate = SUM(ss_net_profit)/SUM(ss_net_paid).
You must NOT sum per-store AOVs or per-store margin rates and call that a total.

Sparse YoY: if the prior-period distinct ticket count is < 5 (or 0), YoY is undefined
and must be refused. Prior window uses the same grain one year earlier.

Write DuckDB SQL. Use DATE 'YYYY-MM-DD' literals. Do not invent tables.
""".strip()

SEMANTIC_RULES = """
Decide one of three behaviors:
1) compute — the question fully specifies the definition (grain, denominator, currency,
   formula) AND the request is legal AND the time window is complete in the fixture.
   Then write SQL that returns a single scalar.
2) clarify — two or more legitimate definitions could answer the question and the
   question does not choose (e.g. calendar month vs rolling 30-day YoY; calendar year
   vs retail FY; raw local sum vs USD; store-only vs all channels; first-sale vs
   catalog-start "new products"; amount vs quantity return rate). Do NOT pick a default.
3) refuse — any execution would violate a contract: incomplete period, sparse/undefined
   YoY, summing non-additive rates, treating a raw mixed-currency sum as USD.

Return ONLY a JSON object with keys:
  "behavior": "compute" | "clarify" | "refuse",
  "sql": string or null,
  "refuse_reason": string or null,
  "clarify_axes": array of strings (the conflicting axes) or null,
  "brief": a short rationale (one sentence).
""".strip()
