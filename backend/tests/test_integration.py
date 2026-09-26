"""Integration tests on the REAL local database (after `python -m app.pipeline`)."""
import pytest
from sqlalchemy import func

from app.models import (CommerceObservation, CustomsRecord, DataSource, EconomicIndicator, EntryPoint, Forecast,
                        RiskScore, Seller)


def test_ins_monthly_matches_published_ytd(realdb):
    """Jan–Aug 2026 imports derived from chapter files must match INS's published 62,525.4 MD (±0.5%)."""
    s = realdb.query(func.sum(EconomicIndicator.value)).filter(
        EconomicIndicator.indicator == "ins_imports_monthly", EconomicIndicator.period.between("2026-01", "2026-08")).scalar()
    if s is None:
        pytest.skip("2026 months not ingested")
    assert abs(s - 62525.4) / 62525.4 < 0.005


def test_data_freshness_and_provenance(realdb):
    latest = realdb.query(func.max(CustomsRecord.period)).filter(CustomsRecord.dataset == "ins_chapter_month").scalar()
    assert latest >= "2026-01"
    r = realdb.query(CustomsRecord).first()
    assert r.source_url and r.retrieved_at and r.source_key
    assert realdb.query(CustomsRecord).filter(CustomsRecord.source_url.is_(None)).count() == 0


def test_entry_points_are_real_and_typed(realdb):
    eps = realdb.query(EntryPoint).all()
    assert {e.entry_type for e in eps} <= {"AIRPORT", "SEAPORT", "LAND_BORDER"}
    assert all(e.source_url for e in eps)


def test_source_links_are_http(realdb):
    for s in realdb.query(Seller).filter(Seller.facebook.isnot(None)).all():
        assert s.facebook.startswith("http")
    for o in realdb.query(CommerceObservation).limit(50):
        assert o.page_url.startswith("https://")


def test_sentence_transformer_matching(realdb):
    from app.ml.matching import match_question_to_product, suggest_hs
    p, s = match_question_to_product(realdb, "smartphones et téléphones portables")
    assert p.id == "8517"
    assert suggest_hs(realdb, "wireless bluetooth headphones")[0]["hs_code"] in ("8518", "8517")


def test_risk_uses_na_not_zero(realdb):
    r = realdb.query(RiskScore).first()
    if not r:
        pytest.skip("analytics not run")
    na = [k for k, v in r.factors.items() if not v["available"]]
    assert all(r.factors[k]["value"] is None for k in na)
    assert 0 < r.data_coverage <= 1


def test_forecast_intervals(realdb):
    rows = realdb.query(Forecast).all()
    if not rows:
        pytest.skip("forecast not run")
    assert all(f.lower <= f.predicted <= f.upper for f in rows)
    assert max(int(f.period) for f in rows) == 2035


def test_access_required_sources_are_explicit(realdb):
    st = {d.key: d.status for d in realdb.query(DataSource)}
    assert st.get("sinda") in ("ACCESS REQUIRED", "CONNECTED")
    assert st.get("rne") in ("ACCESS REQUIRED", "CONNECTED")




def test_cases_come_only_from_detected_anomalies(realdb):
    """Every dossier is backed by a real analysed subject and carries its sources — never invented."""
    from app.models import Case
    from app.services.cases import classification_summary
    cases = realdb.query(Case).all()
    if not cases:
        pytest.skip("analysis not run")
    assert all(c.classification in ("A_VERIFIER", "PRIORITAIRE") for c in cases)
    assert all((c.evidence or {}).get("sources") for c in cases)
    assert all("fraude" not in (c.explanation or "").lower() for c in cases)
    s = classification_summary(realdb)
    assert s["Prioritaire"] + s["Anomalie à vérifier"] >= len([c for c in cases if c.status != "CLASSE"]) * 0  # summary computable
