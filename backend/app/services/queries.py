"""Read-side queries shared by the API and the agents. French business wording; every payload carries its sources.

`db` is the session of the (real-data) store. Official context (economy, countries, source
catalogue) always comes from the REAL store and is labelled as such.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timedelta

import numpy as np
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..db import session_for
from ..ml.entry import entry_analysis
from ..models import (Alert, Anomaly, Business, BusinessMatch, Cluster, CommerceObservation, Country, CustomsImport,
                      CustomsRecord, DataSource, EconomicIndicator, EntryPoint, Forecast, FragmentationPattern,
                      Location, Product, Recommendation, RiskScore, Seller)
from . import advisor

NA = "Données insuffisantes pour cette analyse"
MODE_FR = {"SEA": "Voie maritime", "AIR": "Voie aérienne", "LAND": "Voie terrestre"}
ENTRY_TYPE_FR = {"AIRPORT": "Aéroport", "SEAPORT": "Port", "LAND_BORDER": "Frontière terrestre"}
SOURCE_FR = {
    "ins_trade": "INS — Commerce extérieur", "un_comtrade": "Nations unies — statistiques du commerce",
    "world_bank_wdi": "Banque mondiale — indicateurs", "osm_shops": "Localisations commerciales publiques",
    "open_facts": "Registres ouverts de produits", "openbeautyfacts": "Registre ouvert de produits cosmétiques",
    "openproductsfacts": "Registre ouvert de produits", "openfoodfacts": "Registre ouvert de produits alimentaires",
    "entry_points_ref": "Référentiel des points d'entrée", "authorized_customs_extract": "Extrait douanier autorisé",
    "customs_declarations": "Déclarations douanières",
}
# Business description of each source (never technical)
SOURCE_INFO = {
    "ins_trade": ("INS — Commerce extérieur", "Statistiques officielles mensuelles des importations et exportations"),
    "un_comtrade": ("Nations unies — statistiques du commerce", "Importations tunisiennes par produit et par pays"),
    "world_bank_wdi": ("Banque mondiale", "Séries économiques de long terme"),
    "osm_shops": ("Localisations commerciales publiques", "Commerces publiquement référencés en Tunisie"),
    "open_facts": ("Registres ouverts de produits", "Produits observés sur le marché tunisien, avec images"),
    "entry_points_ref": ("Référentiel des points d'entrée", "Ports de commerce, aéroports et postes frontaliers"),
    "hs_nomenclature": ("Nomenclature du Système harmonisé", "Classement des produits"),
    "un_m49": ("Référentiel des pays et continents", "Nomenclature officielle des pays"),
    "geoboundaries_tun_adm1": ("Découpage administratif", "Limites des 24 gouvernorats"),
    "douane_tn": ("Douane tunisienne — portail officiel", "Informations publiques de la Douane"),
    "sinda": ("Déclarations douanières détaillées", "Points d'entrée, modes de transport, importateurs, petits envois"),
    "rne": ("Registre national des entreprises", "Vérification de la formalisation des entreprises"),
    "tariff_tn": ("Tarif douanier", "Droits et taxes applicables"),
    "social_commerce": ("Réseaux sociaux (Facebook, Instagram, TikTok)", "Publications commerciales publiques"),
    "authorized_sites": ("Sites marchands autorisés", "Catalogues de sites marchands"),
    "commerce_public": None,
}


def status_fr(status: str | None, access_type: str | None = None) -> str:
    if status == "CONNECTED":
        return "Connectée"
    if status == "ACCESS REQUIRED":
        return "Source institutionnelle non connectée" if access_type in ("INSTITUTIONAL_ACCESS", "OFFICIAL_ACCESS") else \
            "Autorisation complémentaire nécessaire"
    if status == "NOT AVAILABLE":
        return "Non configurée"
    return "Source actuellement indisponible"


def src(db: Session, key: str) -> dict:
    real = session_for("REAL")
    try:
        d = real.query(DataSource).filter_by(key=key).first()
    finally:
        real.close()
    name = (SOURCE_INFO.get(key) or (SOURCE_FR.get(key, key),))[0]
    if not d:
        return {"source_key": key, "source_name": name}
    return {"source_key": key, "source_name": name, "source_url": d.url, "status": status_fr(d.status, d.access_type),
            "period": d.period, "last_updated": d.last_updated.isoformat() if d.last_updated else None}


def data_mode(db: Session) -> str:
    return db.info.get("data_mode", "REAL")


def latest_comtrade_year(db):
    return db.query(func.max(CustomsRecord.period)).filter(CustomsRecord.dataset == "comtrade_hs4_partner").scalar()


# ============================================================ VUE D'ENSEMBLE
def dashboard(db: Session) -> dict:
    monitored = db.query(Product).filter(Product.monitored.is_(True)).count()
    alerts = db.query(Alert).filter(Alert.status == "TO_REVIEW").count()
    risks = db.query(RiskScore).all()
    coverage = float(np.mean([r.data_coverage for r in risks])) if risks else 0.0
    gap = advisor.value_gap(db)
    real = session_for("REAL")
    try:
        imports = real.query(EconomicIndicator).filter(EconomicIndicator.indicator == "ins_imports_monthly").order_by(EconomicIndicator.period).all()
        exports = {e.period: e.value for e in real.query(EconomicIndicator).filter(EconomicIndicator.indicator == "ins_exports_monthly")}
        graph = [{"period": e.period, "imports": e.value, "exports": exports.get(e.period)} for e in imports][-36:]
    finally:
        real.close()
    recs = [advisor.recommendation_dict(r) for r in db.query(Recommendation).order_by(Recommendation.rank).limit(3)]
    return {
        "data_mode": data_mode(db),
        "kpis": {"products": monitored, "alerts": alerts, "coverage": coverage, "revenue_to_verify": gap},
        "brief": recs,
        "graph": {"title": "Commerce extérieur de la Tunisie (millions de dinars)", "series": graph, "source": src(db, "ins_trade")},
        "map": map_data(db, light=True),
    }


# ============================================================ PRODUITS / COMMERCE NUMÉRIQUE
def _window_start(window: str) -> datetime | None:
    now = datetime.utcnow()
    return {"7d": now - timedelta(days=7), "30d": now - timedelta(days=30), "90d": now - timedelta(days=90),
            "2026": datetime(2026, 1, 1)}.get(window)


def top_observed_products(db: Session, window: str = "all", limit: int = 10) -> dict:
    start = _window_start(window)
    q = db.query(CommerceObservation).filter(CommerceObservation.product_id.isnot(None))
    if start:
        q = q.filter(CommerceObservation.observed_at >= start)
    obs = q.all()
    prods = {p.id: p for p in db.query(Product)}
    if not obs:
        return {"window": window, "items": [], "most_observed": None, "message": "Aucune observation sur cette période."}
    by = defaultdict(list)
    for o in obs:
        by[o.product_id].append(o)
    now = datetime.utcnow()
    items = []
    for pid, lst in by.items():
        p = prods.get(pid)
        recent = sum(1 for o in lst if o.observed_at and o.observed_at >= now - timedelta(days=90))
        older = sum(1 for o in lst if o.observed_at and now - timedelta(days=180) <= o.observed_at < now - timedelta(days=90))
        img = next((o for o in sorted(lst, key=lambda o: o.observed_at or datetime.min, reverse=True) if o.image_url), None)
        brands = Counter(o.brand for o in lst if o.brand)
        locs = Counter(o.public_business_location for o in lst if o.public_business_location)
        origin = Counter(o.manufacturing_place for o in lst if o.manufacturing_place)
        prices = [o.price for o in lst if o.price]
        items.append({
            "product_id": pid, "product": p.short_name if p else pid, "category": p.category if p else None,
            "observations": len(lst), "unique_sellers": len({o.page_name for o in lst}), "brands": len(brands),
            "top_brand": brands.most_common(1)[0][0] if brands else None, "platforms": sorted({o.platform for o in lst}),
            "image_url": img.image_url if img else None, "image_source": img.page_url if img else None,
            "trend_recent": recent, "trend_previous": older, "growth": (recent / older - 1) if older else None,
            "price_min": min(prices) if prices else None, "price_max": max(prices) if prices else None,
            "currency": next((o.currency for o in lst if o.currency), None),
            "zone": locs.most_common(1)[0][0] if locs else None,
            "origin": origin.most_common(1)[0][0] if origin else None,
            "links": sorted({o.post_url or o.page_url for o in lst if (o.post_url or o.page_url)})[:5],
        })
    items.sort(key=lambda i: (i["observations"], len(i["platforms"]), i["brands"]), reverse=True)
    return {"window": window, "items": items[:limit], "most_observed": items[0] if items else None}


def digital_commerce(db: Session, window: str = "all") -> dict:
    """Page 'Commerce numérique': observed products, brands, sellers, platforms, prices, zones, trends, links."""
    top = top_observed_products(db, window, limit=12)
    start = _window_start(window)
    q = db.query(CommerceObservation).filter(CommerceObservation.product_id.isnot(None))
    if start:
        q = q.filter(CommerceObservation.observed_at >= start)
    obs = q.all()
    platforms = Counter(o.platform for o in obs)
    brands = Counter(o.brand for o in obs if o.brand)
    prod_cat = {p.id: p.category for p in db.query(Product)}
    cats = Counter(prod_cat.get(o.product_id) for o in obs if prod_cat.get(o.product_id))
    sellers = Counter(o.page_name for o in obs if o.page_name)
    zones = Counter(o.public_business_location for o in obs if o.public_business_location)
    months = Counter(o.observed_at.strftime("%Y-%m") for o in obs if o.observed_at)
    real = session_for("REAL")
    try:
        soc = real.query(DataSource).filter_by(key="social_commerce").first()
        social_connected = bool(soc and soc.status == "CONNECTED")
    finally:
        real.close()
    feed = sorted(obs, key=lambda o: o.observed_at or datetime.min, reverse=True)[:24]
    return {
        "data_mode": data_mode(db), "window": window, "total": len(obs), "top": top,
        "platforms": dict(platforms.most_common()), "brands": dict(brands.most_common(10)),
        "categories": dict(cats.most_common(10)), "sellers": dict(sellers.most_common(10)),
        "zones": dict(zones.most_common(8)), "trend": [{"period": k, "observations": v} for k, v in sorted(months.items())][-18:],
        "social_note": None if social_connected else "Certaines plateformes nécessitent une autorisation complémentaire.",
        "feed": [{"product": o.product, "brand": o.brand, "platform": o.platform,
                  "seller": o.page_name if o.page_name != o.platform else None, "price": o.price,
                  "currency": o.currency, "image_url": o.image_url, "link": o.post_url or o.page_url, "zone": o.public_business_location,
                  "date": o.observed_at.date().isoformat() if o.observed_at else None, "product_id": o.product_id} for o in feed],
    }


def products_list(db: Session) -> list[dict]:
    risks = {r.product_id: r for r in db.query(RiskScore)}
    year = latest_comtrade_year(db)
    vals = dict(db.query(CustomsRecord.hs_code, func.sum(CustomsRecord.value)).filter(
        CustomsRecord.dataset == "comtrade_hs4_partner", CustomsRecord.period == year).group_by(CustomsRecord.hs_code))
    obs = dict(db.query(CommerceObservation.product_id, func.count()).group_by(CommerceObservation.product_id))
    out = []
    for p in db.query(Product).filter(Product.monitored.is_(True)).order_by(Product.category, Product.id):
        r = risks.get(p.id)
        out.append({"id": p.id, "name": p.short_name, "category": p.category, "import_value_usd": vals.get(p.id), "import_year": year,
                    "observations": obs.get(p.id, 0), "score": r.score if r else None, "level": _level(r.score if r else None),
                    "data_coverage": r.data_coverage if r else None})
    return out


def _level(score):
    if score is None:
        return None
    return "Prioritaire" if score >= 75 else "Élevé" if score >= 60 else "Modéré" if score >= 40 else "Faible"


CONF_FR = {"HIGH": "Élevé", "MEDIUM": "Moyen", "LOW": "Faible"}


def product_360(db: Session, pid: str, section: str | None = None) -> dict:
    p = db.get(Product, pid)
    if not p:
        return {"error": "not found"}
    sections = {}
    want = lambda s: section in (None, s)
    year = latest_comtrade_year(db)
    if want("overview"):
        r = db.query(RiskScore).filter_by(product_id=pid).first()
        img = db.query(CommerceObservation.image_url).filter(CommerceObservation.product_id == pid, CommerceObservation.image_url.isnot(None)).first()
        sections["overview"] = {"id": p.id, "name": p.short_name, "category": p.category, "chapter": p.chapter,
                                "score": r.score if r else None, "level": _level(r.score if r else None),
                                "data_coverage": r.data_coverage if r else None, "confidence": CONF_FR.get(r.confidence) if r else None,
                                "image_url": img[0] if img else None}
    if want("online"):
        obs = db.query(CommerceObservation).filter_by(product_id=pid).order_by(CommerceObservation.observed_at.desc()).all()
        groups = defaultdict(list)
        for o in obs:
            groups[o.group_key or o.external_id].append(o)
        items = sorted(groups.values(), key=len, reverse=True)[:12]
        prices = [o.price for o in obs if o.price]
        sections["online"] = {
            "observations": len(obs), "platforms": dict(Counter(o.platform for o in obs)),
            "sellers": dict(Counter(o.page_name for o in obs if o.page_name).most_common(8)),
            "brands": dict(Counter(o.brand for o in obs if o.brand).most_common(10)),
            "price_min": min(prices) if prices else None, "price_max": max(prices) if prices else None,
            "items": [{"product": g[0].product, "brand": g[0].brand, "observations": len(g), "image_url": next((o.image_url for o in g if o.image_url), None),
                       "platform": g[0].platform, "seller": g[0].page_name, "link": g[0].post_url or g[0].page_url,
                       "date": g[0].observed_at.date().isoformat() if g[0].observed_at else None, "price": g[0].price,
                       "origin": g[0].manufacturing_place} for g in items],
        }
    if want("customs") or want("origin"):
        rows = db.query(CustomsRecord).filter(CustomsRecord.dataset == "comtrade_hs4_partner", CustomsRecord.hs_code == pid).all()
        by_year = defaultdict(float)
        for r in rows:
            by_year[r.period] += r.value or 0
        latest = [r for r in rows if r.period == year]
        tot = sum(r.value or 0 for r in latest)
        countries = {c.iso3: c for c in db.query(Country)}
        cname = lambda iso, fallback: (countries[iso].name_fr or countries[iso].name_en) if iso in countries else fallback
        cont = defaultdict(float)
        for r in latest:
            cont[CONTINENT_FR.get(countries[r.partner_iso3].continent) if r.partner_iso3 in countries else "Autre"] += r.value or 0
        clist = [{"iso3": r.partner_iso3, "country": cname(r.partner_iso3, r.partner_name),
                  "continent": CONTINENT_FR.get(countries[r.partner_iso3].continent) if r.partner_iso3 in countries else None,
                  "value": r.value, "unit": "USD", "weight_kg": r.weight_kg, "share": (r.value or 0) / tot if tot else None}
                 for r in sorted(latest, key=lambda r: -(r.value or 0))[:15]]
        decl = db.query(CustomsImport).filter(CustomsImport.hs_code.like(f"{pid}%")).all()
        if not clist and decl:  # declaration-level provenance
            agg = defaultdict(float)
            for d in decl:
                agg[d.provenance_iso3 or d.origin_iso3] += d.declared_value or 0
            tot = sum(agg.values())
            for iso, v in sorted(agg.items(), key=lambda kv: -kv[1]):
                c = countries.get(iso)
                cont[CONTINENT_FR.get(c.continent) if c else "Autre"] += v
                clist.append({"iso3": iso, "country": cname(iso, iso), "continent": CONTINENT_FR.get(c.continent) if c else None,
                              "value": v, "unit": "TND", "share": v / tot if tot else None})
        monthly = defaultdict(float)
        for d in decl:
            monthly[d.declaration_date.strftime("%Y-%m")] += d.declared_value or 0
        ch = db.query(CustomsRecord).filter(CustomsRecord.dataset == "ins_chapter_month", CustomsRecord.flow == "M",
                                            CustomsRecord.hs_code == p.chapter).order_by(CustomsRecord.period).all()
        sections["customs"] = {
            "by_year": [{"period": k, "value": v} for k, v in sorted(by_year.items())], "year": year, "chapter": p.chapter,
            "chapter_monthly": [{"period": r.period, "value": r.value} for r in ch][-36:],
            "declarations_monthly": [{"period": k, "value": v} for k, v in sorted(monthly.items())],
            "declarations": len(decl), "sources": [src(db, "un_comtrade"), src(db, "ins_trade")],
        }
        sections["origin"] = {"year": year, "countries": clist,
                              "continents": sorted([{"continent": k, "share": v / sum(cont.values())} for k, v in cont.items()], key=lambda x: -x["share"]) if cont else [],
                              "top_continent": max(cont, key=cont.get) if cont else None,
                              "note": "Pays de provenance selon les statistiques douanières (différent de l'origine de la marque)."}
    if want("entry"):
        sections["entry"] = entry_view(db, pid)
    if want("geography") or want("sellers"):
        sellers = db.query(Seller).filter(Seller.category == p.category).all()
        govs = Counter(s.governorate for s in sellers if s.governorate)
        sections["geography"] = {"governorates": [{"governorate": g, "count": n} for g, n in govs.most_common(10)],
                                 "note": "Zones où sont observés des commerces de cette catégorie (association statistique)."}
        sections["sellers"] = {"items": [seller_brief(s) for s in sorted(sellers, key=lambda s: (not (s.facebook or s.website), s.name or "~"))[:25]],
                               "total": len(sellers)}
    if want("anomalies"):
        an = db.query(Anomaly).filter(((Anomaly.subject_type == "HS_CHAPTER_MONTH") & (Anomaly.hs_code == p.chapter)) |
                                      ((Anomaly.subject_type != "HS_CHAPTER_MONTH") & (Anomaly.hs_code == pid))).all()
        fr = db.query(FragmentationPattern).filter_by(hs_code=pid).all()
        sections["anomalies"] = {"items": [anomaly_dict(a) for a in sorted(an, key=lambda a: (a.period or ""), reverse=True) if a.is_anomaly][:12],
                                 "series": [{"period": a.period, "score": a.score} for a in sorted([a for a in an if a.subject_type == "HS_CHAPTER_MONTH"], key=lambda a: a.period)],
                                 "fragmentation": [{"window_days": f.window_days, "state": FRAG_FR.get(f.status, f.status),
                                                    "reasons": (f.features or {}).get("reasons", [])} for f in fr]}
    if want("risk"):
        sections["risk"] = risk_dict(db, pid)
    if want("network"):
        from ..ml.network import product_constellation
        sections["network"] = product_constellation(db, pid)
    if want("sources"):
        sections["sources"] = [src(db, k) for k in ("un_comtrade", "ins_trade", "open_facts", "osm_shops", "entry_points_ref")]
    return {"product_id": pid, "data_mode": data_mode(db), "sections": sections}


CONTINENT_FR = {"Africa": "Afrique", "Europe": "Europe", "Asia": "Asie", "North America": "Amérique du Nord",
                "South America": "Amérique du Sud", "Oceania": "Océanie"}
FRAG_FR = {"NORMAL": "Comportement habituel", "MONITOR": "À surveiller", "POSSIBLE FRAGMENTATION PATTERN": "Fragmentation possible"}


def entry_view(db: Session, pid: str | None) -> dict:
    ea = entry_analysis(db, pid)
    if not ea.get("available"):
        return {"available": False, "message": "Les données actuellement connectées ne permettent pas de déterminer de manière fiable "
                                               "si ce produit entre principalement par voie maritime, aérienne ou terrestre. "
                                               "Une connexion aux données douanières détaillées est nécessaire.",
                "records": ea.get("records_analyzed", 0)}
    return {"available": True, "main_mode": MODE_FR.get(ea["main_entry_mode"]),
            "modes": [{"mode": MODE_FR.get(m, m), "key": m, "share": v["share_value"], "records": v["records"], "value": v["value"]}
                      for m, v in sorted(ea["modes"].items(), key=lambda kv: -kv[1]["share_value"])],
            "entry_points": [{**t, "type": ENTRY_TYPE_FR.get({"SEA": "SEAPORT", "AIR": "AIRPORT", "LAND": "LAND_BORDER"}.get(t["type"]), t["type"])}
                             for t in ea["top_entry_points"]],
            "evolution": ea.get("evolution"), "records": ea["records_analyzed"], "period": ea["period"],
            "coverage": ea["data_coverage"], "confidence": CONF_FR.get(ea["confidence"])}


def risk_dict(db: Session, pid: str) -> dict:
    r = db.query(RiskScore).filter_by(product_id=pid).first()
    if not r:
        return {"product_id": pid, "score": None, "message": NA}
    return {"product_id": pid, "score": r.score, "level": _level(r.score),
            "factors": [{"label": v["label"], "value": v.get("value"), "available": v["available"], "detail": v["detail"]}
                        for v in (r.factors or {}).values()],
            "why": r.explanation, "data_coverage": r.data_coverage, "confidence": CONF_FR.get(r.confidence), "period": r.period}


ANOMALY_KIND_FR = {"HS_CHAPTER_MONTH": "Importations mensuelles", "PARTNER_HS_UNIT_VALUE": "Valeurs déclarées par pays",
                   "ENTRY": "Points d'entrée", "DECLARED_VALUE": "Valeurs déclarées", "MODE_SHIFT": "Mode d'entrée"}


def anomaly_state(a: Anomaly) -> str:
    if a.is_anomaly:
        return "Comportement inhabituel"
    return "À surveiller" if a.score >= 85 else "Comportement habituel"


def anomaly_dict(a: Anomaly) -> dict:
    return {"id": a.id, "kind": ANOMALY_KIND_FR.get(a.subject_type, a.subject_type), "hs_code": a.hs_code, "period": a.period,
            "state": anomaly_state(a), "why": a.reasons, "label": (a.features or {}).get("description") or (a.features or {}).get("partner"),
            "coverage": a.data_coverage, "confidence": CONF_FR.get(a.confidence, a.confidence),
            "source": SOURCE_FR.get(a.source_key, "Statistiques officielles")}


# ============================================================ VENDEURS / ENTREPRISES
def seller_brief(s: Seller) -> dict:
    return {"id": s.id, "name": s.name, "category": s.category, "governorate": s.governorate, "platform": s.platform,
            "lat": s.lat, "lon": s.lon, "has_links": bool(s.facebook or s.instagram or s.website or s.tiktok)}


def sellers(db: Session, q: str | None = None, category: str | None = None, governorate: str | None = None,
            with_links: bool = False, limit: int = 200) -> dict:
    qs = db.query(Seller)
    if q:
        qs = qs.filter(Seller.name.ilike(f"%{q}%"))
    if category:
        qs = qs.filter(Seller.category == category)
    if governorate:
        qs = qs.filter(Seller.governorate == governorate)
    if with_links:
        qs = qs.filter((Seller.facebook.isnot(None)) | (Seller.website.isnot(None)) | (Seller.instagram.isnot(None)))
    return {"total": qs.count(), "items": [seller_brief(s) for s in qs.order_by(Seller.name.is_(None), Seller.name).limit(limit)],
            "data_mode": data_mode(db)}


def seller_360(db: Session, sid: int) -> dict:
    from ..ml.verification import FORMALIZATION_FR
    from ..models import SellerReview
    s = db.get(Seller, sid)
    if not s:
        return {"error": "not found"}
    bm = db.query(BusinessMatch).filter_by(seller_id=sid).first()
    rv = db.query(SellerReview).filter_by(seller_id=sid).order_by(SellerReview.id.desc()).first()
    obs = db.query(CommerceObservation).filter_by(page_name=s.name).all() if s.name else []
    prices = [o.price for o in obs if o.price]
    prods = Counter(o.product for o in obs if o.product)
    return {
        "id": s.id, "name": s.name or "(nom non publié)", "category": s.category, "platform": s.platform,
        "links": {"facebook": s.facebook, "instagram": s.instagram, "tiktok": s.tiktok, "website": s.website},
        "location": {"lat": s.lat, "lon": s.lon, "governorate": s.governorate, "city": s.city},
        "products": [p for p, _ in prods.most_common(8)], "main_product": prods.most_common(1)[0][0] if prods else None,
        "observations": len(obs), "price_min": min(prices) if prices else None, "price_max": max(prices) if prices else None,
        "formalization": FORMALIZATION_FR.get(bm.status, "Information indisponible") if bm else "Information indisponible",
        "review": {"score": rv.score, "level": rv.level, "reasons": rv.reasons, "customs_activity": rv.customs_activity,
                   "consistency": rv.consistency} if rv else None,
        "sources": [{"name": SOURCE_FR.get(s.source_key, "Source publique"), "url": s.source_url,
                     "retrieved_at": s.retrieved_at.date().isoformat() if s.retrieved_at else None}],
        "data_mode": data_mode(db),
    }


def businesses(db: Session, limit: int = 50) -> dict:
    n_bus = db.query(Business).count()
    counts = dict(db.query(BusinessMatch.status, func.count()).group_by(BusinessMatch.status))
    from ..ml.verification import FORMALIZATION_FR
    fr = Counter()
    for k, v in counts.items():
        fr[FORMALIZATION_FR.get(k, "Information indisponible")] += v
    return {"businesses_loaded": n_bus, "verification_counts": dict(fr),
            "message": None if n_bus else "Registre des entreprises : source institutionnelle non connectée. La formalisation n'est pas vérifiable."}


# ============================================================ PAYS (données réelles)
def countries(db: Session) -> dict:
    cmap = {c.iso3: c for c in db.query(Country)}
    latest = db.query(func.max(CustomsRecord.period)).filter(CustomsRecord.dataset == "ins_country_month").scalar()
    rows = []
    if latest:
        y, m = latest.split("-")
        agg = lambda a, b: dict(db.query(CustomsRecord.partner_iso3, func.sum(CustomsRecord.value)).filter(
            CustomsRecord.dataset == "ins_country_month", CustomsRecord.flow == "M", CustomsRecord.partner_iso3.isnot(None),
            CustomsRecord.period >= a, CustomsRecord.period <= b).group_by(CustomsRecord.partner_iso3))
        cur, prev = agg(f"{y}-01", latest), agg(f"{int(y)-1}-01", f"{int(y)-1}-{m}")
        tot = sum(v for v in cur.values() if v)
        for iso, v in sorted(cur.items(), key=lambda kv: -(kv[1] or 0)):
            c = cmap.get(iso)
            if not c or not v:
                continue
            rows.append({"iso3": iso, "country": c.name_fr or c.name_en, "continent": CONTINENT_FR.get(c.continent, c.continent),
                         "lat": c.lat, "lon": c.lon, "imports_mtnd": v, "share": v / tot, "trend": (v / prev[iso] - 1) if prev.get(iso) else None})
    cont = defaultdict(float)
    for r in rows:
        cont[r["continent"] or "Autre"] += r["imports_mtnd"]
    tot = sum(cont.values())
    year = latest_comtrade_year(db)
    prods = {p.id: p for p in db.query(Product)}
    cats = defaultdict(Counter)
    for r in db.query(CustomsRecord).filter(CustomsRecord.dataset == "comtrade_hs4_partner", CustomsRecord.period == year):
        if r.partner_iso3 and r.hs_code in prods:
            cats[r.partner_iso3][prods[r.hs_code].category] += r.value or 0
    for r in rows:
        r["categories"] = [k for k, _ in cats.get(r["iso3"], Counter()).most_common(3)]
    months = {"01": "janvier", "02": "février", "03": "mars", "04": "avril", "05": "mai", "06": "juin", "07": "juillet",
              "08": "août", "09": "septembre", "10": "octobre", "11": "novembre", "12": "décembre"}
    return {"period": f"janvier → {months[latest[5:]]} {latest[:4]}" if latest else None, "countries": rows,
            "continents": sorted([{"continent": k, "imports_mtnd": v, "share": v / tot} for k, v in cont.items()], key=lambda x: -x["imports_mtnd"]),
            "top_continent": max(cont, key=cont.get) if cont else None, "sources": [src(db, "ins_trade"), src(db, "un_comtrade")]}


# ============================================================ CARTE
def map_data(db: Session, light: bool = False, product_id: str | None = None) -> dict:
    sellers_ = [{"id": s.id, "lat": s.lat, "lon": s.lon, "name": s.name, "category": s.category, "governorate": s.governorate}
                for s in db.query(Seller).filter(Seller.lat.isnot(None))]
    eps = [{"id": e.entry_point_id, "name": e.official_name, "type": e.entry_type, "type_fr": ENTRY_TYPE_FR.get(e.entry_type),
            "lat": e.latitude, "lon": e.longitude, "governorate": e.governorate, "source_url": e.source_url} for e in db.query(EntryPoint)]
    govs = {l.name: l for l in db.query(Location).filter(Location.level == "governorate")}
    attention = []
    for r in db.query(Recommendation).order_by(Recommendation.rank).limit(3):
        p = db.get(Product, r.product_id) if r.product_id else None
        if not p:
            continue
        cnt = Counter(s["governorate"] for s in sellers_ if s["category"] == p.category and s["governorate"])
        total = sum(cnt.values()) or 1
        for g, n in cnt.most_common(2):
            loc = govs.get(g)
            if loc:
                attention.append({"zone": g, "lat": loc.centroid_lat, "lon": loc.centroid_lon, "priority": r.priority_score,
                                  "intensity": r.priority_score / 100 * (n / total) ** 0.5, "product": p.short_name, "product_id": p.id,
                                  "reason": (r.why or [""])[0], "observations": n, "period": r.period})
        ea = (r.evidence or {}).get("entry") or {}
        for t in (ea.get("top_entry_points") or [])[:1]:
            e = next((x for x in eps if x["id"] == t["entry_point_id"]), None)
            if e and e["lat"] is not None:
                attention.append({"zone": e["name"], "lat": e["lat"], "lon": e["lon"], "priority": r.priority_score,
                                  "intensity": r.priority_score / 100, "product": p.short_name, "product_id": p.id,
                                  "reason": (r.why or [""])[0], "observations": t["records"], "period": r.period, "is_entry": True})
    out = {"sellers": sellers_, "entry_points": eps, "attention": attention, "data_mode": data_mode(db)}
    if not light:
        out["governorates"] = [{"name": l.name, "geometry": l.geometry} for l in govs.values()]
    if product_id:
        out["product_flow"] = product_flow(db, product_id)
    return out


def product_flow(db: Session, pid: str) -> dict:
    p = db.get(Product, pid)
    o = product_360(db, pid, "origin")["sections"]["origin"]
    cmap = {c.iso3: c for c in db.query(Country)}
    flows = [{"country": c["country"], "lat": cmap[c["iso3"]].lat, "lon": cmap[c["iso3"]].lon, "value": c["value"], "unit": c["unit"],
              "relation": "Flux enregistré"} for c in o["countries"][:10] if c["iso3"] in cmap and cmap[c["iso3"]].lat]
    zones = Counter(s.governorate for s in db.query(Seller).filter(Seller.category == (p.category if p else None)) if s.governorate)
    return {"product": p.short_name if p else pid, "origins": flows, "entry": entry_view(db, pid),
            "zones": [{"zone": g, "count": n, "relation": "Association statistique"} for g, n in zones.most_common(5)]}


# ============================================================ ÉCONOMIE (toujours données réelles)
def economic_history(db: Session) -> dict:
    def series(ind):
        return [{"period": e.period, "value": e.value} for e in db.query(EconomicIndicator).filter_by(indicator=ind).order_by(EconomicIndicator.period)]
    imp = {e["period"]: e["value"] for e in series("ins_imports_monthly")}
    exp = {e["period"]: e["value"] for e in series("ins_exports_monthly")}
    monthly = [{"period": k, "imports": imp[k], "exports": exp.get(k), "balance": (exp.get(k) - imp[k]) if exp.get(k) is not None else None,
                "coverage_rate": (exp.get(k) / imp[k]) if exp.get(k) and imp[k] else None} for k in sorted(imp)]
    return {"monthly_ins": monthly, "long_term": {"imports": series("wb_imports_gs"), "exports": series("wb_exports_gs")},
            "sources": [src(db, "ins_trade"), src(db, "world_bank_wdi")]}


def economic_forecast(db: Session) -> dict:
    out = {}
    for ind in ("ins_imports", "ins_exports"):
        rows = db.query(Forecast).filter_by(indicator=ind).order_by(Forecast.period).all()
        if not rows:
            out[ind] = {"available": False}
            continue
        m = rows[0].metrics or {}
        bt = m.get("backtest", {}).get(rows[0].model, {})
        out[ind] = {"available": True, "accuracy_pct": (100 - bt["MAPE"]) if bt.get("MAPE") is not None else None,
                    "history_period": m.get("train_period"),
                    "annual": [{"year": int(r.period), "predicted": r.predicted, "lower": r.lower, "upper": r.upper,
                                "partial": (r.metrics or {}).get("kind") == "ACTUAL + NOWCAST",
                                "actual_months": (r.metrics or {}).get("actual_months")} for r in rows]}
    act = {ind: [{"year": int(e.period), "value": e.value} for e in db.query(EconomicIndicator).filter_by(indicator=ind + "_annual").order_by(EconomicIndicator.period)]
           for ind in ("ins_imports", "ins_exports")}
    return {"forecasts": out, "actual": act, "unit": "millions de dinars (prix courants)", "sources": [src(db, "ins_trade")]}
