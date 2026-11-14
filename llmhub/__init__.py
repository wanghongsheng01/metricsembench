"""Minimal OpenAI-compatible stand-in for the private `llmhub` gateway used in our runs.

The paper's LLM predictions were collected through a private, quota-enforcing gateway
(commercial OpenAI-compatible relays; channel names appear in stored rows as
`channel`). Third parties do not need it to reproduce any table: every table is
recomputed from the stored per-item predictions in `results/`. To *re-run* a model,
point this shim at any OpenAI-compatible endpoint:

    export MSB_LLM_BASE_URL=https://api.example.com/v1
    export MSB_LLM_API_KEY=...            # never commit keys
    # optional per-channel overrides: MSB_LLM_BASE_URL__<CHANNEL>, MSB_LLM_API_KEY__<CHANNEL>

Model strings are `<channel>/<model>`; the shim sends `<model>` to the endpoint.
Costs are not metered by the shim (cost_usd=0.0); use your provider's dashboard.
"""
from __future__ import annotations

import json
import os
import time
import urllib.request
from dataclasses import dataclass, field
from typing import Any

__all__ = ["chat", "ChatResult", "QuotaExceeded"]


class QuotaExceeded(RuntimeError):
    pass


@dataclass
class ChatResult:
    text: str
    channel: str
    model: str
    provider_model: str
    cost_usd: float = 0.0
    cached: bool = False
    latency_ms: float = 0.0
    experiment: str = ""
    raw: dict[str, Any] = field(default_factory=dict, repr=False)


def _env(name: str, channel: str) -> str:
    key = f"{name}__{channel.upper().replace('-', '_')}"
    v = os.environ.get(key) or os.environ.get(name)
    if not v:
        raise RuntimeError(f"set {name} (or {key}) to re-run LLM systems; tables do not need it")
    return v


def chat(model: str, messages, *, experiment: str = "", max_tokens: int | None = None,
         temperature: float | None = None, extra: dict | None = None, **_: Any) -> ChatResult:
    channel, _, name = model.partition("/")
    if not name:
        channel, name = "default", model
    if isinstance(messages, str):
        messages = [{"role": "user", "content": messages}]
    body: dict[str, Any] = {"model": name, "messages": messages}
    if max_tokens:
        body["max_tokens"] = max_tokens
    if temperature is not None:
        body["temperature"] = temperature
    body.update(extra or {})
    req = urllib.request.Request(
        _env("MSB_LLM_BASE_URL", channel).rstrip("/") + "/chat/completions",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "Authorization": "Bearer " + _env("MSB_LLM_API_KEY", channel)},
    )
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=600) as r:
        raw = json.loads(r.read().decode())
    text = raw["choices"][0]["message"].get("content") or ""
    return ChatResult(text=text, channel=channel, model=model, provider_model=raw.get("model", name),
                      latency_ms=(time.time() - t0) * 1000, experiment=experiment, raw=raw)
