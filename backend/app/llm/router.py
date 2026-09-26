"""AIModelRouter — routes tasks to models ACTUALLY available at the provider (/models).

FAST      → extraction, classification, normalisation
REASONING → analysis, recommendations, reports
VISION    → image understanding (only if a vision-capable model is listed)
Semantic matching is done locally by the Sentence Transformer (not the LLM).
No model id is hardcoded: candidates are ranked from the live list by size hints.
"""
from __future__ import annotations

import re
import time

from ..config import settings
from .provider import LLMUnavailable, provider

_cache = {"ts": 0.0, "models": [], "error": None}
EXCLUDE = re.compile(r"whisper|tts|guard|playai|orpheus|embed|moderation|prompt-guard|distil", re.I)
VISION = re.compile(r"vision|llama-4|scout|maverick|pixtral|llava", re.I)


def _size(mid: str) -> float:
    m = re.search(r"(\d+(?:\.\d+)?)\s*b\b", mid.lower().replace("-", " "))
    return float(m.group(1)) if m else 0.0


def available_models(force: bool = False) -> list[str]:
    if not force and time.time() - _cache["ts"] < 3600 and _cache["models"]:
        return _cache["models"]
    try:
        ms = [m["id"] for m in provider.list_models() if m.get("active", True)]
        _cache.update(ts=time.time(), models=ms, error=None)
    except LLMUnavailable as e:
        _cache.update(ts=time.time(), models=[], error=str(e))
    return _cache["models"]


def route(task: str) -> str | None:
    """task ∈ {fast, reasoning, vision}. Returns an available model id or None."""
    models = [m for m in available_models() if not EXCLUDE.search(m)]
    if not models:
        return None
    override = {"fast": settings.groq_fast_model, "reasoning": settings.groq_reasoning_model,
                "vision": settings.groq_vision_model}.get(task)
    if override and override in models:
        return override
    if task == "vision":
        vis = [m for m in models if VISION.search(m)]
        return max(vis, key=_size) if vis else None
    text = [m for m in models if not re.search(r"vision", m, re.I)] or models
    sized = sorted(text, key=_size)
    if task == "fast":
        small = [m for m in sized if 0 < _size(m) <= 20] or [m for m in sized if "instant" in m] or sized
        return small[0]
    return sized[-1]


def status() -> dict:
    ms = available_models()
    return {"configured": provider.configured, "keys": [slot for slot, _ in provider.keys],
            "available_models": ms, "error": _cache["error"],
            "routes": {t: route(t) for t in ("fast", "reasoning", "vision")} if ms else {},
            "last_key_slot_used": provider.last_slot}


def complete(task: str, system: str, user: str, json_mode: bool = False, max_tokens: int = 900):
    model = route(task)
    if not model:
        raise LLMUnavailable(_cache["error"] or f"No available model for task '{task}'")
    return provider.chat(model, [{"role": "system", "content": system}, {"role": "user", "content": user}],
                         json_mode=json_mode, max_tokens=max_tokens)
