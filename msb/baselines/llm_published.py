"""Published NL2SQL prompting (DIN-SQL, DAIL-SQL) via llmhub. Always-answer protocols."""
from __future__ import annotations

import os

os.environ.pop("OPENAI_API_KEY", None)
os.environ.pop("ANTHROPIC_API_KEY", None)

from llmhub import QuotaExceeded, chat as hub_chat

from msb.baselines.llm_qwen import _extract_json, _extract_sql, exec_scalar as _exec_scalar
from msb.config import DB_PATH
from msb.prompts.schema_card import SCHEMA_CARD

import subprocess, sys, tempfile, textwrap

def exec_scalar(sql, db_path, timeout_s=12):
    """Execute SQL with a hard subprocess timeout so a bad plan cannot hang the eval."""
    if not sql:
        return None
    helper = textwrap.dedent(f"""
        import duckdb, sys
        con = duckdb.connect(sys.argv[1], read_only=True)
        try:
            con.execute("SET memory_limit='1GB'")
        except Exception:
            pass
        v = con.execute(sys.argv[2]).fetchone()
        print(('' if v is None or v[0] is None else repr(float(v[0]) if not isinstance(v[0], str) else v[0])))
    """)
    try:
        r = subprocess.run(
            [sys.executable, "-c", helper, str(db_path), sql],
            capture_output=True, text=True, timeout=timeout_s,
        )
        out = (r.stdout or "").strip()
        if r.returncode != 0 or not out:
            return None
        return eval(out, {"__builtins__": {}}) if out not in ("", "None") else None
    except subprocess.TimeoutExpired:
        return None
    except Exception:
        return None


_DIN_LINK = (
    "Step 1 — Schema linking: list the tables, columns, metric names, and filters "
    "this question needs. Be brief."
)
_DIN_GEN = (
    "Step 2 — Generate a single DuckDB SQL query that returns one scalar. "
    "Return ONLY JSON {\"sql\": \"...\"}. Always produce SQL; do not refuse or ask questions."
)
_DIN_FIX = (
    "Step 3 — The SQL failed with error:\n{err}\n\nSQL was:\n{sql}\n\n"
    "Write a corrected DuckDB SQL. Return ONLY JSON {{\"sql\": \"...\"}}."
)

# Hand-written few-shots, years outside the main test emphasis (1998), not copied from test gold.
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


def _hub(model, messages, experiment, max_tokens=600):
    return hub_chat(model, messages, experiment=experiment, max_tokens=max_tokens, temperature=0.0)


class HubDINSQLBaseline:
    """DIN-SQL style: schema link + generate + self-correct. Always computes. Pourreza & Rafiei 2023."""

    def __init__(self, model="ark/deepseek-v4-pro", experiment="metricsembench-v0.1-dinsql", name=None, db_path=None):
        self.model = model
        self.experiment = experiment
        self.name = name or (model.replace("/", "_") + "_dinsql")
        self.db_path = db_path or DB_PATH

    def answer(self, task_view: dict) -> dict:
        q = task_view["question_en"]
        sys = (
            "You are following a decomposed Text-to-SQL procedure (DIN-SQL style) "
            "on a DuckDB TPC-DS database.\n\n" + SCHEMA_CARD
        )
        spent = 0.0
        try:
            r1 = _hub(self.model, [
                {"role": "system", "content": sys},
                {"role": "user", "content": f"Question: {q}\n\n{_DIN_LINK}"},
            ], self.experiment, 400)
            spent += r1.cost_usd
            link = r1.text or ""
            r2 = _hub(self.model, [
                {"role": "system", "content": sys},
                {"role": "user", "content": f"Question: {q}\n\nSchema linking notes:\n{link}\n\n{_DIN_GEN}"},
            ], self.experiment, 600)
            spent += r2.cost_usd
            sql = _extract_sql(r2.text or "") or ((_extract_json(r2.text or "") or {}).get("sql"))
            value = exec_scalar(sql, self.db_path) if sql else None
            if sql and value is None:
                import duckdb
                err = None
                try:
                    con = duckdb.connect(str(self.db_path), read_only=True)
                    con.execute(sql).fetchone()
                    con.close()
                except Exception as e:
                    err = type(e).__name__ + ": " + str(e)[:300]
                if err:
                    r3 = _hub(self.model, [
                        {"role": "system", "content": sys},
                        {"role": "user", "content": _DIN_FIX.format(err=err, sql=sql) + f"\nQuestion: {q}"},
                    ], self.experiment, 600)
                    spent += r3.cost_usd
                    sql2 = _extract_sql(r3.text or "") or ((_extract_json(r3.text or "") or {}).get("sql"))
                    if sql2:
                        sql = sql2
                        value = exec_scalar(sql, self.db_path)
            return {"behavior": "compute", "sql": sql, "value": value, "cost_usd": spent, "cached": r2.cached, "link": (link or "")[:400]}
        except QuotaExceeded as e:
            return {"behavior": "compute", "sql": None, "value": None, "error": "QuotaExceeded", "quota": str(e)[:200], "cost_usd": spent}
        except Exception as e:
            return {"behavior": "compute", "sql": None, "value": None, "error": type(e).__name__, "err": str(e)[:300], "cost_usd": spent}


class HubDAILSQLBaseline:
    """DAIL-SQL style: few-shot example-similar prompting. Always computes. Gao et al. 2024."""

    def __init__(self, model="ark/deepseek-v4-pro", experiment="metricsembench-v0.1-dailsql", name=None, db_path=None):
        self.model = model
        self.experiment = experiment
        self.name = name or (model.replace("/", "_") + "_dailsql")
        self.db_path = db_path or DB_PATH

    def answer(self, task_view: dict) -> dict:
        q = task_view["question_en"]
        shots = "\n\n".join(f"Q: {a}\nSQL: {b}" for a, b in _DAIL_SHOTS)
        messages = [
            {
                "role": "system",
                "content": (
                    "You are a Text-to-SQL assistant using example-retrieval prompting (DAIL-SQL style). "
                    "Always write one DuckDB SQL that returns a single scalar. "
                    "Return ONLY JSON {\"sql\": \"...\"}. Do not refuse or ask questions.\n\n"
                    + SCHEMA_CARD
                    + "\n\nExamples:\n"
                    + shots
                ),
            },
            {"role": "user", "content": f"Question: {q}\n\nJSON:"},
        ]
        try:
            r = _hub(self.model, messages, self.experiment, 700)
            sql = ((_extract_json(r.text or "") or {}).get("sql")) or _extract_sql(r.text or "")
            value = exec_scalar(sql, self.db_path) if sql else None
            return {"behavior": "compute", "sql": sql, "value": value, "cost_usd": r.cost_usd, "cached": r.cached, "raw": (r.text or "")[:800]}
        except QuotaExceeded as e:
            return {"behavior": "compute", "sql": None, "value": None, "error": "QuotaExceeded", "quota": str(e)[:200]}
        except Exception as e:
            return {"behavior": "compute", "sql": None, "value": None, "error": type(e).__name__, "err": str(e)[:300]}
