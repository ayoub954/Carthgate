"""LLMProvider — Groq (OpenAI-compatible) with PRIMARY → SECONDARY key fallback.

Handles timeouts, rate limits (429), transient errors (5xx) and retries.
Keys are never logged or returned; errors are reported by status code / class only.
All LLM calls go through FastAPI (never from the browser).
"""
from __future__ import annotations

import time
from dataclasses import dataclass

import httpx

from ..config import settings


class LLMUnavailable(Exception):
    pass


@dataclass
class LLMResult:
    text: str
    model: str
    key_slot: str  # "primary" / "secondary"
    latency: float


class LLMProvider:
    def __init__(self):
        self.keys = [("primary", settings.groq_key_primary), ("secondary", settings.groq_key_secondary)]
        self.keys = [(slot, k) for slot, k in self.keys if k]
        self.base = settings.groq_base_url
        self.last_error: str | None = None
        self.last_slot: str | None = None

    @property
    def configured(self) -> bool:
        return bool(self.keys)

    def _request(self, method: str, path: str, json: dict | None = None, timeout: float = 45.0):
        if not self.keys:
            raise LLMUnavailable("No GROQ_API_KEY_PRIMARY / GROQ_API_KEY_SECONDARY configured")
        errors = []
        for slot, key in self.keys:
            for attempt in range(3):
                try:
                    r = httpx.request(method, self.base + path, json=json, timeout=timeout,
                                      headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
                except (httpx.TimeoutException, httpx.TransportError) as e:
                    errors.append(f"{slot}: {e.__class__.__name__}")
                    time.sleep(1.5 * (attempt + 1))
                    continue
                if r.status_code == 200:
                    self.last_slot, self.last_error = slot, None
                    return r.json(), slot
                if r.status_code in (401, 403):
                    errors.append(f"{slot}: HTTP {r.status_code} (invalid key or no access)")
                    break  # try next key
                if r.status_code == 429:
                    errors.append(f"{slot}: HTTP 429 (quota / rate limit)")
                    break  # quota → secondary key immediately
                if r.status_code >= 500:
                    errors.append(f"{slot}: HTTP {r.status_code}")
                    time.sleep(1.5 * (attempt + 1))
                    continue
                errors.append(f"{slot}: HTTP {r.status_code} {r.text[:160]}")
                break
        self.last_error = "; ".join(errors)
        raise LLMUnavailable(self.last_error)

    def list_models(self) -> list[dict]:
        data, _ = self._request("GET", "/models", timeout=20)
        return data.get("data", [])

    def chat(self, model: str, messages: list[dict], temperature: float = 0.2, max_tokens: int = 900,
             json_mode: bool = False) -> LLMResult:
        body = {"model": model, "messages": messages, "temperature": temperature, "max_tokens": max_tokens}
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        t = time.time()
        data, slot = self._request("POST", "/chat/completions", json=body)
        return LLMResult(data["choices"][0]["message"]["content"], data.get("model", model), slot, time.time() - t)


provider = LLMProvider()
