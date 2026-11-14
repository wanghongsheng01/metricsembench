"""MetricSemBench LLM baselines via llmhub (quota, ledger, experiment tags). Gold-blind."""
from __future__ import annotations

import os

from llmhub import QuotaExceeded, chat as hub_chat

from msb.baselines.llm_qwen import _extract_json, _extract_sql, exec_scalar
from msb.config import DB_PATH
from msb.prompts.schema_card import SCHEMA_CARD, SEMANTIC_RULES

# Do not send the invalid OPENAI_API_KEY wrapper through llmhub.
os.environ.pop("OPENAI_API_KEY", None)
os.environ.pop("ANTHROPIC_API_KEY", None)


def _hub(model: str, messages: list[dict], *, experiment: str, max_tokens: int = 800, temperature: float = 0.0):
    return hub_chat(
        model,
        messages,
        experiment=experiment,
        max_tokens=max_tokens,
        temperature=temperature,
    )


class HubDirectBaseline:
    """Classic Text-to-SQL: always produce SQL. model e.g. tokens1688/gpt-6-sol."""

    def __init__(self, model: str, experiment: str, name: str | None = None, db_path=None):
        self.model = model
        self.experiment = experiment
        self.name = name or (model.replace("/", "_") + "_direct")
        self.db_path = db_path or DB_PATH
        self.last_cost = 0.0
        self.last_cached = False

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
            r = _hub(self.model, messages, experiment=self.experiment, max_tokens=700)
        except QuotaExceeded as e:
            return {"behavior": "compute", "sql": None, "value": None, "error": "QuotaExceeded", "quota": str(e)[:200]}
        except Exception as e:
            return {"behavior": "compute", "sql": None, "value": None, "error": type(e).__name__, "err": str(e)[:300]}
        self.last_cost = r.cost_usd
        self.last_cached = r.cached
        content = r.text or ""
        js = _extract_json(content) or {}
        sql = js.get("sql") or _extract_sql(content)
        value = exec_scalar(sql, self.db_path) if sql else None
        return {
            "behavior": "compute",
            "sql": sql,
            "value": value,
            "raw": content[:1500],
            "cost_usd": r.cost_usd,
            "cached": r.cached,
            "channel": r.channel,
            "provider_model": r.provider_model,
        }


class HubSemanticBaseline:
    """Prompted with metric-semantic contracts: compute / clarify / refuse."""

    def __init__(self, model: str, experiment: str, name: str | None = None, db_path=None):
        self.model = model
        self.experiment = experiment
        self.name = name or (model.replace("/", "_") + "_semantic")
        self.db_path = db_path or DB_PATH
        self.last_cost = 0.0
        self.last_cached = False

    def answer(self, task_view: dict) -> dict:
        q = task_view["question_en"]
        zh = task_view.get("question_zh") or ""
        messages = [
            {"role": "system", "content": SCHEMA_CARD + "\n\n" + SEMANTIC_RULES},
            {"role": "user", "content": f"Question (EN): {q}\nQuestion (ZH): {zh}\n\nJSON:"},
        ]
        try:
            r = _hub(self.model, messages, experiment=self.experiment, max_tokens=800)
        except QuotaExceeded as e:
            return {"behavior": "compute", "sql": None, "value": None, "error": "QuotaExceeded", "quota": str(e)[:200]}
        except Exception as e:
            return {"behavior": "compute", "sql": None, "value": None, "error": type(e).__name__, "err": str(e)[:300]}
        self.last_cost = r.cost_usd
        self.last_cached = r.cached
        content = r.text or ""
        js = _extract_json(content) or {}
        behavior = (js.get("behavior") or "").strip().lower()
        if behavior not in ("compute", "clarify", "refuse"):
            tl = content.lower()
            if "\"clarify\"" in tl or (tl.find("clarify") >= 0 and tl.find("compute") > 80):
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
            "cost_usd": r.cost_usd,
            "cached": r.cached,
            "channel": r.channel,
            "provider_model": r.provider_model,
        }
