"""Frozen fixture constants for MetricSemBench v0. Public, deterministic, no enterprise data."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
TASKS_DIR = ROOT / "tasks"
RESULTS_DIR = ROOT / "results"
DB_PATH = DATA_DIR / "metricsem_tpcds_sf1.duckdb"

SCALE_FACTOR = 1.0
SEED = 0
VERSION = "v0.1"

# DuckDB official TPC-DS extension (v2.0.0, linux_amd64). HTTP mirror returns 500; use HTTPS.
TPCDS_EXT_URL = "https://extensions.duckdb.org/v2.0.0/linux_amd64/tpcds.duckdb_extension.gz"
TPCDS_EXT_SHA256 = "42f6b9dbea6841c876cfd5d1511fdb2ff8f23c9c9e2a096459536964a2ea63de"

# Documented FX extension (metricsem_fx_v1).
# ss_net_paid is *reinterpreted* as already denominated in the store's assigned
# local currency. This is a semantic overlay on official TPC-DS amounts, not
# invented sales. Assignment is deterministic in store_sk. Rates are frozen
# fixture constants (order of magnitude of late-2001 G10 rates), not a claim
# about a specific official publication. The scientific point is non-additivity
# across units, which holds for any rates other than all-ones.
CURRENCIES = ("USD", "EUR", "GBP", "CAD")
FX_TO_USD = {"USD": 1.0, "EUR": 0.89, "GBP": 1.45, "CAD": 0.63}

# Retail fiscal year: starts February 1. FY Y covers Feb 1, Y .. Jan 31, Y+1.
# TPC-DS d_fy_year equals d_year (verified 0 rows differ), so we cannot use it.
RETAIL_FY_START_MONTH = 2  # February

# Sign-disagreement gate: ignore near-zero flips.
MIN_ABS_YOY = 0.01  # 1 percentage point

# Sparse YoY: refuse if prior-period ticket count is below this, or prior amount is 0.
SPARSE_MIN_PRIOR_TICKETS = 5

EXPECTED_COUNTS = {
    "store_sales": 2_880_404,
    "web_sales": 719_384,
    "catalog_sales": 1_441_548,
    "store": 12,
    "item": 18_000,
}
