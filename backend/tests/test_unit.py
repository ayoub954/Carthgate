"""Unit tests (synthetic fixtures, test-only)."""
import io
from datetime import datetime, timedelta

import httpx
import numpy as np
import openpyxl
import pandas as pd
import pytest

from app.ml import entry, forecast, fragmentation, risk
from app.models import CustomsImport, EntryPoint


# ---------------------------------------------------------------- INS parser
def _ins_xlsx():
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append([None, "Commerce par chapitre"])
    ws.append(["CODE", "LIBELLE", "Export VALEUR 2 mois 2025", "Export POIDS 2 mois 2025", "Import VALEUR 2 mois 2025", "Import POIDS 2 mois 2025"])
    ws.append([None, None, "TND", "KG", "TND", "KG"])
    ws.append(["85", "Machines électriques", 100, 10, 300, 30])
    ws.append(["TOTAL", None, 1, 1, 1, 1])
    b = io.BytesIO()
    wb.save(b)
    return b.getvalue()


def test_ins_chapter_parser_flows_and_measures():
    from app.providers.ins import INSDataProvider
    rows = INSDataProvider().parse_chapter(_ins_xlsx())
    by = {r["flow"]: r for r in rows}
    assert set(by) == {"M", "X"}
    assert by["M"]["value_tnd"] == 300 and by["M"]["weight_kg"] == 30
    assert by["M"]["months"] == 2 and by["M"]["year"] == 2025 and by["M"]["hs"] == "85"


# ---------------------------------------------------------------- LLM fallback
def test_llm_primary_quota_falls_back_to_secondary(monkeypatch):
    from app.llm.provider import LLMProvider
    p = LLMProvider()
    p.keys = [("primary", "k1"), ("secondary", "k2")]
    calls = []

    def fake_request(method, url, json=None, timeout=None, headers=None):
        key = headers["Authorization"].split()[-1]
        calls.append(key)
        req = httpx.Request(method, url)
        if key == "k1":
            return httpx.Response(429, request=req, json={"error": "rate"})
        return httpx.Response(200, request=req, json={"choices": [{"message": {"content": "ok"}}], "model": "m"})

    monkeypatch.setattr(httpx, "request", fake_request)
    r = p.chat("m", [{"role": "user", "content": "hi"}])
    assert r.text == "ok" and r.key_slot == "secondary" and calls == ["k1", "k2"]


def test_llm_errors_never_contain_keys(monkeypatch):
    from app.llm.provider import LLMProvider, LLMUnavailable
    p = LLMProvider()
    p.keys = [("primary", "SECRET-1"), ("secondary", "SECRET-2")]
    monkeypatch.setattr(httpx, "request", lambda *a, **k: httpx.Response(401, request=httpx.Request("GET", "http://x")))
    with pytest.raises(LLMUnavailable) as e:
        p.list_models()
    assert "SECRET" not in str(e.value)


def test_router_uses_only_listed_models(monkeypatch):
    from app.llm import router
    monkeypatch.setattr(router, "available_models", lambda force=False: ["llama-3.1-8b-instant", "llama-3.3-70b-versatile", "whisper-large-v3"])
    assert router.route("fast") == "llama-3.1-8b-instant"
    assert router.route("reasoning") == "llama-3.3-70b-versatile"
    assert router.route("vision") is None


# ---------------------------------------------------------------- entry intelligence
def test_entry_mode_requires_data(memdb):
    r = entry.entry_analysis(memdb, "8517")
    assert r["available"] is False
    assert "Insufficient customs data" in r["message_en"]
    assert "connexion aux données douanières détaillées" in r["message_fr"]


def _synthetic_decls(db, n_sea=60, n_air=30, hs="851713"):
    db.add_all([EntryPoint(entry_point_id="SEA-X", official_name="Port X", entry_type="SEAPORT"),
                EntryPoint(entry_point_id="AIR-Y", official_name="Airport Y", entry_type="AIRPORT")])
    base = datetime(2026, 1, 1)
    for i in range(n_sea):
        db.add(CustomsImport(declaration_date=base + timedelta(days=i % 90), hs_code=hs, entry_point_id="SEA-X",
                             declared_value=1000, importer_hash=f"i{i%7}"))
    for i in range(n_air):
        db.add(CustomsImport(declaration_date=base + timedelta(days=i % 90), hs_code=hs, entry_point_id="AIR-Y",
                             declared_value=500, importer_hash=f"i{i%3}"))
    db.flush()


def test_entry_mode_shares(memdb):
    _synthetic_decls(memdb)
    r = entry.entry_analysis(memdb, "8517")
    assert r["available"] and r["main_entry_mode"] == "SEA"
    assert abs(r["modes"]["SEA"]["share_value"] - 60000 / 75000) < 1e-9
    assert r["top_entry_points"][0]["entry_point_id"] == "SEA-X"


# ---------------------------------------------------------------- fragmentation
def test_fragmentation_detects_burst_of_small_imports():
    end = datetime(2026, 6, 30)
    hist = pd.DataFrame({"date": [end - timedelta(days=100 + i * 5) for i in range(60)], "value": np.full(60, 5000.0),
                         "importer": ["h1"] * 60, "entry": ["SEA-X"] * 60, "desc": [None] * 60})
    burst = pd.DataFrame({"date": [end - timedelta(hours=i * 6) for i in range(40)], "value": np.full(40, 300.0),
                          "importer": [f"imp{i%9}" for i in range(40)], "entry": [["SEA-X", "AIR-Y", "LAND-Z"][i % 3] for i in range(40)],
                          "desc": [None] * 40})
    r = fragmentation.score_window(burst, hist, 30)
    assert r["status"] == "POSSIBLE FRAGMENTATION PATTERN"
    normal = hist.tail(6).assign(date=[end - timedelta(days=i * 5) for i in range(6)])
    assert fragmentation.score_window(normal, hist, 30)["status"] == "NORMAL"


def test_fragmentation_without_data_is_explicit(memdb):
    assert "SINDA CONNECTION REQUIRED" in fragmentation.detect_fragmentation(memdb)


# ---------------------------------------------------------------- forecast
def test_backtest_and_selection_on_seasonal_series():
    idx = pd.date_range("2019-01-01", periods=72, freq="MS")
    y = pd.Series(1000 * (1.004 ** np.arange(72)) * (1 + 0.1 * np.sin(2 * np.pi * idx.month / 12)), index=idx)
    m = forecast.backtest(y)
    valid = {k: v for k, v in m.items() if "MAPE" in v}
    assert len(valid) >= 4
    assert all(v["MAPE"] >= 0 for v in valid.values())
    paths = np.exp(forecast.MODELS["SARIMA(1,0,0)(0,1,1,12) + drift"](np.log(y), 24, 50))
    assert paths.shape == (50, 24)


# ---------------------------------------------------------------- risk
def test_growth_score_and_na():
    assert risk._growth_score(None) is None
    assert risk._growth_score(-0.5) == 0
    assert 40 < risk._growth_score(0.3) < 50


# ---------------------------------------------------------------- DBSCAN geo
def test_geo_clusters(memdb):
    from app.ml.clustering import geo_clusters
    from app.models import Cluster, Seller
    rng = np.random.default_rng(0)
    for i in range(30):
        memdb.add(Seller(external_id=f"t{i}", lat=36.8 + rng.normal(0, 0.001), lon=10.18 + rng.normal(0, 0.001), category="Electronics"))
    memdb.add(Seller(external_id="far", lat=33.0, lon=9.0))
    memdb.flush()
    geo_clusters(memdb, eps_km=1.0, min_samples=5)
    assert memdb.query(Cluster).count() == 1


# ---------------------------------------------------------------- customs extract import
def test_customs_import_hashes_importers(memdb):
    from app.providers.institutional import import_customs_extract
    csv = b"declaration_date,hs_code,declared_value,importer_id,transport_mode\n2026-01-02,8517.13,100,ACME-123,mer\n"
    import_customs_extract(memdb, csv, "x.csv", "b1")
    r = memdb.query(CustomsImport).one()
    assert r.importer_hash != "ACME-123" and len(r.importer_hash) == 64 and r.transport_mode == "SEA" and r.hs_code == "851713"
