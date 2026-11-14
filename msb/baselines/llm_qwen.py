"""Local Qwen2.5-7B baselines (GPU llama.cpp). Gold-blind. Three prompt styles."""
from __future__ import annotations

import json
import re

import duckdb

from msb.config import DB_PATH
from msb.llm_client import chat
from msb.prompts.schema_card import SCHEMA_CARD, SEMANTIC_RULES

DEFAULT_BASE = "http://127.0.0.1:18080/v1"
DEFAULT_MODEL = "qwen2.5-7b-instruct-q4_k_m"


def _extract_json(text: str) -> dict | None:
    if not text:
        return None
    text = text.strip()
    # fenced
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)
    blob = m.group(1) if m else None
    if blob is None:
        m = re.search(r"\{.*\}", text, re.S)
        blob = m.group(0) if m else None
    if not blob:
        return None
    try:
        return json.loads(blob)
    except json.JSONDecodeError:
        # trailing commas / single quotes — light repair
        t = blob.replace("'", '"')
        t = re.sub(r",\s*}", "}", t)
        t = re.sub(r",\s*]", "]", t)
        try:
            return json.loads(t)
        except json.JSONDecodeError:
            return None


def _extract_sql(text: str) -> str | None:
    if not text:
        return None
    m = re.search(r"```(?:sql)?\s*(.*?)```", text, re.S | re.I)
    if m:
        s = m.group(1).strip().rstrip(";")
        if re.match(r"^\s*(WITH|SELECT)\b", s, re.I):
            return s
    m = re.search(r"((?:WITH|SELECT)\b[\s\S]+?)(?:;|\Z)", text, re.I)
    if m:
        return m.group(1).strip().rstrip(";")
    return None


def exec_scalar(sql: str, db_path=None, timeout_s: float = 30.0) -> float | None:
    if not sql:
        return None
    s = sql.strip().rstrip(";")
    if not re.match(r"^\s*(WITH|SELECT)\b", s, re.I):
        return None
    # block obvious writes
    if re.search(r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|ATTACH|COPY|PRAGMA|INSTALL|LOAD)\b", s, re.I):
        return None
    try:
        con = duckdb.connect(str(db_path or DB_PATH), read_only=True)
        # DuckDB python doesn't have statement_timeout like PG; rely on being read-only + SF=1 speed.
        row = con.execute(s).fetchone()
        con.close()
        if not row or row[0] is None:
            return None
        return float(row[0])
    except Exception:
        return None


class QwenDirectBaseline:
    """Classic Text-to-SQL: always try to answer with a SQL scalar. Never refuses by instruction."""

    name = "qwen25_7b_direct"

    def __init__(self, base_url=DEFAULT_BASE, model=DEFAULT_MODEL, db_path=None):
        self.base_url = base_url
        self.model = model
        self.db_path = db_path or DB_PATH

    def answer(self, task_view: dict) -> dict:
        q = task_view["question_en"]
        messages = [
            {
                "role": "system",
                "content": (
                    "You are a Text-to-SQL assistant. Given a question and a DuckDB schema, "
                    "write ONE SQL query that returns a single scalar answer. "
                    "Return ONLY a JSON object {\"sql\": \"...\"}. Do not ask questions. "
                    "Always produce SQL.\n\n" + SCHEMA_CARD
                ),
            },
            {"role": "user", "content": f"Question: {q}\n\nJSON:"},
        ]
        try:
            resp = chat(
                base_url=self.base_url, model=self.model, messages=messages,
                cache_ns=self.name, task_id=task_view["id"], max_tokens=700, timeout=180,
            )
            content = resp["content"]
        except Exception as e:
            return {"behavior": "compute", "sql": None, "value": None, "error": type(e).__name__}
        js = _extract_json(content) or {}
        sql = js.get("sql") or _extract_sql(content)
        value = exec_scalar(sql, self.db_path) if sql else None
        return {
            "behavior": "compute",
            "sql": sql,
            "value": value,
            "raw": content[:1500],
            "usage": resp.get("usage") if "resp" in dir() else None,
        }


class QwenSemanticBaseline:
    """Prompted with metric-semantic contracts: may compute, clarify, or refuse."""

    name = "qwen25_7b_semantic"

    def __init__(self, base_url=DEFAULT_BASE, model=DEFAULT_MODEL, db_path=None):
        self.base_url = base_url
        self.model = model
        self.db_path = db_path or DB_PATH

    def answer(self, task_view: dict) -> dict:
        q = task_view["question_en"]
        zh = task_view.get("question_zh") or ""
        messages = [
            {
                "role": "system",
                "content": SCHEMA_CARD + "\n\n" + SEMANTIC_RULES,
            },
            {
                "role": "user",
                "content": f"Question (EN): {q}\nQuestion (ZH): {zh}\n\nJSON:",
            },
        ]
        try:
            resp = chat(
                base_url=self.base_url, model=self.model, messages=messages,
                cache_ns=self.name, task_id=task_view["id"], max_tokens=800, timeout=180,
            )
            content = resp["content"]
        except Exception as e:
            return {"behavior": "compute", "sql": None, "value": None, "error": type(e).__name__}
        js = _extract_json(content) or {}
        behavior = (js.get("behavior") or "").strip().lower()
        if behavior not in ("compute", "clarify", "refuse"):
            # fallback from text
            tl = content.lower()
            if "clarify" in tl and "compute" not in tl[:80]:
                behavior = "clarify"
            elif "refuse" in tl:
                behavior = "refuse"
            else:
                behavior = "compute"
        sql = js.get("sql") or (_extract_sql(content) if behavior == "compute" else None)
        value = exec_scalar(sql, self.db_path) if (behavior == "compute" and sql) else None
        return {
            "behavior": behavior,
            "sql": sql,
            "value": value,
            "refuse_reason_cat": js.get("refuse_reason"),
            "clarify_axes": js.get("clarify_axes"),
            "brief": js.get("brief"),
            "raw": content[:1500],
        }


# --- DIN-SQL style (decompose then generate, then optional self-correct) ---

_DIN_LINK = (
    "List the tables and columns from the schema that are needed to answer the question. "
    "Be concise. Then say whether the question is easy, non-nested, or nested."
)
_DIN_GEN = (
    "Using those tables, write ONE DuckDB SQL query that returns a single scalar. "
    "Return ONLY the SQL, no commentary."
)
_DIN_FIX = (
    "The SQL failed with this error. Write a corrected DuckDB SQL query only.\nError: {err}\nSQL: {sql}"
)


class QwenDINSQLBaseline:
    """DIN-SQL-inspired multi-step prompting on Qwen (schema link + generate + self-correct). Always answers."""

    name = "qwen25_7b_dinsql"

    def __init__(self, base_url=DEFAULT_BASE, model=DEFAULT_MODEL, db_path=None):
        self.base_url = base_url
        self.model = model
        self.db_path = db_path or DB_PATH

    def answer(self, task_view: dict) -> dict:
        q = task_view["question_en"]
        sys = (
            "You are following a decomposed Text-to-SQL procedure (DIN-SQL style) "
            "on a DuckDB TPC-DS database.\n\n" + SCHEMA_CARD
        )
        try:
            r1 = chat(
                base_url=self.base_url, model=self.model,
                messages=[
                    {"role": "system", "content": sys},
                    {"role": "user", "content": f"Question: {q}\n\n{_DIN_LINK}"},
                ],
                cache_ns=self.name + "_link", task_id=task_view["id"],
                max_tokens=400, timeout=180,
            )
            link = r1["content"]
            r2 = chat(
                base_url=self.base_url, model=self.model,
                messages=[
                    {"role": "system", "content": sys},
                    {"role": "user", "content": f"Question: {q}\n\nSchema linking notes:\n{link}\n\n{_DIN_GEN}"},
                ],
                cache_ns=self.name + "_gen", task_id=task_view["id"],
                max_tokens=600, timeout=180,
            )
            sql = _extract_sql(r2["content"]) or _extract_json(r2["content"] or "")
            if isinstance(sql, dict):
                sql = sql.get("sql")
            value = None
            err = None
            if sql:
                value = exec_scalar(sql, self.db_path)
                if value is None:
                    # try executing to get error for self-correct
                    try:
                        con = duckdb.connect(str(self.db_path), read_only=True)
                        con.execute(sql).fetchone()
                        con.close()
                    except Exception as e:
                        err = type(e).__name__ + ": " + str(e)[:300]
            if sql and value is None and err:
                r3 = chat(
                    base_url=self.base_url, model=self.model,
                    messages=[
                        {"role": "system", "content": sys},
                        {"role": "user", "content": _DIN_FIX.format(err=err, sql=sql) + f"\nQuestion: {q}"},
                    ],
                    cache_ns=self.name + "_fix", task_id=task_view["id"],
                    max_tokens=600, timeout=180,
                )
                sql2 = _extract_sql(r3["content"])
                if sql2:
                    sql = sql2
                    value = exec_scalar(sql, self.db_path)
            return {"behavior": "compute", "sql": sql, "value": value, "link": (link or "")[:500]}
        except Exception as e:
            return {"behavior": "compute", "sql": None, "value": None, "error": type(e).__name__}


# DAIL-SQL-inspired few-shot (hand-written examples NOT from the test set)
_DAIL_SHOTS = [
    (
        "What were total store-channel net sales (store_sales only) in calendar year 1998?",
        "SELECT SUM(ss_net_paid) FROM msb_store_sales WHERE d_year = 1998",
    ),
    (
        "How many distinct store tickets were there in calendar year 1998?",
        "SELECT COUNT(DISTINCT ss_ticket_number) FROM msb_store_sales WHERE d_year = 1998",
    ),
    (
        "What was the overall average order value of store sales in calendar year 1998, "
        "defined as total ss_net_paid divided by the number of distinct tickets?",
        "SELECT SUM(ss_net_paid)*1.0/NULLIF(COUNT(DISTINCT ss_ticket_number),0) "
        "FROM msb_store_sales WHERE d_year = 1998",
    ),
]


class QwenDAILSQLBaseline:
    """DAIL-SQL-inspired few-shot prompting on Qwen. Examples are 1998 queries, not test items. Always answers."""

    name = "qwen25_7b_dailsql"

    def __init__(self, base_url=DEFAULT_BASE, model=DEFAULT_MODEL, db_path=None):
        self.base_url = base_url
        self.model = model
        self.db_path = db_path or DB_PATH

    def answer(self, task_view: dict) -> dict:
        q = task_view["question_en"]
        shots = "\n\n".join(
            f"Q: {qq}\nSQL: {ss}" for qq, ss in _DAIL_SHOTS
        )
        messages = [
            {
                "role": "system",
                "content": (
                    "You are a Text-to-SQL model. Follow the example style. "
                    "Write ONE DuckDB SQL that returns a single scalar. "
                    "Return only SQL.\n\n" + SCHEMA_CARD + "\n\nExamples:\n" + shots
                ),
            },
            {"role": "user", "content": f"Q: {q}\nSQL:"},
        ]
        try:
            resp = chat(
                base_url=self.base_url, model=self.model, messages=messages,
                cache_ns=self.name, task_id=task_view["id"], max_tokens=700, timeout=180,
            )
            sql = _extract_sql(resp["content"])
            value = exec_scalar(sql, self.db_path) if sql else None
            return {"behavior": "compute", "sql": sql, "value": value, "raw": resp["content"][:800]}
        except Exception as e:
            return {"behavior": "compute", "sql": None, "value": None, "error": type(e).__name__}
