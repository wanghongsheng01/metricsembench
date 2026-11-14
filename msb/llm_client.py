"""OpenAI-compatible chat client with on-disk cache. No secrets written to cache."""
from __future__ import annotations

import hashlib
import json
import time
import urllib.error
import urllib.request
from pathlib import Path

from msb.config import RESULTS_DIR

CACHE = RESULTS_DIR / "llm_cache"


def _cache_key(model: str, mode: str, task_id: str, prompt_hash: str) -> Path:
    safe = "".join(c if c.isalnum() or c in "-_." else "_" for c in f"{model}_{mode}_{task_id}")
    return CACHE / f"{safe}_{prompt_hash[:10]}.json"


def chat(
    *,
    base_url: str,
    model: str,
    messages: list[dict],
    temperature: float = 0.0,
    max_tokens: int = 1024,
    timeout: int = 180,
    cache_ns: str | None = None,
    task_id: str | None = None,
    retries: int = 2,
) -> dict:
    """Return {content, usage, raw_finish, cached}. Never logs API keys."""
    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "seed": 0,
    }
    blob = json.dumps({"model": model, "messages": messages, "temperature": temperature, "max_tokens": max_tokens}, ensure_ascii=False)
    ph = hashlib.sha256(blob.encode()).hexdigest()
    if cache_ns and task_id:
        CACHE.mkdir(parents=True, exist_ok=True)
        cp = _cache_key(cache_ns, "chat", task_id, ph)
        if cp.exists():
            d = json.loads(cp.read_text(encoding="utf-8"))
            d["cached"] = True
            return d

    url = base_url.rstrip("/") + "/chat/completions"
    data = json.dumps(payload).encode()
    last_err = None
    for attempt in range(retries + 1):
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                body = json.loads(r.read().decode("utf-8", "replace"))
            content = body["choices"][0]["message"].get("content") or ""
            out = {
                "content": content,
                "usage": body.get("usage") or {},
                "finish": body["choices"][0].get("finish_reason"),
                "cached": False,
                "model": model,
            }
            if cache_ns and task_id:
                cp.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
            return out
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
            last_err = e
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"chat failed after retries: {type(last_err).__name__}: {last_err}")
