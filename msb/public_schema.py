"""Compact SQLite schema cards from official BIRD Mini-Dev dev_tables.json."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

TABLES = Path(__file__).resolve().parents[1] / "data" / "public_bench" / "bird_minidev" / "dev_tables.json"
DBDIR = Path(__file__).resolve().parents[1] / "data" / "public_bench" / "bird_minidev" / "databases"


@lru_cache(maxsize=1)
def _tables() -> dict:
    raw = json.loads(TABLES.read_text(encoding="utf-8"))
    return {r["db_id"]: r for r in raw}


def schema_card(db_id: str, max_chars: int = 6000) -> str:
    r = _tables()[db_id]
    tnames = r["table_names_original"]
    cols = r["column_names_original"]  # [table_idx, name], table_idx -1 is *
    types = r.get("column_types") or []
    by_t: dict[int, list[str]] = {i: [] for i in range(len(tnames))}
    for i, (ti, name) in enumerate(cols):
        if ti < 0:
            continue
        ty = types[i] if i < len(types) else ""
        by_t[ti].append(f"{name} {ty}".strip())
    lines = [f"Database: {db_id} (SQLite).", "Tables:"]
    for i, tn in enumerate(tnames):
        lines.append(f"- {tn}(" + ", ".join(by_t.get(i) or []) + ")")
    # FKs
    fks = r.get("foreign_keys") or []
    if fks:
        lines.append("Foreign keys:")
        for a, b in fks:
            # indices into column_names_original
            def col(idx):
                ti, n = cols[idx]
                return f"{tnames[ti]}.{n}" if ti >= 0 else n
            try:
                lines.append(f"- {col(a)} -> {col(b)}")
            except Exception:
                continue
    text = "\n".join(lines)
    if len(text) > max_chars:
        text = text[: max_chars - 20] + "\n… [schema truncated]"
    return text


def db_path(db_id: str) -> Path:
    return DBDIR / f"{db_id}.sqlite"
