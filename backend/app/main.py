"""DIWANA TRACE AI — FastAPI entry point (local development).

Run from backend/:  uvicorn app.main:app --reload

Access control: /api/douane/* → ROLE_DOUANE · /api/finance/* → ROLE_FINANCE · /api/admin/* → ROLE_ADMIN.
Every other /api route requires an authenticated user. There is no unauthenticated data route.
"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .db import init_db
from .routes import admin, common, douane, finance

app = FastAPI(title="DIWANA TRACE AI", version="2.0.0", docs_url=None, redoc_url=None, openapi_url=None)
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
                   allow_methods=["*"], allow_headers=["*"])
for r in (common.router, douane.router, finance.router, admin.router):
    app.include_router(r)


@app.on_event("startup")
def _startup():
    init_db()


@app.get("/")
def root():
    return {"name": "DIWANA TRACE AI"}
