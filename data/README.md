The DuckDB file `metricsem_tpcds_sf1.duckdb` (~330 MB) is generated locally and is gitignored.

    python -m msb.generate_db

This runs official DuckDB `CALL dsdgen(sf=1)` after installing the TPC-DS extension
from HTTPS (SHA256 pinned in `msb/config.py`). Do not commit the database or the
extension binary.
