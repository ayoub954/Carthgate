"""RBAC and Douane → Finance workflow on an isolated temporary database (never the application database)."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth import create_user
from app.db import Base, get_db
from app.main import app
from app.models import Case

PW = "MotDePasse-Test-2026"


@pytest.fixture()
def client():
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(eng)
    Maker = sessionmaker(bind=eng, expire_on_commit=False)
    s = Maker()
    create_user(s, "agent.test@douane.com", PW, "ROLE_DOUANE")
    create_user(s, "agent.test@finance.com", PW, "ROLE_FINANCE")
    create_user(s, "admin.test@diwana.tn", PW, "ROLE_ADMIN")
    s.add(Case(case_ref="DT-TEST-1", signature="test:1", kind="VALEUR", motif="Valeur unitaire basse — Produit test",
               product="Produit test", category="Électronique", priority_score=80, classification="PRIORITAIRE",
               explanation="Signal de test.", evidence={"sources": [{"name": "Test"}]}, value_concerned=1000.0,
               amount_unit="USD", status="A_ANALYSER"))
    s.commit()
    s.close()

    def _db():
        d = Maker()
        try:
            yield d
        finally:
            d.close()
    app.dependency_overrides[get_db] = _db
    yield TestClient(app)
    app.dependency_overrides.clear()


def _login(c, email):
    r = c.post("/api/auth/login", json={"email": email, "password": PW})
    assert r.status_code == 200
    return {"Authorization": "Bearer " + r.json()["token"]}


def test_domain_convention_checked_but_role_is_server_side():
    with pytest.raises(ValueError):
        create_user(None, "prenom.nom@finance.com", PW, "ROLE_DOUANE")


def test_login_and_unauthenticated(client):
    assert client.post("/api/auth/login", json={"email": "agent.test@douane.com", "password": "faux"}).status_code == 401
    assert client.get("/api/douane/cases").status_code == 401
    assert client.get("/api/finance/cases").status_code == 401


@pytest.mark.parametrize("who,path,code", [
    ("agent.test@douane.com", "/api/douane/cases", 200), ("agent.test@douane.com", "/api/finance/cases", 403),
    ("agent.test@douane.com", "/api/admin/users", 403), ("agent.test@finance.com", "/api/finance/cases", 200),
    ("agent.test@finance.com", "/api/douane/cases", 403), ("agent.test@finance.com", "/api/douane/map", 403),
    ("agent.test@finance.com", "/api/admin/users", 403), ("admin.test@diwana.tn", "/api/admin/users", 200),
    ("admin.test@diwana.tn", "/api/douane/cases", 403), ("admin.test@diwana.tn", "/api/finance/cases", 403)])
def test_rbac(client, who, path, code):
    assert client.get(path, headers=_login(client, who)).status_code == code


def test_transfer_workflow(client):
    D, F = _login(client, "agent.test@douane.com"), _login(client, "agent.test@finance.com")
    cid = client.get("/api/douane/cases", headers=D).json()["items"][0]["id"]
    assert client.get(f"/api/finance/cases/{cid}", headers=F).status_code == 404  # not transmitted yet
    assert client.post(f"/api/douane/cases/{cid}/transfer", headers=D, json={"motif": "x", "verified": True}).status_code == 400
    client.post(f"/api/douane/cases/{cid}/status", headers=D, json={"status": "EN_COURS"})
    assert client.post(f"/api/douane/cases/{cid}/transfer", headers=D, json={"motif": "x"}).status_code == 400  # human confirmation
    assert client.post(f"/api/douane/cases/{cid}/transfer", headers=D, json={"motif": "Écart", "verified": True}).status_code == 200
    assert client.post(f"/api/finance/cases/{cid}/transfer", headers=F, json={}).status_code in (403, 404, 405)
    assert client.get("/api/notifications", headers=F).json()["unread"] == 1
    assert client.get(f"/api/finance/cases/{cid}", headers=F).json()["status"] == "RECU"
    client.post(f"/api/finance/cases/{cid}/status", headers=F, json={"status": "EN_ANALYSE", "comment": "note interne"})
    assert client.get("/api/douane/transfers", headers=D).json()["items"][0]["finance_status"] == "En analyse"
    hist = client.get(f"/api/douane/cases/{cid}", headers=D).json()["history"]
    assert not any("note interne" in (h["detail"] or "") for h in hist)
