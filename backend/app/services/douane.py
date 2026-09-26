"""ESPACE DOUANE — read models for every Douane page. Only data present in the database is used;
when a piece of information does not exist, the payload says so ("Information non disponible" /
"Source non connectée") instead of inventing it.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..models import (Anomaly, Brand, Case, CaseTransfer, CommerceObservation, Country, CustomsImport, CustomsRecord,
                      DataSource, EntryPoint, FragmentationPattern, Location, PipelineRun, Product, RiskScore, Seller)
from .cases import (CLASS_FR, CONTINENT_FR, FIN_STATUS_FR, KIND_FR, MODE_FR, OPEN_STATUSES, STATUS_FR, _n, case_row,
                    classification_summary, month_fr)

NA = "Information non disponible"
NOT_CONNECTED = "Source non connectée : déclarations douanières détaillées (extrait autorisé)"
EP_TYPE_FR = {"AIRPORT": "Aéroport", "SEAPORT": "Port", "LAND_BORDER": "Passage terrestre"}
EP_MODE = {"AIRPORT": "AIR", "SEAPORT": "SEA", "LAND_BORDER": "LAND"}


def _has_decl(db: Session) -> bool:
    return db.query(CustomsImport.id).first() is not None


def _latest_comtrade_year(db: Session) -> str | None:
    return db.query(func.max(CustomsRecord.period)).filter(CustomsRecord.dataset == "comtrade_hs4_partner").scalar()


def _countries(db: Session) -> dict:
    return {c.iso3: c for c in db.query(Country)}


def _cname(c: Country | None, fallback=None):
    return (c.name_fr or c.name_en) if c else fallback


def _last_analysis(db: Session) -> str | None:
    r = db.query(PipelineRun).filter(PipelineRun.status == "DONE").order_by(PipelineRun.finished_at.desc()).first()
    return r.finished_at.strftime("%d/%m/%Y à %H:%M") if r and r.finished_at else None


# ============================================================ VUE D'ENSEMBLE
def overview(db: Session) -> dict:
    monitored = {p.id: p for p in db.query(Product).filter(Product.monitored.is_(True))}
    chapters = {p.chapter for p in monitored.values()}
    n_records = (db.query(func.count(CustomsRecord.id)).filter(CustomsRecord.dataset == "ins_chapter_month",
                                                               CustomsRecord.hs_code.in_(chapters)).scalar() or 0) + \
                (db.query(func.count(CustomsRecord.id)).filter(CustomsRecord.dataset == "comtrade_hs4_partner").scalar() or 0)
    n_decl = db.query(func.count(CustomsImport.id)).scalar() or 0
    n_obs = db.query(func.count(CommerceObservation.id)).scalar() or 0
    anomalies = (db.query(func.count(Anomaly.id)).filter(Anomaly.is_anomaly.is_(True), Anomaly.hs_code.in_(list(monitored) + list(chapters))).scalar() or 0) + \
                (db.query(func.count(FragmentationPattern.id)).filter(FragmentationPattern.status != "NORMAL").scalar() or 0)
    prio = db.query(func.count(Case.id)).filter(Case.classification == "PRIORITAIRE", Case.status.in_(OPEN_STATUSES)).scalar() or 0
    transferred = db.query(func.count(CaseTransfer.id)).scalar() or 0
    open_cases = db.query(Case).filter(Case.status.in_(OPEN_STATUSES)).order_by(Case.priority_score.desc()).limit(5).all()
    return {
        "kpis": [
            {"key": "operations", "label": "Opérations analysées", "value": n_records + n_decl + n_obs,
             "detail": f"{_n(n_records, 0)} enregistrements douaniers officiels · {_n(n_decl, 0)} déclarations · {_n(n_obs, 0)} observations commerciales"},
            {"key": "anomalies", "label": "Anomalies détectées", "value": anomalies, "detail": "Situations sortant du comportement habituel"},
            {"key": "priority", "label": "Dossiers prioritaires", "value": prio, "detail": "À examiner en premier"},
            {"key": "transferred", "label": "Dossiers transmis", "value": transferred, "detail": "Transmis à Finance après vérification"},
        ],
        "classification": classification_summary(db),
        "top_cases": [case_row(c) for c in open_cases],
        "last_analysis": _last_analysis(db),
        "declarations_connected": n_decl > 0,
        "declarations_note": None if n_decl else ("La détection de fragmentation au niveau des opérations individuelles nécessite l'extrait "
                                                  "des déclarations détaillées. Les analyses actuelles portent sur les statistiques officielles "
                                                  "et les observations commerciales publiques."),
    }


# ============================================================ GRAPHIQUES DOUANE
def charts(db: Session) -> dict:
    monitored = {p.id: p for p in db.query(Product).filter(Product.monitored.is_(True))}
    chapters = {p.chapter for p in monitored.values()}
    out = {}
    # anomalies over time (official monthly statistics, monitored chapters)
    rows = db.query(Anomaly.period, func.count(Anomaly.id)).filter(Anomaly.subject_type == "HS_CHAPTER_MONTH", Anomaly.is_anomaly.is_(True),
                                                                   Anomaly.hs_code.in_(chapters)).group_by(Anomaly.period).all()
    all_months = sorted({p for (p,) in db.query(Anomaly.period).filter(Anomaly.subject_type == "HS_CHAPTER_MONTH").distinct()})
    cnt = dict(rows)
    out["anomalies_time"] = {"available": bool(all_months), "unit": "anomalies", "source": "INS — publication mensuelle",
                             "rows": [{"label": m, "value": cnt.get(m, 0)} for m in all_months][-36:]}
    # small flows over time (declarations only)
    if _has_decl(db):
        decl = db.query(CustomsImport.declaration_date, CustomsImport.declared_value).all()
        vals = sorted(v for _, v in decl if v is not None)
        thr = vals[len(vals) // 4] if vals else 0
        weeks = Counter()
        for d, v in decl:
            if v is not None and v <= thr:
                weeks[(d - timedelta(days=d.weekday())).date().isoformat()] += 1
        out["small_flows_time"] = {"available": True, "unit": "petites opérations", "threshold": thr, "source": "Déclarations douanières",
                                   "rows": [{"label": k, "value": v} for k, v in sorted(weeks.items())][-52:]}
        modes = Counter(r[0] for r in db.query(CustomsImport.transport_mode) if r[0])
        out["modes"] = {"available": bool(modes), "rows": [{"label": MODE_FR.get(k, k), "value": v} for k, v in modes.most_common()],
                        "unit": "opérations", "source": "Déclarations douanières"}
        eps = {e.entry_point_id: e for e in db.query(EntryPoint)}
        ec = Counter(r[0] for r in db.query(CustomsImport.entry_point_id) if r[0])
        out["entry_points"] = {"available": bool(ec), "unit": "opérations", "source": "Déclarations douanières",
                               "rows": [{"label": eps[k].official_name if k in eps else k, "value": v} for k, v in ec.most_common(10)]}
    else:
        for k in ("small_flows_time", "modes", "entry_points"):
            out[k] = {"available": False, "message": NOT_CONNECTED, "rows": []}
    cases = db.query(Case).all()
    by_prod, by_cat, by_country = Counter(), Counter(), Counter()
    for c in cases:
        by_prod[c.product] += 1
        by_cat[c.category] += 1
        if c.country:
            by_country[c.country] += 1
    out["products"] = {"available": bool(cases), "unit": "dossiers", "source": "Dossiers issus de l'analyse",
                       "rows": [{"label": k, "value": v} for k, v in by_prod.most_common(10)]}
    out["categories"] = {"available": bool(cases), "unit": "dossiers", "source": "Dossiers issus de l'analyse",
                         "rows": [{"label": k or NA, "value": v} for k, v in by_cat.most_common()]}
    out["countries_cases"] = {"available": bool(by_country), "unit": "dossiers", "source": "Dossiers issus de l'analyse",
                              "rows": [{"label": k, "value": v} for k, v in by_country.most_common(10)]}
    o = origins(db)
    out["countries"] = {"available": bool(o["countries"]), "unit": "USD", "source": o["source"], "period": o["period"],
                        "rows": [{"label": c["country"], "value": c["value"]} for c in o["countries"][:10]]}
    out["continents"] = {"available": bool(o["continents"]), "unit": "%", "source": o["source"], "period": o["period"],
                         "rows": [{"label": c["continent"], "value": round(c["share"] * 100, 1)} for c in o["continents"]]}
    out["classification"] = {"available": True, "unit": "situations analysées", "source": "Analyse IA",
                             "rows": [{"label": k, "value": v} for k, v in classification_summary(db).items()]}
    return out


# ============================================================ COMMERCE EN LIGNE
def commerce(db: Session) -> dict:
    from .queries import digital_commerce
    d = digital_commerce(db, "all")
    d.pop("data_mode", None)
    # commerce vs customs by category (comparison of two separate measures — never merged into one)
    year = _latest_comtrade_year(db)
    prods = {p.id: p for p in db.query(Product).filter(Product.monitored.is_(True))}
    imp = Counter()
    for hs, v in db.query(CustomsRecord.hs_code, func.sum(CustomsRecord.value)).filter(
            CustomsRecord.dataset == "comtrade_hs4_partner", CustomsRecord.period == year).group_by(CustomsRecord.hs_code):
        if hs in prods:
            imp[prods[hs].category] += v or 0
    obs = Counter()
    for (pid,) in db.query(CommerceObservation.product_id).filter(CommerceObservation.product_id.isnot(None)):
        if pid in prods:
            obs[prods[pid].category] += 1
    shops = Counter(s[0] for s in db.query(Seller.category) if s[0])
    cats = sorted(set(imp) | set(obs) | set(shops), key=lambda c: -imp.get(c, 0))
    d["comparison"] = {"year": year, "rows": [{"category": c, "imports_usd": imp.get(c), "observations": obs.get(c, 0), "shops": shops.get(c, 0)} for c in cats],
                       "note": "Deux mesures différentes présentées côte à côte : une observation ou un commerce référencé ne représente pas un volume de ventes."}
    soc = db.query(DataSource).filter_by(key="social_commerce").first()
    d["sources_status"] = [
        {"name": "Registres ouverts de produits", "status": "Connectée"},
        {"name": "Localisations commerciales publiques", "status": "Connectée"},
        {"name": "Réseaux sociaux (pages publiques)", "status": "Connectée" if soc and soc.status == "CONNECTED" else "Source non connectée"},
    ]
    d["sellers_total"] = db.query(func.count(Seller.id)).scalar()
    d["sellers_with_links"] = db.query(func.count(Seller.id)).filter((Seller.facebook.isnot(None)) | (Seller.website.isnot(None)) | (Seller.instagram.isnot(None))).scalar()
    return d


# ============================================================ CARTE / ZONES
def _gov_centroids(db: Session) -> dict:
    return {l.name: (l.centroid_lat, l.centroid_lon) for l in db.query(Location).filter(Location.level == "governorate")}


def control_map(db: Session, light: bool = False) -> dict:
    eps = db.query(EntryPoint).all()
    has_decl = _has_decl(db)
    ep_ops = Counter(r[0] for r in db.query(CustomsImport.entry_point_id) if r[0]) if has_decl else Counter()
    ep_cases = Counter()
    for c in db.query(Case).filter(Case.entry_points.isnot(None)):
        for e in c.entry_points or []:
            ep_cases[e.get("id")] += 1
    cents = _gov_centroids(db)
    zones = zone_stats(db)
    sellers = [{"id": s.id, "lat": s.lat, "lon": s.lon, "name": s.name, "category": s.category, "governorate": s.governorate}
               for s in db.query(Seller).filter(Seller.lat.isnot(None))]
    small = Counter()
    if has_decl:
        vals = sorted(v for (v,) in db.query(CustomsImport.declared_value) if v is not None)
        thr = vals[len(vals) // 4] if vals else 0
        for g, v in db.query(CustomsImport.destination_governorate, CustomsImport.declared_value):
            if g and v is not None and v <= thr:
                small[g] += 1
    out = {
        "entry_points": [{"id": e.entry_point_id, "name": e.official_name, "type": e.entry_type, "type_fr": EP_TYPE_FR.get(e.entry_type),
                          "lat": e.latitude, "lon": e.longitude, "governorate": e.governorate, "source_url": e.source_url,
                          "operations": ep_ops.get(e.entry_point_id) if has_decl else None, "cases": ep_cases.get(e.entry_point_id, 0)}
                         for e in eps],
        "zones": [{**z, "lat": cents.get(z["governorate"], (None, None))[0], "lon": cents.get(z["governorate"], (None, None))[1],
                   "small_flows": small.get(z["governorate"]) if has_decl else None} for z in zones],
        "sellers": sellers,
        "declarations_connected": has_decl,
        "notes": [] if has_decl else ["Opérations par point d'entrée et concentrations de petits flux : " + NOT_CONNECTED.split(" : ")[1]],
    }
    if not light:
        out["governorates"] = [{"name": l.name, "geometry": l.geometry} for l in db.query(Location).filter(Location.level == "governorate")]
    return out


def zone_stats(db: Session) -> list[dict]:
    shops = defaultdict(Counter)
    for s in db.query(Seller.governorate, Seller.category):
        if s[0]:
            shops[s[0]][s[1] or "Autre"] += 1
    cases = defaultdict(list)
    for c in db.query(Case):
        if c.geographic_zone:
            cases[c.geographic_zone].append(c)
    total_cases = sum(len(v) for v in cases.values()) or 1
    total_shops = sum(sum(v.values()) for v in shops.values()) or 1
    out = []
    for g in set(shops) | set(cases):
        cs = cases.get(g, [])
        share_cases = len(cs) / total_cases
        share_shops = sum(shops[g].values()) / total_shops
        maxs = max((c.priority_score for c in cs), default=0)
        idx = round(min(100.0, 0.5 * maxs + 30 * share_cases / max(0.01, max(share_cases, 0.34)) + 20 * min(1, share_shops * 3)), 1) if cs else round(20 * min(1, share_shops * 3), 1)
        out.append({"governorate": g, "shops": sum(shops[g].values()), "categories": [k for k, _ in shops[g].most_common(3)],
                    "cases": len(cs), "case_share": share_cases, "shop_share": share_shops, "priority_index": idx,
                    "level": CLASS_FR["PRIORITAIRE"] if idx >= 75 else CLASS_FR["A_VERIFIER"] if idx >= 55 else CLASS_FR["A_SURVEILLER"] if idx >= 35 else CLASS_FR["HABITUEL"]})
    out.sort(key=lambda z: -z["priority_index"])
    return out


def zone_detail(db: Session, gov: str) -> dict:
    sellers = db.query(Seller).filter(Seller.governorate == gov).all()
    cs = db.query(Case).filter(Case.geographic_zone == gov).order_by(Case.priority_score.desc()).all()
    if not sellers and not cs:
        return {"governorate": gov, "available": False, "message": NA}
    stats = next((z for z in zone_stats(db) if z["governorate"] == gov), None)
    cats = Counter(s.category for s in sellers if s.category)
    cities = Counter(s.city for s in sellers if s.city)
    prods = Counter(c.product for c in cs)
    months = Counter((c.period_end or c.created_at).strftime("%Y-%m") for c in cs)
    obs = db.query(CommerceObservation).filter(CommerceObservation.public_business_location.ilike(f"%{gov}%")).count()
    why = []
    if stats and stats["cases"]:
        why.append(f"La zone est associée à {stats['cases']} dossier(s), soit {stats['case_share'] * 100:.0f} % des dossiers détectés.")
    if cats:
        top, n = cats.most_common(1)[0]
        why.append(f"{len(sellers)} commerce(s) référencé(s) publiquement, dont {n} dans la catégorie « {top} ».")
    if cs:
        why.append(f"Dossier le plus élevé : {cs[0].product} — indice {cs[0].priority_score:.0f}/100 ({cs[0].motif.split(' — ')[0].lower()}).")
    why.append("Le rattachement d'un dossier à une zone repose sur la localisation publique des commerces de la catégorie "
               "(corrélation statistique), sauf lorsque les déclarations indiquent le gouvernorat de destination.")
    return {"governorate": gov, "available": True, "cities": [k for k, _ in cities.most_common(5)],
            "shops": len(sellers), "observations": obs, "categories": [{"label": k, "value": v} for k, v in cats.most_common(6)],
            "products": [{"label": k, "value": v} for k, v in prods.most_common(6)], "anomalies": [case_row(c) for c in cs[:10]],
            "evolution": [{"label": k, "value": v} for k, v in sorted(months.items())],
            "priority_index": stats["priority_index"] if stats else None, "level": stats["level"] if stats else None, "why": why,
            "sellers": [{"id": s.id, "name": s.name, "category": s.category, "city": s.city,
                         "link": s.website or s.facebook or s.instagram} for s in sellers if s.name][:30],
            "evidence": {"sources": [{"name": "Localisations commerciales publiques", "observations": len(sellers)},
                                     {"name": "Dossiers issus de l'analyse", "observations": len(cs)}],
                         "information_used": ["Gouvernorat et ville publiés", "Catégorie de commerce", "Dossiers rattachés à la zone"]}}


def geo_analysis(db: Session, emit) -> dict:
    step = _stepper(emit)
    step("Lecture des localisations commerciales publiques")
    zones = zone_stats(db)
    step("Croisement avec les dossiers détectés")
    step("Analyse des points d'entrée")
    m = control_map(db, light=True)
    step("Calcul des concentrations")
    top = [z for z in zones if z["cases"]][:5]
    step(None)
    tot = sum(z["cases"] for z in zones) or 1
    lines = []
    for z in top[:3]:
        lines.append(f"**{z['governorate']}** concentre {z['cases']} dossier(s) ({z['cases'] / tot * 100:.0f} % du total) et "
                     f"{z['shops']} commerce(s) référencé(s), principalement : {', '.join(z['categories'][:2]) or NA}. "
                     f"Indice de priorité de la zone : {z['priority_index']:.0f}/100.")
    eps_cases = [e for e in m["entry_points"] if e["cases"]]
    ep_line = ("Points d'entrée associés aux dossiers : " + ", ".join(f"{e['name']} ({e['cases']})" for e in sorted(eps_cases, key=lambda e: -e['cases'])[:3]) + "."
               ) if eps_cases else ("Aucun point d'entrée ne peut être associé aux dossiers avec les données connectées "
                                    "(les statistiques officielles publiques n'indiquent pas le point d'entrée).")
    text = "Selon les données disponibles :\n" + "\n".join(f"• {l}" for l in lines) + f"\n• {ep_line}\n" + \
           "Ces zones méritent une attention renforcée ; il s'agit de priorités d'analyse, pas de conclusions."
    return {"text": text, "zones": top}


# ============================================================ PRODUITS OBSERVÉS / 360°
def _product_images(db: Session) -> dict:
    out = {}
    for pid, url, link in db.query(CommerceObservation.product_id, CommerceObservation.image_url, CommerceObservation.page_url).filter(
            CommerceObservation.product_id.isnot(None), CommerceObservation.image_url.isnot(None)):
        out.setdefault(pid, {"image_url": url, "source": link})
    return out


def _supplier(db: Session, pid: str, year: str | None, countries: dict) -> dict | None:
    if not year:
        return None
    rows = db.query(CustomsRecord).filter(CustomsRecord.dataset == "comtrade_hs4_partner", CustomsRecord.hs_code == pid,
                                          CustomsRecord.period == year).all()
    tot = sum(r.value or 0 for r in rows)
    if not tot:
        return None
    top = max(rows, key=lambda r: r.value or 0)
    c = countries.get(top.partner_iso3)
    return {"country": _cname(c, top.partner_name), "continent": CONTINENT_FR.get(c.continent) if c else None,
            "share": (top.value or 0) / tot, "total_usd": tot, "year": year}


def products_observed(db: Session) -> dict:
    from .queries import top_observed_products
    top = top_observed_products(db, "all", limit=40)
    countries = _countries(db)
    year = _latest_comtrade_year(db)
    risks = {r.product_id: r.score for r in db.query(RiskScore)}
    cases = Counter(c.product_id for c in db.query(Case) if c.product_id)
    maxcase = defaultdict(float)
    for c in db.query(Case):
        if c.product_id:
            maxcase[c.product_id] = max(maxcase[c.product_id], c.priority_score)
    items = []
    for i in top["items"]:
        sup = _supplier(db, i["product_id"], year, countries)
        items.append({**i, "sources": len(i["platforms"]), "provenance": sup, "entry_point": None,
                      "priority_score": maxcase.get(i["product_id"]) or risks.get(i["product_id"]),
                      "cases": cases.get(i["product_id"], 0)})
    imgs = _product_images(db)
    observed = {i["product_id"] for i in items}
    others = []
    for p in db.query(Product).filter(Product.monitored.is_(True)).order_by(Product.category, Product.short_name):
        if p.id in observed:
            continue
        sup = _supplier(db, p.id, year, countries)
        others.append({"product_id": p.id, "product": p.short_name, "category": p.category, "observations": 0,
                       "image_url": imgs.get(p.id, {}).get("image_url"), "provenance": sup,
                       "priority_score": maxcase.get(p.id) or risks.get(p.id), "cases": cases.get(p.id, 0)})
    return {"observed": items, "others": others, "sales_data": False,
            "note": "Aucune donnée réelle de ventes n'est connectée : le classement porte sur le nombre d'observations publiques, pas sur les ventes."}


def product_360(db: Session, pid: str) -> dict | None:
    from .queries import entry_view, product_360 as p360
    p = db.get(Product, pid)
    if not p:
        return None
    countries = _countries(db)
    year = _latest_comtrade_year(db)
    sec = p360(db, pid, None)["sections"]
    obs = sec["online"]
    imgs = [i for i in obs["items"] if i.get("image_url")]
    origin = sec["origin"]
    by_year = sec["customs"]["by_year"]
    evo = None
    if len(by_year) >= 2 and by_year[-2]["value"]:
        evo = by_year[-1]["value"] / by_year[-2]["value"] - 1
    ev = entry_view(db, pid)
    cases = db.query(Case).filter(Case.product_id == pid).order_by(Case.priority_score.desc()).all()
    zones = sec["geography"]["governorates"]
    decl_n = sec["customs"]["declarations"]
    top_c = origin["countries"][0] if origin["countries"] else None
    maxscore = cases[0].priority_score if cases else (sec["risk"].get("score") if sec.get("risk") else None)
    advice = _product_advice(p, cases, top_c, ev, zones)
    return {
        "product_id": pid, "name": p.short_name, "category": p.category, "hs": p.id,
        "image": imgs[0] if imgs else None,
        "gallery": [{"image_url": i["image_url"], "source": i["platform"], "date": i["date"], "price": i["price"],
                     "seller": i["seller"], "link": i["link"], "product": i["product"]} for i in obs["items"] if i.get("image_url")],
        "origin": {"country": top_c["country"] if top_c else None, "continent": top_c["continent"] if top_c else None,
                   "share": top_c["share"] if top_c else None, "year": origin["year"], "countries": origin["countries"][:8],
                   "continents": origin["continents"],
                   "brand_country": NA, "manufacturing": _manufacturing(db, pid), "export_country": NA,
                   "provenance": NA if not decl_n else "Voir les déclarations"},
        "imports": {"by_year": by_year, "evolution": evo, "declarations": decl_n,
                    "frequency": f"{decl_n} déclaration(s)" if decl_n else "Fréquence des opérations : " + NOT_CONNECTED.split(" : ")[1]},
        "entry": ev, "online": {"observations": obs["observations"], "platforms": obs["platforms"], "brands": obs["brands"],
                                "price_min": obs["price_min"], "price_max": obs["price_max"]},
        "zones": zones[:6], "cases": [case_row(c) for c in cases[:8]], "priority_score": maxscore,
        "level": CLASS_FR.get(cases[0].classification) if cases else None, "advice": advice,
        "risk": sec.get("risk"),
    }


def _manufacturing(db: Session, pid: str) -> list[dict]:
    c = Counter(o.manufacturing_place.strip() for o in db.query(CommerceObservation).filter(
        CommerceObservation.product_id == pid, CommerceObservation.manufacturing_place.isnot(None)) if o.manufacturing_place.strip())
    return [{"label": k, "value": v} for k, v in c.most_common(5)]


def _product_advice(p: Product, cases: list[Case], top_c: dict | None, ev: dict, zones: list[dict]) -> dict:
    why = []
    if cases:
        why.append(f"{len(cases)} dossier(s) détecté(s) ; le plus élevé : {cases[0].motif.split(' — ')[0].lower()} (indice {cases[0].priority_score:.0f}/100).")
    if top_c and top_c.get("share"):
        why.append(f"Principal pays d'origine : {top_c['country']} ({top_c['share'] * 100:.0f} % de la valeur importée).")
    if ev.get("available"):
        why.append(f"Mode d'entrée principal : {ev['main_mode']}.")
    if zones:
        why.append(f"Zone commerciale la plus représentée : {zones[0]['governorate']} ({zones[0]['count']} commerces de la catégorie).")
    if cases and cases[0].classification == "PRIORITAIRE":
        action = f"Examiner en priorité le dossier {cases[0].case_ref} et vérifier les valeurs déclarées pour ce produit."
    elif cases:
        action = "Ouvrir les dossiers associés et vérifier les éléments signalés avant toute transmission."
    else:
        action = "Aucune action immédiate : maintenir le produit sous observation lors des prochaines analyses."
    return {"why": why or ["Données insuffisantes pour formuler une recommandation."], "action": action}


def analyze_product(db: Session, pid: str, emit) -> dict:
    from .queries import entry_view, product_360 as p360
    step = _stepper(emit)
    for label, section in (("Recherche des observations", "online"), ("Analyse de l'origine", "origin"), ("Analyse des flux", "customs"),
                           ("Analyse des points d'entrée", None), ("Analyse géographique", "geography"),
                           ("Recherche des activités associées", "sellers"), ("Recherche des anomalies", "anomalies")):
        step(label)
        entry_view(db, pid) if section is None else p360(db, pid, section)
    step("Génération du parcours")
    res = {"product": product_360(db, pid), "pathway": pathway(db, pid)}
    step(None)
    return res


# ============================================================ ORIGINE DES PRODUITS / FLUX
def origins(db: Session, category: str | None = None, product: str | None = None, year: str | None = None) -> dict:
    countries = _countries(db)
    years = [y for (y,) in db.query(CustomsRecord.period).filter(CustomsRecord.dataset == "comtrade_hs4_partner").distinct().order_by(CustomsRecord.period)]
    year = year if year in years else (years[-1] if years else None)
    prods = {p.id: p for p in db.query(Product).filter(Product.monitored.is_(True))}
    ids = [k for k, p in prods.items() if (not category or p.category == category) and (not product or k == product)]
    rows = db.query(CustomsRecord).filter(CustomsRecord.dataset == "comtrade_hs4_partner", CustomsRecord.period == year,
                                          CustomsRecord.hs_code.in_(ids)).all() if year and ids else []
    byc, cont, bycat = Counter(), Counter(), defaultdict(Counter)
    for r in rows:
        c = countries.get(r.partner_iso3)
        byc[r.partner_iso3 or r.partner_name] += r.value or 0
        ct = CONTINENT_FR.get(c.continent, c.continent) if c else "Non précisé"
        cont[ct] += r.value or 0
        bycat[prods[r.hs_code].category][ct] += r.value or 0
    tot = sum(byc.values())
    clist = []
    for iso, v in byc.most_common(15):
        c = countries.get(iso)
        clist.append({"iso3": iso, "country": _cname(c, "Zones non précisées"), "continent": CONTINENT_FR.get(c.continent) if c else None,
                      "value": v, "share": v / tot if tot else None, "lat": c.lat if c else None, "lon": c.lon if c else None})
    brands = db.query(Brand).filter(Brand.brand_origin_country.isnot(None)).count()
    return {"year": year, "years": years, "period": year, "source": "Nations unies — statistiques du commerce", "unit": "USD", "total": tot,
            "countries": clist,
            "continents": [{"continent": k, "value": v, "share": v / tot} for k, v in cont.most_common()] if tot else [],
            "by_category": [{"category": k, **{ct: v for ct, v in d.items()}} for k, d in bycat.items()],
            "top_continent": cont.most_common(1)[0][0] if cont else None,
            "concepts": [
                {"label": "Pays de la marque", "status": "Information non disponible" if not brands else f"{brands} marque(s) documentée(s)",
                 "detail": "Pays d'origine de la marque commerciale. Aucune source connectée ne le fournit de manière fiable."},
                {"label": "Pays de fabrication", "status": "Disponible" if tot else NA,
                 "detail": "Pays d'origine déclaré dans les statistiques d'importation (lieu de production des marchandises)."},
                {"label": "Pays d'exportation", "status": NA,
                 "detail": "Pays depuis lequel la marchandise a été expédiée. Non publié par les sources connectées."},
                {"label": "Pays de provenance", "status": "Disponible" if _has_decl(db) else "Source non connectée",
                 "detail": "Dernier pays de transit avant l'arrivée en Tunisie. Figure uniquement dans les déclarations détaillées."},
            ],
            "note": "Ces quatre informations sont distinctes et ne sont jamais considérées comme identiques."}


def flows(db: Session, product: str | None = None, category: str | None = None, year: str | None = None) -> dict:
    o = origins(db, category, product, year)
    has_decl = _has_decl(db)
    ev = None
    if product:
        from .queries import entry_view
        ev = entry_view(db, product)
    paths = []
    for c in o["countries"][:10]:
        if c["lat"] is None:
            continue
        paths.append({"continent": c["continent"], "country": c["country"], "lat": c["lat"], "lon": c["lon"], "value": c["value"],
                      "share": c["share"], "entry": (ev["modes"][0]["mode"] if ev and ev.get("available") else None),
                      "entry_point": (ev["entry_points"][0]["name"] if ev and ev.get("available") and ev["entry_points"] else None)})
    return {"year": o["year"], "years": o["years"], "unit": "USD", "metric": "valeur importée", "paths": paths,
            "continents": o["continents"], "entry_known": bool(ev and ev.get("available")),
            "entry_note": None if (ev and ev.get("available")) else ("Le mode et le point d'entrée ne sont affichés que lorsque les déclarations "
                                                                     "détaillées permettent de les établir." if not has_decl else None),
            "source": o["source"]}


# ============================================================ PARCOURS INTELLIGENT (réseau)
REL = {"OBS": "OBSERVÉ", "VER": "VÉRIFIÉ", "STAT": "CORRÉLATION STATISTIQUE", "HYP": "HYPOTHÈSE À VÉRIFIER", "NA": "DONNÉE NON CONNECTÉE"}
LAYERS = ["Continent", "Pays", "Produit", "Importations", "Mer / Air / Terre", "Point d'entrée", "Zone en Tunisie",
          "Activité commerciale", "Analyse des liens", "Anomalie", "Priorité", "Douane", "Finance"]


def pathway(db: Session, product: str | None = None) -> dict:
    countries = _countries(db)
    year = _latest_comtrade_year(db)
    prods_all = {p.id: p for p in db.query(Product).filter(Product.monitored.is_(True))}
    if product and product in prods_all:
        prods = [prods_all[product]]
    else:
        ranked = Counter()
        for c in db.query(Case):
            if c.product_id:
                ranked[c.product_id] = max(ranked[c.product_id], c.priority_score)
        prods = [prods_all[k] for k, _ in ranked.most_common(3) if k in prods_all]
    nodes, edges = {}, []

    def node(nid, layer, label, sub=None, detail=None, unavailable=False, **extra):
        if nid not in nodes:
            nodes[nid] = {"id": nid, "layer": layer, "label": label, "sub": sub, "detail": detail, "unavailable": unavailable, **extra}
        return nid

    def edge(a, b, rel, why, weight=1.0):
        edges.append({"source": a, "target": b, "relation": REL[rel], "why": why, "weight": weight})

    has_decl = _has_decl(db)
    ids = [p.id for p in prods]
    cr = db.query(CustomsRecord).filter(CustomsRecord.dataset == "comtrade_hs4_partner", CustomsRecord.period == year,
                                        CustomsRecord.hs_code.in_(ids)).all() if year else []
    by_prod = defaultdict(list)
    for r in cr:
        by_prod[r.hs_code].append(r)
    zones_by_cat = defaultdict(Counter)
    for s in db.query(Seller.category, Seller.governorate):
        if s[0] and s[1]:
            zones_by_cat[s[0]][s[1]] += 1
    obs = Counter(r[0] for r in db.query(CommerceObservation.product_id).filter(CommerceObservation.product_id.in_(ids)))
    links = node("LINK", 8, "Croisement des données", "Analyse des liens",
                 "L'IA rapproche les flux d'importation, les points d'entrée, les zones commerciales et l'activité observée.")
    douane = node("DOUANE", 11, "Vérification Douane", "Décision humaine", "Seul un agent de la Douane peut valider un dossier et le transmettre.")
    finance = node("FINANCE", 12, "Analyse Finance", "Dossiers transmis", "Finance reçoit uniquement les dossiers transmis par la Douane.")
    n_transfers = 0
    for p in prods:
        pn = node(f"P:{p.id}", 2, p.short_name, p.category, f"Position tarifaire {p.id} — catégorie {p.category}.", product_id=p.id)
        rows = sorted(by_prod.get(p.id, []), key=lambda r: -(r.value or 0))
        tot = sum(r.value or 0 for r in rows)
        for r in rows[:3]:
            c = countries.get(r.partner_iso3)
            cont = CONTINENT_FR.get(c.continent, c.continent) if c else "Non précisé"
            kn = node(f"K:{cont}", 0, cont, "Continent")
            cn = node(f"C:{r.partner_iso3}", 1, _cname(c, r.partner_name), cont, iso3=r.partner_iso3)
            edge(kn, cn, "VER", f"{_cname(c, r.partner_name)} appartient au continent {cont} (référentiel officiel des pays).")
            edge(cn, pn, "OBS", f"{_n((r.value or 0) / 1e6)} M USD importés en {year} ({(r.value or 0) / tot * 100:.0f} % du produit) — "
                                f"statistiques officielles d'importation.", weight=(r.value or 0) / tot if tot else 0)
        imp = node(f"I:{p.id}", 3, "Importations", f"{_n(tot / 1e6)} M USD ({year})" if tot else NA,
                   "Flux d'importation déclarés pour ce produit." + ("" if has_decl else " Le détail des petites opérations individuelles nécessite l'extrait des déclarations."),
                   unavailable=not tot)
        edge(pn, imp, "OBS" if tot else "NA", "Valeurs d'importation publiées." if tot else NA)
        ev = None
        if has_decl:
            from .queries import entry_view
            ev = entry_view(db, p.id)
        if ev and ev.get("available"):
            for m in ev["modes"][:3]:
                mn = node(f"M:{m['key']}", 4, m["mode"], f"{m['share'] * 100:.0f} % de la valeur")
                edge(imp, mn, "OBS", f"{m['records']} déclaration(s) par {m['mode'].lower()}.")
                for t in ev["entry_points"][:3]:
                    if {"Port": "SEA", "Aéroport": "AIR", "Frontière terrestre": "LAND"}.get(t["type"]) == m["key"]:
                        en = node(f"E:{t['entry_point_id']}", 5, t["name"], t["type"])
                        edge(mn, en, "OBS", f"{t['records']} opération(s) ({t['share'] * 100:.0f} % de la valeur).")
            last = [n for n in nodes if n.startswith("E:")] or [f"M:{ev['modes'][0]['key']}"]
        else:
            mn = node("M:NA", 4, "Mode d'entrée", NA, "Les statistiques publiques n'indiquent pas si le produit entre par mer, air ou terre.", unavailable=True)
            en = node("E:NA", 5, "Point d'entrée", NA, "Le point d'entrée n'est connu qu'avec les déclarations détaillées.", unavailable=True)
            edge(imp, mn, "NA", NOT_CONNECTED)
            edge(mn, en, "NA", NOT_CONNECTED)
            last = [en]
        for g, n in zones_by_cat[p.category].most_common(2):
            zn = node(f"Z:{g}", 6, g, "Gouvernorat")
            for l in last:
                edge(l, zn, "STAT", f"{n} commerce(s) de la catégorie « {p.category} » sont référencés publiquement dans ce gouvernorat. "
                                    "Le lien entre point d'entrée et zone est une corrélation statistique, pas un trajet observé.")
            an = node(f"A:{p.category}:{g}", 7, f"{n} commerces", p.category, "Commerces publiquement référencés de la catégorie.")
            edge(zn, an, "OBS", "Localisations commerciales publiques.")
            edge(an, links, "STAT", "L'activité commerciale observée est comparée aux flux d'importation.")
        if obs.get(p.id):
            on = node(f"O:{p.id}", 7, f"{obs[p.id]} observations", "Commerce en ligne", "Observations publiques du produit (une observation n'est pas une vente).")
            edge(pn, on, "OBS", "Produit observé dans des sources commerciales publiques.")
            edge(on, links, "STAT", "Rapprochement des observations et des flux.")
        cases = db.query(Case).filter(Case.product_id == p.id).order_by(Case.priority_score.desc()).limit(2).all()
        for c in cases:
            xn = node(f"X:{c.id}", 9, c.case_ref, KIND_FR.get(c.kind, c.kind), f"{c.motif}. {c.explanation}", case_id=c.id)
            edge(links, xn, "STAT", "; ".join(i["label"] for i in (c.risk_indicators or [])[:2]) or c.motif)
            lvl = CLASS_FR.get(c.classification)
            pr = node(f"R:{c.id}", 10, f"{c.priority_score:.0f}/100", lvl, f"Indice de priorité {c.priority_score:.0f}/100 — classement : {lvl}.", case_id=c.id)
            edge(xn, pr, "HYP", "Une anomalie est une hypothèse à vérifier, jamais une preuve.")
            verified = c.status not in ("A_ANALYSER",)
            edge(pr, douane, "VER" if verified else "HYP", f"Dossier {STATUS_FR.get(c.status, c.status).lower()}.")
            if c.status == "TRANSMIS":
                n_transfers += 1
                edge(douane, finance, "VER", f"Dossier {c.case_ref} transmis à Finance par un agent de la Douane.")
    nodes["FINANCE"]["sub"] = f"{n_transfers} dossier(s) transmis" if n_transfers else "Aucun dossier transmis"
    return {"layers": LAYERS, "nodes": list(nodes.values()), "edges": edges, "product": product,
            "products": [{"id": p.id, "name": p.short_name} for p in prods_all.values()],
            "relations": [{"key": v, "label": v} for v in REL.values()],
            "note": "Une corrélation n'est jamais une preuve. Seuls les liens « observé » et « vérifié » reposent directement sur une source."}


# ============================================================ CONSEILLER IA
def advisor(db: Session, emit) -> dict:
    step = _stepper(emit)
    step("Analyse géographique")
    zones = {z["governorate"]: z for z in zone_stats(db)}
    step("Analyse des produits")
    cases = [c for c in db.query(Case).filter(Case.status != "CLASSE")]
    step("Analyse des points d'entrée")
    has_decl = _has_decl(db)
    step("Analyse des anomalies")
    groups = defaultdict(list)
    for c in cases:
        ep = (c.entry_points or [{}])[0].get("name") if c.entry_points else None
        groups[(c.category, c.geographic_zone, ep)].append(c)
    step("Analyse de l'évolution récente")
    total = len(cases) or 1
    ranked = []
    for (cat, zone, ep), lst in groups.items():
        lst.sort(key=lambda c: -c.priority_score)
        score = min(100.0, lst[0].priority_score * 0.7 + 30 * min(1.0, len(lst) / max(3, total * 0.25)))
        ranked.append((score, cat, zone, ep, lst))
    ranked.sort(key=lambda r: -r[0])
    recs = []
    for rank, (score, cat, zone, ep, lst) in enumerate(ranked[:3], 1):
        kinds = Counter(KIND_FR[c.kind] for c in lst)
        recent = [c for c in lst if c.period_end and c.period_end >= datetime.utcnow() - timedelta(days=365)]
        why = [f"{len(lst)} dossier(s) similaire(s) dans la catégorie « {cat} » ({len(lst) / total * 100:.0f} % des dossiers ouverts)."]
        why.append("Motifs : " + ", ".join(f"{k.lower()} ({v})" for k, v in kinds.most_common(3)) + ".")
        if zone and zone in zones:
            z = zones[zone]
            why.append(f"{zone} regroupe {z['shops']} commerce(s) référencé(s) et {z['cases']} dossier(s) au total.")
        if recent:
            why.append(f"{len(recent)} signal(s) portant sur les 12 derniers mois.")
        vals = [c.value_concerned for c in lst if c.value_concerned]
        if vals:
            why.append(f"Valeur des opérations concernées : {_n(sum(vals) / 1e6)} M {lst[0].amount_unit}.")
        level = CLASS_FR["PRIORITAIRE"] if score >= 75 else CLASS_FR["A_VERIFIER"] if score >= 55 else CLASS_FR["A_SURVEILLER"]
        evo = "hausse" if any(c.kind == "HAUSSE" for c in lst) else "baisse" if any(c.kind == "BAISSE" for c in lst) else "stable ou non mesurable"
        where = ep or "Point d'entrée : " + ("non déterminable" if has_decl else NA.lower())
        recs.append({
            "rank": rank, "zone": zone or NA, "entry_point": ep or NA, "entry_note": None if ep else NOT_CONNECTED,
            "category": cat, "products": sorted({c.product for c in lst})[:4], "evolution": evo, "level": level,
            "priority_score": round(score, 1), "why": why,
            "action": (f"Renforcer temporairement l'analyse de la catégorie « {cat} »" + (f" au niveau de {ep}" if ep else "")
                       + (f" et des circuits de distribution de la zone de {zone}" if zone else "") + ", en commençant par le dossier "
                       + lst[0].case_ref + "."),
            "case_ids": [c.id for c in lst[:10]], "top_case": case_row(lst[0]),
            "evidence": {"sources": [s for c in lst[:3] for s in (c.evidence or {}).get("sources", [])][:5],
                         "information_used": ["Dossiers détectés", "Zones commerciales publiques", "Indices de priorité"],
                         "observations": len(lst)},
            "product_id": lst[0].product_id,
        })
    step(None)
    if recs:
        text = ("Selon les données disponibles, " + ("la priorité la plus élevée concerne la catégorie « " + recs[0]["category"] + " »"
                + (f" dans la zone de {recs[0]['zone']}" if recs[0]["zone"] != NA else "") + ". ")
                + "Ces recommandations reposent uniquement sur les dossiers détectés, leur fréquence et leur localisation ; "
                  "elles désignent des priorités de vérification, pas des conclusions.")
    else:
        text = "Aucun dossier ouvert : aucune priorité de contrôle ne ressort des données disponibles."
    return {"recommendations": recs, "text": text, "generated_at": datetime.utcnow().strftime("%d/%m/%Y %H:%M"),
            "entry_points_connected": has_decl}


# ============================================================ DOSSIERS TRANSMIS (vue Douane)
def transfers(db: Session) -> list[dict]:
    out = []
    for t in db.query(CaseTransfer).order_by(CaseTransfer.transferred_at.desc()):
        c = db.get(Case, t.case_id)
        if not c:
            continue
        out.append({"id": t.id, "case_id": c.id, "ref": c.case_ref, "product": c.product, "category": c.category,
                    "transferred_at": t.transferred_at.isoformat(), "motif": t.motif, "comment": t.comment,
                    "finance_status": FIN_STATUS_FR.get(t.status, t.status), "received_at": t.received_at.isoformat() if t.received_at else None,
                    "processed_at": t.processed_at.isoformat() if t.processed_at else None, "priority_score": c.priority_score,
                    "classification": CLASS_FR.get(c.classification)})
    return out


# ============================================================ helpers
def _stepper(emit):
    state = {"cur": None}

    def step(label):
        if state["cur"]:
            emit({"type": "step", "key": state["cur"], "label": state["cur"], "status": "done"})
        state["cur"] = label
        if label:
            emit({"type": "step", "key": label, "label": label, "status": "running"})
    return step


# ============================================================ ANALYSE DES DONNÉES (bouton principal)
def run_analysis(db: Session, emit) -> dict:
    """Each visible step executes the corresponding computations on the data actually present."""
    import traceback

    from ..ml import anomaly, clustering, fragmentation, matching, network, risk
    from ..models import PipelineRun
    from . import advisor as adv
    from . import analytics
    from .cases import build_cases

    t0 = datetime.utcnow()
    plan = [
        ("Analyse des opérations", [anomaly.detect_chapter_anomalies, anomaly.detect_unit_value_anomalies]),
        ("Analyse des produits", [matching.match_observations_to_products]),
        ("Recherche de regroupements", [fragmentation.detect_fragmentation, clustering.geo_clusters]),
        ("Analyse du commerce numérique", [matching.group_observations]),
        ("Analyse géographique", [fragmentation.detect_entry_anomalies, fragmentation.detect_mode_shifts, network.analyze_network]),
        ("Recherche des anomalies", [fragmentation.detect_declared_values, risk.compute_risk, analytics.generate_alerts]),
        ("Calcul des priorités", [adv.compute_priorities, build_cases]),
    ]
    partial = []
    result = None
    for label, fns in plan:
        emit({"type": "step", "key": label, "label": label, "status": "running"})
        for fn in fns:
            try:
                r = fn(db)
                db.flush()
                if fn is build_cases:
                    result = r
            except Exception:
                db.rollback()
                traceback.print_exc()
                partial.append(label)
        db.commit()
        emit({"type": "step", "key": label, "label": label, "status": "done"})
    db.add(PipelineRun(started_at=t0, finished_at=datetime.utcnow(), status="DONE", log=[f"analyse Douane : {result}"]))
    db.commit()
    return {"summary": result, "overview": overview(db), "incomplete_steps": partial,
            "duration": round((datetime.utcnow() - t0).total_seconds(), 1)}
