"""Generate official TPC-DS SF=1 via DuckDB dsdgen and install MetricSem views/extensions."""
from __future__ import annotations

import hashlib
import urllib.request
from pathlib import Path

import duckdb

from msb.config import (
    CURRENCIES,
    DB_PATH,
    EXPECTED_COUNTS,
    FX_TO_USD,
    SCALE_FACTOR,
    TPCDS_EXT_SHA256,
    TPCDS_EXT_URL,
    DATA_DIR,
)


def _download_extension(dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    gz = dest.with_suffix(".duckdb_extension.gz")
    if not gz.exists() or hashlib.sha256(gz.read_bytes()).hexdigest() != TPCDS_EXT_SHA256:
        print(f"downloading {TPCDS_EXT_URL}")
        # The extension CDN rejects the default Python-urllib user agent (HTTP 403).
        req = urllib.request.Request(TPCDS_EXT_URL, headers={"User-Agent": "duckdb-metricsembench/1.0"})
        with urllib.request.urlopen(req, timeout=300) as r:
            gz.write_bytes(r.read())
    digest = hashlib.sha256(gz.read_bytes()).hexdigest()
    if digest != TPCDS_EXT_SHA256:
        raise RuntimeError(f"tpcds extension sha256 mismatch: {digest}")
    raw = dest
    import gzip, shutil
    if not raw.exists() or raw.stat().st_mtime < gz.stat().st_mtime:
        with gzip.open(gz, "rb") as src, open(raw, "wb") as out:
            shutil.copyfileobj(src, out)
    return raw


def _load_tpcds(con: duckdb.DuckDBPyConnection) -> None:
    ext = _download_extension(DATA_DIR / "vendor" / "tpcds.duckdb_extension")
    con.execute(f"INSTALL '{ext.as_posix()}';")
    con.execute("LOAD tpcds;")


def _create_extensions(con: duckdb.DuckDBPyConnection) -> None:
    """Documented, deterministic overlays. Sales amounts stay official TPC-DS."""
    ccy_rows = ", ".join(
        f"({i}, '{CURRENCIES[(i - 1) % 4]}')" for i in range(1, 13)
    )
    fx_rows = ", ".join(f"('{c}', {FX_TO_USD[c]})" for c in CURRENCIES)
    con.execute(
        f"""
        CREATE OR REPLACE TABLE msb_store_currency AS
        SELECT * FROM (VALUES {ccy_rows}) AS t(s_store_sk, currency);

        CREATE OR REPLACE TABLE msb_fx_to_usd AS
        SELECT * FROM (VALUES {fx_rows}) AS t(currency, fx_to_usd);

        CREATE OR REPLACE VIEW msb_date AS
        SELECT
          d.*,
          -- Retail FY starting February 1: shift by 31 days so Feb 1..Jan 31 share a year.
          CAST(strftime(d.d_date - INTERVAL 31 DAY, '%Y') AS INTEGER) AS retail_fy,
          CASE
            WHEN d.d_moy >= 2 THEN d.d_moy - 1
            ELSE 12
          END AS retail_fy_month
        FROM date_dim d;

        CREATE OR REPLACE VIEW msb_store_sales AS
        SELECT
          ss.*,
          d.d_date,
          d.d_year,
          d.d_moy,
          d.d_dom,
          d.d_month_seq,
          d.d_quarter_seq,
          d.d_qoy,
          d.retail_fy,
          d.retail_fy_month,
          s.s_store_name,
          s.s_state,
          s.s_city,
          s.s_country,
          sc.currency AS store_currency,
          fx.fx_to_usd,
          ss.ss_net_paid * fx.fx_to_usd AS net_paid_usd,
          i.i_item_id,
          i.i_category,
          i.i_brand,
          i.i_class,
          i.i_rec_start_date,
          i.i_rec_end_date,
          i.i_product_name
        FROM store_sales ss
        JOIN msb_date d ON ss.ss_sold_date_sk = d.d_date_sk
        JOIN store s ON ss.ss_store_sk = s.s_store_sk
        JOIN msb_store_currency sc ON sc.s_store_sk = s.s_store_sk
        JOIN msb_fx_to_usd fx ON fx.currency = sc.currency
        JOIN item i ON ss.ss_item_sk = i.i_item_sk;

        CREATE OR REPLACE VIEW msb_web_sales AS
        SELECT
          ws.*,
          d.d_date,
          d.d_year,
          d.d_moy,
          d.retail_fy,
          i.i_item_id,
          i.i_category
        FROM web_sales ws
        JOIN msb_date d ON ws.ws_sold_date_sk = d.d_date_sk
        JOIN item i ON ws.ws_item_sk = i.i_item_sk;

        CREATE OR REPLACE VIEW msb_catalog_sales AS
        SELECT
          cs.*,
          d.d_date,
          d.d_year,
          d.d_moy,
          d.retail_fy,
          i.i_item_id,
          i.i_category
        FROM catalog_sales cs
        JOIN msb_date d ON cs.cs_sold_date_sk = d.d_date_sk
        JOIN item i ON cs.cs_item_sk = i.i_item_sk;

        CREATE OR REPLACE VIEW msb_store_returns AS
        SELECT
          sr.*,
          d.d_date,
          d.d_year,
          d.d_moy
        FROM store_returns sr
        JOIN msb_date d ON sr.sr_returned_date_sk = d.d_date_sk;
        """
    )


def generate(force: bool = False) -> Path:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    need_gen = force or not DB_PATH.exists()
    con = duckdb.connect(str(DB_PATH))
    if not need_gen:
        try:
            for t, n in EXPECTED_COUNTS.items():
                got = con.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
                if got != n:
                    print(f"count mismatch {t}: {got} != {n}, regenerating")
                    need_gen = True
                    break
        except Exception as e:
            print("existing db unusable, regenerating:", e)
            need_gen = True
    if need_gen:
        con.close()
        if DB_PATH.exists():
            DB_PATH.unlink()
        con = duckdb.connect(str(DB_PATH))
        _load_tpcds(con)
        print(f"CALL dsdgen(sf={SCALE_FACTOR}) ...")
        con.execute(f"CALL dsdgen(sf={SCALE_FACTOR});")
        for t, n in EXPECTED_COUNTS.items():
            got = con.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
            if got != n:
                raise RuntimeError(f"unexpected {t} count {got}, expected {n}")
        print("dsdgen verified")
    _create_extensions(con)
    # completeness point of this fixture
    mx = con.execute("SELECT max(d_date) FROM msb_store_sales").fetchone()[0]
    print("max store_sales date:", mx)
    con.execute("CHECKPOINT;")
    con.close()
    print("database ready:", DB_PATH, "size_mb=", round(DB_PATH.stat().st_size / 1e6, 2))
    return DB_PATH


if __name__ == "__main__":
    generate()
