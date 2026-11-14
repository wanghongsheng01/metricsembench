"""Domain-general compute/clarify/refuse and DAIL-SQL for the public overlay.

NOT the TPC-DS SCHEMA_CARD. Schema comes from the official BIRD Mini-Dev
dev_tables (or a short note that the engine is not local, for Spider BQ/SF).
"""
from __future__ import annotations

import os
import subprocess
import sys
import textwrap

os.environ.pop("OPENAI_API_KEY", None)
os.environ.pop("ANTHROPIC_API_KEY", None)

from llmhub import QuotaExceeded, chat as hub_chat

from msb.baselines.llm_qwen import _extract_json, _extract_sql
from msb.public_schema import db_path, schema_card

PUBLIC_RULES = """
You are a metric-semantic assistant. Decide one of three behaviors:

1) compute — the question (plus any official evidence provided) states a unique,
   executable contract (windows, filters, formula). Then write ONE SQLite SQL
   query that returns the answer (a single scalar when the question asks for one
   number). Do not invent values; let SQL compute them.
2) clarify — at least two documented, numerically distinct contracts are consistent
   with the question (e.g. unweighted mean of rates vs rate of totals; calendar vs
   fiscal year; relative percent vs percentage-point change of an already-percent
   quantity; an unstated baseline of a "percentage increase"). Do NOT pick a default.
   Name the conflicting axes.
3) refuse — the request is illegal or undefined given the provided schema/evidence.

Return ONLY JSON:
  {"behavior": "compute"|"clarify"|"refuse",
   "sql": string or null,
   "clarify_axes": array of strings or null,
   "brief": one sentence}.
"""


def _hub(model, messages, experiment, max_tokens=800):
    return hub_chat(model, messages, experiment=experiment, max_tokens=max_tokens, temperature=0.0)


def exec_sqlite(sql, db_file, timeout_s=15):
    if not sql or not db_file or not Path_exists(db_file):
        return None
    helper = textwrap.dedent("""
        import sqlite3, sys, json
        con = sqlite3.connect('file:%s?mode=ro' % sys.argv[1], uri=True, timeout=5)
        try:
            rows = con.execute(sys.argv[2]).fetchall()
        except Exception as e:
            print('ERR', type(e).__name__, e)
            sys.exit(2)
        if not rows:
            sys.exit(0)
        v = rows[0][0] if len(rows)==1 and len(rows[0])==1 else None
        if v is None:
            print('NONSCALAR', len(rows), len(rows[0]) if rows else 0)
        else:
            print(repr(float(v) if isinstance(v,(int,float)) and not isinstance(v,bool) else v))
    """)
    try:
        r = subprocess.run(
            [sys.executable, "-c", helper, str(db_file), sql],
            capture_output=True, text=True, timeout=timeout_s,
        )
        out = (r.stdout or "").strip()
        if r.returncode != 0 or not out or out.startswith("ERR") or out.startswith("NONSCALAR"):
            return None
        return eval(out, {"__builtins__": {}})
    except subprocess.TimeoutExpired:
        return None
    except Exception:
        return None


def Path_exists(p):
    from pathlib import Path
    return Path(p).exists()


def _task_context(task_view: dict) -> tuple[str, str | None]:
    """Return (schema_text, db_file or None)."""
    db = task_view.get("db_id") or task_view.get("db")
    engine = task_view.get("engine") or "sqlite"
    if engine == "sqlite" and db:
        try:
            card = schema_card(db)
            path = db_path(db)
            return card, (str(path) if path.exists() else None)
        except Exception:
            return f"Database: {db} (SQLite). Schema unavailable.", None
    # Spider BQ / Snowflake / local without a file
    return (
        f"Engine: {engine}. Database: {db}. "
        "No local executable schema is provided for this item; if you compute, write SQL "
        "for that engine, knowing the value cannot be executed here.",
        None,
    )


class PublicSemanticBaseline:
    def __init__(self, model: str, experiment: str, name: str | None = None):
        self.model = model
        self.experiment = experiment
        self.name = name or (model.replace("/", "_") + "_semantic")

    def answer(self, task_view: dict) -> dict:
        q = task_view["question_en"]
        ev = task_view.get("evidence") or task_view.get("external_knowledge") or ""
        # question-only items: do not include EK
        if task_view.get("prompt_includes_evidence") is False:
            ev = ""
        card, dbfile = _task_context(task_view)
        user = f"Question: {q}\n"
        if ev:
            user += f"Official evidence / external knowledge:\n{ev}\n"
        user += "\nJSON:"
        messages = [
            {"role": "system", "content": PUBLIC_RULES + "\n\n" + card},
            {"role": "user", "content": user},
        ]
        try:
            r = _hub(self.model, messages, self.experiment, 800)
        except QuotaExceeded as e:
            return {"behavior": "refuse", "sql": None, "value": None, "error": "QuotaExceeded", "quota": str(e)[:200]}
        except Exception as e:
            return {"behavior": "compute", "sql": None, "value": None, "error": type(e).__name__, "err": str(e)[:300]}
        content = r.text or ""
        js = _extract_json(content) or {}
        behavior = (js.get("behavior") or "").strip().lower()
        if behavior not in ("compute", "clarify", "refuse"):
            tl = content.lower()
            if "clarify" in tl and "compute" not in tl[:40]:
                behavior = "clarify"
            elif "refuse" in tl:
                behavior = "refuse"
            else:
                behavior = "compute"
        sql = js.get("sql") or (_extract_sql(content) if behavior == "compute" else None)
        value = exec_sqlite(sql, dbfile) if (behavior == "compute" and sql and dbfile) else None
        return {
            "behavior": behavior,
            "sql": sql,
            "value": value,
            "clarify_axes": js.get("clarify_axes"),
            "brief": js.get("brief"),
            "raw": content[:1500],
            "cost_usd": r.cost_usd,
            "cached": r.cached,
        }


_PUBLIC_SHOTS = [
    (
        "How many rows are in the customers table?",
        "SELECT COUNT(*) FROM customers",
    ),
    (
        "What is the total Consumption in year 2012?",
        "SELECT SUM(Consumption) FROM yearmonth WHERE SUBSTR(Date, 1, 4) = '2012'",
    ),
    (
        "What is the average overall_rating of all players?",
        "SELECT AVG(overall_rating) FROM Player_Attributes",
    ),
]


class PublicDAILSQLBaseline:
    """Always-answer DAIL-style few-shot Text-to-SQL on the item's official schema."""

    def __init__(self, model="ark/deepseek-v4-pro", experiment="metricsembench-public-dailsql", name=None):
        self.model = model
        self.experiment = experiment
        self.name = name or (model.replace("/", "_") + "_dailsql")

    def answer(self, task_view: dict) -> dict:
        q = task_view["question_en"]
        ev = task_view.get("evidence") or task_view.get("external_knowledge") or ""
        if task_view.get("prompt_includes_evidence") is False:
            ev = ""
        card, dbfile = _task_context(task_view)
        shots = "\n\n".join(f"Q: {a}\nSQL: {b}" for a, b in _PUBLIC_SHOTS)
        messages = [
            {
                "role": "system",
                "content": (
                    "You are a Text-to-SQL assistant (DAIL-SQL style). "
                    "Always write one SQLite SQL query. Return ONLY JSON {\"sql\": \"...\"}. "
                    "Do not refuse or ask questions.\n\n" + card + "\n\nExamples:\n" + shots
                ),
            },
            {"role": "user", "content": (f"Evidence: {ev}\n" if ev else "") + f"Question: {q}\n\nJSON:"},
        ]
        try:
            r = _hub(self.model, messages, self.experiment, 700)
            sql = ((_extract_json(r.text or "") or {}).get("sql")) or _extract_sql(r.text or "")
            value = exec_sqlite(sql, dbfile) if sql and dbfile else None
            return {"behavior": "compute", "sql": sql, "value": value, "cost_usd": r.cost_usd, "cached": r.cached, "raw": (r.text or "")[:800]}
        except QuotaExceeded as e:
            return {"behavior": "compute", "sql": None, "value": None, "error": "QuotaExceeded", "quota": str(e)[:200]}
        except Exception as e:
            return {"behavior": "compute", "sql": None, "value": None, "error": type(e).__name__, "err": str(e)[:300]}
