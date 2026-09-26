"""DEMO dataset — SIMULATED data for the hackathon demonstration ONLY (demo_data = true).

Stored exclusively in the separate DEMO database (never mixed with REAL data).
All identities are fictitious ("Commerce Démo A", "Importateur DEMO-001"...); no real person,
company, URL or image is used. Reference data (HS nomenclature, countries, governorates, official
entry points, monitored headings) is copied from the REAL database because it is public reference,
not observations.

Scenarios
  A — NORMAL        computers (HS 8471): verified company, regular monthly sea imports
  B — À SURVEILLER  cosmetics (HS 3304): rising digital activity, several small air flows
  C — PRIORITAIRE   smartphones / earphones (HS 8517, 8518): strong digital activity, many small
                    imports by several fictitious importers over a short period, several entry
                    points, formalization not verified, large activity/declaration gap
  + watches (HS 9102): new land entry point (entry-mode change)
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timedelta

import numpy as np
from sqlalchemy.orm import Session

from ..db import session_for
from ..models import (Alert, Anomaly, Business, BusinessMatch, Cluster, CommerceObservation, Country, CustomsImport,
                      CustomsRecord, EntryPoint, FragmentationPattern, HSCode, Location, NetworkEdge, NetworkNode,
                      PriorityScore, Product, Recommendation, RiskScore, Seller, SellerReview)

DEMO_SOURCE = "demo_dataset"
DEMO_URL = None  # no URL is invented for simulated data


def _h(v: str) -> str:
    return hashlib.sha256(v.encode()).hexdigest()


def _copy_reference(db: Session) -> dict:
    real = session_for("REAL")
    counts = {}
    for model in (Country, HSCode, Location, EntryPoint, Product):
        rows = real.query(model).all()
        for r in rows:
            data = {c.name: getattr(r, c.name) for c in model.__table__.columns}
            db.merge(model(**data))
        counts[model.__tablename__] = len(rows)
    real.close()
    db.flush()
    return counts


def build_demo(db: Session) -> str:
    rng = np.random.default_rng(2026)
    today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    # wipe previous demo content (DEMO database only)
    for m in (SellerReview, Alert, Recommendation, PriorityScore, RiskScore, Anomaly, FragmentationPattern, NetworkEdge,
              NetworkNode, Cluster, BusinessMatch, CommerceObservation, CustomsImport, CustomsRecord, Seller, Business):
        db.query(m).delete()
    ref = _copy_reference(db)
    govs = {l.name: l for l in db.query(Location).filter(Location.level == "governorate")}
    eps = {e.entry_point_id: e for e in db.query(EntryPoint)}
    ep_sea = next((k for k in eps if k.startswith("SEA-RAD")), next(k for k in eps if k.startswith("SEA")))
    ep_sea2 = next((k for k in eps if k.startswith("SEA-SFAX")), ep_sea)
    ep_air = next((k for k in eps if k == "AIR-TUN"), next(k for k in eps if k.startswith("AIR")))
    ep_air2 = next((k for k in eps if k == "AIR-MIR"), ep_air)
    lands = [k for k in eps if k.startswith("LAND")]
    ep_land = next((k for k in lands if "11-5" in k or "Ras" in (eps[k].official_name or "") or "راس" in (eps[k].official_name or "")), lands[0])
    ep_land2 = lands[1] if len(lands) > 1 else ep_land

    now = datetime.utcnow()

    def gov_point(name):
        g = govs.get(name)
        return (g.centroid_lat + rng.normal(0, 0.02), g.centroid_lon + rng.normal(0, 0.02)) if g else (None, None)

    # ---------------- fictitious companies (simulated registry)
    companies = [
        ("Commerce Démo A", "Commerce de matériel informatique", "Tunis", "DEMO-001", "ACTIVE"),
        ("Société Démo Cosmétiques", "Commerce de produits cosmétiques", "Sfax", "DEMO-002", "ACTIVE"),
        ("Boutique Démo B", "Commerce de produits cosmétiques", "Sousse", None, "ACTIVE"),
        ("Distribution Démo Mode", "Commerce de vêtements", "Nabeul", "DEMO-012", "ACTIVE"),
        ("Horlogerie Démo", "Commerce de montres et bijoux", "Médenine", "DEMO-013", "ACTIVE"),
        ("Électro Démo Services", "Commerce de vêtements", "Ariana", "DEMO-014", "ACTIVE"),  # declared ≠ observed activity
    ]
    for name, act, gov, imp, st in companies:
        db.add(Business(registry_id=f"RNE-DEMO-{len(name):03d}{ord(name[-1])}", name=name, declared_activity=act,
                        governorate=gov, status=st, importer_hash=_h(imp) if imp else None,
                        source_key=DEMO_SOURCE, source_url=DEMO_URL, retrieved_at=now))

    # ---------------- fictitious sellers (simulated digital commerce)
    sellers_spec = [
        # name, platform, governorate, category, scenario, posts, product mix
        ("Commerce Démo A", "Site marchand", "Tunis", "Électronique", "A", 18, [("Ordinateur portable 15 pouces", 8471, 1450, 2600)]),
        ("Boutique Démo B", "Instagram", "Sousse", "Cosmétiques", "B", 55, [("Crème hydratante visage", 3304, 25, 70), ("Sérum éclat", 3304, 35, 90)]),
        ("Société Démo Cosmétiques", "Facebook", "Sfax", "Cosmétiques", "B", 30, [("Palette de maquillage", 3304, 40, 95)]),
        ("Vendeur Démo C", "Facebook", "Tunis", "Électronique", "C", 140, [("Smartphone 128 Go", 8517, 690, 1250), ("Écouteurs sans fil", 8518, 45, 120)]),
        ("Vendeur Démo D", "TikTok", "Ariana", "Électronique", "C", 95, [("Écouteurs sans fil", 8518, 40, 110), ("Smartphone 256 Go", 8517, 890, 1600)]),
        ("Vendeur Démo E", "Instagram", "Ben Arous", "Électronique", "C", 70, [("Smartphone 128 Go", 8517, 650, 1200)]),
        ("Électro Démo Services", "Facebook", "Ariana", "Électronique", "C", 60, [("Chargeur rapide", 8504, 25, 60), ("Smartphone 128 Go", 8517, 700, 1300)]),
        ("Horlogerie Démo", "Site marchand", "Médenine", "Bijoux et montres", "W", 35, [("Montre connectée", 9102, 120, 390)]),
        ("Distribution Démo Mode", "Facebook", "Nabeul", "Textile et habillement", "A", 25, [("Pull en maille", 6110, 45, 110)]),
        ("Vendeur Démo F", "TikTok", "Sfax", "Cosmétiques", "B", 40, [("Crème solaire", 3304, 30, 75)]),
        ("Vendeur Démo G", "Instagram", "Monastir", "Chaussures", "N", 12, [("Baskets de sport", 6404, 90, 220)]),
    ]
    n_obs = 0
    for name, platform, gov, cat, scen, posts, mix in sellers_spec:
        lat, lon = gov_point(gov)
        s = Seller(external_id=f"demo:{name}", name=name, shop_type=None, category=cat, lat=lat, lon=lon, governorate=gov,
                   city=gov, platform=platform, tags={"demo_data": True, "scenario": scen},
                   source_key=DEMO_SOURCE, source_url=DEMO_URL, retrieved_at=now)
        db.add(s)
        db.flush()
        for i in range(posts):
            # scenario B/C: activity concentrated in the last 30–45 days; others spread over 180 days
            age = int(rng.integers(0, 40)) if scen in ("B", "C") and rng.random() < 0.75 else int(rng.integers(0, 180))
            prod, hs, lo, hi = mix[i % len(mix)]
            db.add(CommerceObservation(
                external_id=f"demo:{s.id}:{i}", platform=platform, page_name=name, page_url=None, post_url=None,
                product=prod, brand=None, category=cat, raw_categories=cat, image_url=None,
                price=float(round(rng.uniform(lo, hi))), currency="TND", observed_at=today - timedelta(days=age, hours=int(rng.integers(0, 23))),
                public_business_location=gov, product_id=str(hs), match_score=None,
                source_key=DEMO_SOURCE, source_url=DEMO_URL, retrieved_at=now))
            n_obs += 1

    # ---------------- simulated declaration-level customs imports
    decl = []

    def add(days_ago, hs, imp, ep, value, qty, origin, desc, gov):
        e = eps[ep]
        mode = {"SEAPORT": "SEA", "AIRPORT": "AIR", "LAND_BORDER": "LAND"}[e.entry_type]
        decl.append(CustomsImport(
            declaration_ref_hash=_h(f"DEMO-DEC-{len(decl):05d}"), declaration_date=today - timedelta(days=days_ago, hours=int(rng.integers(0, 20))),
            hs_code=hs, description=desc, importer_hash=_h(imp), origin_iso3=origin, provenance_iso3=origin, entry_point_id=ep,
            transport_mode=mode, quantity=float(qty), declared_value=float(round(value, 2)), currency="TND",
            destination_governorate=gov, import_batch="DEMO", source_key=DEMO_SOURCE, source_url=DEMO_URL, retrieved_at=now))

    # A — computers, regular monthly sea imports by DEMO-001 (verified company)
    for d in range(5, 181, 15):
        add(d, "847130", "DEMO-001", ep_sea, rng.normal(180000, 15000), int(rng.normal(120, 10)), "CHN", "Ordinateurs portables", "Tunis")
    # A — clothing, regular
    for d in range(3, 181, 20):
        add(d, "611030", "DEMO-012", ep_sea2, rng.normal(60000, 6000), int(rng.normal(900, 60)), "TUR", "Pulls en maille", "Nabeul")
    # B — cosmetics: historical low rate, recent rise of small air flows by 4 importers
    for d in range(40, 181, 14):
        add(d, "330499", "DEMO-002", ep_air, rng.normal(25000, 3000), int(rng.normal(900, 80)), "FRA", "Crèmes de soin", "Sfax")
    for k in range(22):
        imp = f"DEMO-00{2 + k % 4}" if k % 4 else "DEMO-002"
        add(int(rng.integers(0, 30)), "330499", imp, ep_air if k % 3 else ep_air2, rng.normal(2600, 500), int(rng.normal(90, 15)),
            ["FRA", "TUR", "KOR"][k % 3], "Crèmes et sérums de soin", ["Sousse", "Sfax"][k % 2])
    # C — smartphones & earphones: small historical flow, then many small declarations over 14 days
    for d in range(30, 181, 21):
        add(d, "851713", "DEMO-001", ep_sea, rng.normal(95000, 8000), int(rng.normal(60, 5)), "CHN", "Téléphones portables", "Tunis")
    for k in range(64):
        imp = f"DEMO-{3 + k % 9:03d}"
        hs = "851713" if k % 3 else "851830"
        ep = [ep_air, ep_sea, ep_land, ep_air2][k % 4]
        val = rng.normal(2400, 450) if hs == "851713" else rng.normal(900, 200)
        qty = int(rng.normal(4, 1)) if hs == "851713" else int(rng.normal(30, 6))
        add(int(rng.integers(0, 14)), hs, imp, ep, val, max(qty, 1), ["CHN", "ARE", "TUR"][k % 3],
            "Téléphones portables" if hs == "851713" else "Écouteurs sans fil", ["Tunis", "Ariana", "Ben Arous"][k % 3])
    # W — watches: sea historically, recent switch to a land border (new entry point)
    for d in range(35, 181, 18):
        add(d, "910211", "DEMO-013", ep_sea2, rng.normal(40000, 4000), int(rng.normal(300, 30)), "CHN", "Montres", "Médenine")
    for k in range(9):
        add(int(rng.integers(0, 20)), "910211", "DEMO-013", ep_land2, rng.normal(9000, 1500), int(rng.normal(60, 10)), "LBY", "Montres connectées", "Médenine")
    db.add_all(decl)
    db.flush()
    return (f"DEMO dataset rebuilt: {len(sellers_spec)} fictitious sellers, {len(companies)} fictitious companies, "
            f"{n_obs} simulated observations, {len(decl)} simulated declarations; reference copied {ref}")
