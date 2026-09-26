"""Application settings loaded from backend/.env (never hardcode secrets)."""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
CACHE_DIR = DATA_DIR / "cache"
REFERENCE_DIR = DATA_DIR / "reference"
EXPORT_DIR = DATA_DIR / "exports"
REPORT_DIR = DATA_DIR / "reports"

load_dotenv(BASE_DIR / ".env")

for _d in (DATA_DIR, CACHE_DIR, REFERENCE_DIR, EXPORT_DIR, REPORT_DIR):
    _d.mkdir(parents=True, exist_ok=True)


def _env(name: str, default: str = "") -> str:
    return (os.getenv(name) or default).strip()


class Settings:
    groq_key_primary = _env("GROQ_API_KEY_PRIMARY")
    groq_key_secondary = _env("GROQ_API_KEY_SECONDARY")
    groq_base_url = "https://api.groq.com/openai/v1"
    groq_fast_model = _env("GROQ_FAST_MODEL")
    groq_reasoning_model = _env("GROQ_REASONING_MODEL")
    groq_vision_model = _env("GROQ_VISION_MODEL")

    database_url = _env("DATABASE_URL") or f"sqlite:///{(DATA_DIR / 'diwana.db').as_posix()}"
    # Authentication (signed session tokens). Empty = a random secret is generated once in data/.session_secret
    session_secret = _env("SESSION_SECRET")
    session_hours = float(_env("SESSION_HOURS", "8"))

    embedding_model = _env(
        "EMBEDDING_MODEL", "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    )

    rne_api_url = _env("RNE_API_URL")
    rne_api_key = _env("RNE_API_KEY")
    sinda_api_url = _env("SINDA_API_URL")
    sinda_api_key = _env("SINDA_API_KEY")
    meta_token = _env("META_GRAPH_ACCESS_TOKEN")
    meta_page_ids = [p for p in _env("META_PAGE_IDS").split(",") if p.strip()]
    tiktok_token = _env("TIKTOK_RESEARCH_API_TOKEN")
    authorized_commerce_sites = [
        s.strip() for s in _env("AUTHORIZED_COMMERCE_SITES").split(",") if s.strip()
    ]

    http_contact = _env("HTTP_CONTACT")  # URL or e-mail required by Wikimedia's API policy
    user_agent = "DiwanaTraceAI/1.0 (local customs-intelligence research; respects robots.txt" + (
        f"; {http_contact})" if http_contact else ")")
    http_timeout = 60.0


settings = Settings()
