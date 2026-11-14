"""Public metric dictionary for TPC-DS MetricSemBench (abstract contracts, no enterprise caliber)."""

DICTIONARY = {
    "version": "v0.1",
    "metrics": [
        {
            "id": "store_net_paid",
            "name": "store net sales",
            "aliases": ["store sales", "store net paid", "销售额", "销售收入"],
            "additive": True,
            "currency_sensitive": True,
            "time_grain_required": True,
            "default_grain": "calendar_month",
            "default_currency": "raw_local_sum",
            "sql_template": "SELECT SUM(ss_net_paid) FROM msb_store_sales WHERE {date_pred}",
            "usd_sql_template": "SELECT SUM(net_paid_usd) FROM msb_store_sales WHERE {date_pred}",
        },
        {
            "id": "store_aov",
            "name": "store average order value",
            "aliases": ["AOV", "average order value", "客单价"],
            "additive": False,
            "currency_sensitive": True,
            "time_grain_required": True,
            "default_grain": "calendar_year",
            "sql_template": (
                "SELECT SUM(ss_net_paid) * 1.0 / NULLIF(COUNT(DISTINCT ss_ticket_number), 0) "
                "FROM msb_store_sales WHERE {date_pred}"
            ),
        },
        {
            "id": "store_net_paid_yoy",
            "name": "store net sales year-over-year growth",
            "aliases": ["YoY", "year-over-year", "同比"],
            "additive": False,
            "requires_prior_period": True,
            "invalid_if_prior_sparse": True,
            "default_grain": "calendar_month",
            "alternate_grains": ["rolling_30", "retail_fy"],
        },
        {
            "id": "new_product_sales_share",
            "name": "new product sales share",
            "aliases": ["new product share", "新品销售占比"],
            "additive": False,
            "definitions": ["first_sale_in_period", "catalog_rec_start_in_period"],
        },
        {
            "id": "active_item_rate",
            "name": "active item rate",
            "aliases": ["动销率"],
            "additive": False,
            "denominator_defs": ["in_catalog", "all_items", "intersection_catalog_and_sold"],
        },
        {
            "id": "return_rate",
            "name": "store return rate",
            "aliases": ["退货率"],
            "additive": False,
            "denominator_defs": ["return_amt_over_sales_amt", "return_qty_over_sales_qty"],
        },
    ],
    "grains": {
        "calendar_month": "first to last calendar day of the named month",
        "rolling_30": "30 consecutive days ending on the last calendar day of the named month",
        "calendar_year": "Jan 1 to Dec 31 of the named year",
        "retail_fy": "Feb 1 of year Y through Jan 31 of year Y+1",
    },
    "notes": (
        "This dictionary is a public TPC-DS overlay. It is not an enterprise metric dictionary. "
        "Currency uses the documented metricsem_fx_v1 extension."
    ),
}
