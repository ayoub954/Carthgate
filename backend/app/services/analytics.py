"""Analytics steps (the intelligence pipeline) + the on-demand risk analysis used by the UI."""
from __future__ import annotations

import time
from collections import Counter

from sqlalchemy.orm import Session

from ..ml import anomaly, clustering, forecast, fragmentation, matching, network, risk, verification
from ..models import Alert, Anomaly, BusinessMatch, FragmentationPattern, Product, RiskScore, SellerReview
from . import advisor

# Business alert types (French labels shown to users)
ALERT_TYPES = {
    "FRAGMENTATION": "Fragmentation possible",
    "UNUSUAL_ACTIVITY": "Activité commerciale inhabituelle",
    "RECENT_INCREASE": "Hausse récente",
    "COMMERCE_CUSTOMS_GAP": "Écart commerce / douane",
    "FORMALIZATION": "Formalisation à vérifier",
    "GEO_CONCENTRATION": "Concentration géographique",
    "VALUE_CHECK": "Valeur à vérifier",
    "SMALL_FLOWS": "Multiplication des petits flux",
    "NEW_ENTRY_POINT": "Nouveau point d'entrée",
    "ENTRY_MODE_CHANGE": "Changement de mode d'entrée",
}


def generate_alerts(db: Session, log=print, window_days: int = 30) -> str:
    db.query(Alert).filter(Alert.status == "TO_REVIEW").delete()
    prods = {p.id: p for p in db.query(Product)}
    name = lambda hs: prods[hs].short_name if hs in prods else f"Chapitre {hs}"
    n = 0

    def add(kind, title, sev, period, detail, pid=None):
        nonlocal n
        db.add(Alert(kind=kind, title=title, product_id=pid, severity=sev, period=period, detail=detail))
        n += 1

    latest = db.query(Anomaly.period).filter(Anomaly.subject_type == "HS_CHAPTER_MONTH").order_by(Anomaly.period.desc()).first()
    if latest:
        for a in db.query(Anomaly).filter(Anomaly.subject_type == "HS_CHAPTER_MONTH", Anomaly.period == latest[0], Anomaly.is_anomaly.is_(True)):
            kind = "RECENT_INCREASE" if (a.features or {}).get("yoy", 0) > 0 else "UNUSUAL_ACTIVITY"
            add(kind, f"{(a.features or {}).get('description', 'Chapitre ' + a.hs_code)} (chapitre {a.hs_code})",
                "HIGH" if a.score >= 98 else "MEDIUM", a.period, {"reasons": a.reasons, "source": "INS"})
    for a in db.query(Anomaly).filter(Anomaly.subject_type == "PARTNER_HS_UNIT_VALUE", Anomaly.is_anomaly.is_(True)):
        add("VALUE_CHECK", f"{name(a.hs_code)} — provenance {a.features.get('partner')}", "MEDIUM", a.period,
            {"reasons": a.reasons, "source": "Nations unies — statistiques du commerce"}, a.hs_code)
    for a in db.query(Anomaly).filter(Anomaly.subject_type == "DECLARED_VALUE"):
        add("VALUE_CHECK", name(a.hs_code), "MEDIUM", a.period, {"reasons": a.reasons, "source": "Déclarations douanières"}, a.hs_code)
    for a in db.query(Anomaly).filter(Anomaly.subject_type == "MODE_SHIFT"):
        add("ENTRY_MODE_CHANGE", name(a.hs_code), "MEDIUM", a.period, {"reasons": a.reasons, "source": "Déclarations douanières"}, a.hs_code)
    seen_new = set()
    for a in db.query(Anomaly).filter(Anomaly.subject_type == "ENTRY", Anomaly.is_anomaly.is_(True)):
        if "Nouveau point d'entrée pour ce produit" in (a.reasons or []) and a.hs_code not in seen_new:
            seen_new.add(a.hs_code)
            add("NEW_ENTRY_POINT", name(a.hs_code), "MEDIUM", a.period, {"reasons": a.reasons, "source": "Déclarations douanières"}, a.hs_code)
    for f in db.query(FragmentationPattern).filter(FragmentationPattern.window_days == window_days, FragmentationPattern.status != "NORMAL"):
        reasons = (f.features or {}).get("reasons", [])
        if f.status.startswith("POSSIBLE"):
            add("FRAGMENTATION", name(f.hs_code), "HIGH", f.period, {"reasons": reasons, "source": "Déclarations douanières"}, f.hs_code)
        if (f.features or {}).get("low_value_ratio", 0) >= 0.6 and (f.features or {}).get("declarations", 0) >= 10:
            add("SMALL_FLOWS", name(f.hs_code), "MEDIUM", f.period, {"reasons": reasons[:2], "source": "Déclarations douanières"}, f.hs_code)
    for r in db.query(RiskScore).filter(RiskScore.score.isnot(None)):
        fc = r.factors or {}
        gap = fc.get("customs_gap", {})
        if gap.get("available") and gap["value"] >= 60:
            add("COMMERCE_CUSTOMS_GAP", name(r.product_id), "HIGH", r.period, {"reasons": [gap["detail"]], "source": gap.get("source")}, r.product_id)
        geo = fc.get("geographic_concentration", {})
        if geo.get("available") and geo["value"] >= 75:
            add("GEO_CONCENTRATION", name(r.product_id), "LOW", r.period, {"reasons": [geo["detail"]], "source": geo.get("source")}, r.product_id)
    for sr in db.query(SellerReview).filter(SellerReview.level.in_(["Prioritaire", "Élevé"])):
        if sr.formalization.startswith("Non retrouvée"):
            add("FORMALIZATION", (sr.facts or {}).get("public_name", "Vendeur"), "MEDIUM", (sr.facts or {}).get("period"),
                {"reasons": sr.reasons, "source": "Commerce observé × registre"})
        elif "Activité commerciale numérique importante" in " ".join(sr.reasons):
            add("UNUSUAL_ACTIVITY", (sr.facts or {}).get("public_name", "Vendeur"), "MEDIUM", (sr.facts or {}).get("period"),
                {"reasons": sr.reasons, "source": "Commerce observé"})
    db.flush()
    return f"{n} alerts"


def alert_dict(a: Alert) -> dict:
    return {"id": a.id, "type": ALERT_TYPES.get(a.kind, a.kind), "title": a.title, "severity": a.severity,
            "level": {"HIGH": "Élevé", "MEDIUM": "Modéré", "LOW": "Faible"}.get(a.severity, a.severity),
            "period": a.period, "reasons": (a.detail or {}).get("reasons", []), "source": (a.detail or {}).get("source"),
            "product_id": a.product_id}


STEPS = [
    ("match_countries", matching.match_ins_countries),
    ("match_products", matching.match_observations_to_products),
    ("group_observations", matching.group_observations),
    ("verify_businesses", verification.verify_businesses),
    ("anomaly_chapters", anomaly.detect_chapter_anomalies),
    ("anomaly_unit_values", anomaly.detect_unit_value_anomalies),
    ("geo_clusters", clustering.geo_clusters),
    ("fragmentation", fragmentation.detect_fragmentation),
    ("entry_anomalies", fragmentation.detect_entry_anomalies),
    ("declared_values", fragmentation.detect_declared_values),
    ("mode_shifts", fragmentation.detect_mode_shifts),
    ("network", network.analyze_network),
    ("risk", risk.compute_risk),
    ("priorities", advisor.compute_priorities),
    ("seller_review", lambda db, log=print: str(len(verification.review_sellers(db, "30d")["items"])) + " sellers reviewed"),
    ("alerts", generate_alerts),
    ("forecast", forecast.run_forecasts),
    ("cases", lambda db, log=print: str(__import__("app.services.cases", fromlist=["x"]).build_cases(db, log))),
]


def run_risk_analysis(db: Session, window: str, emit) -> dict:
    """On-demand analysis for 'Risques et alertes'. Each emitted step = a real computation."""
    days = advisor.WINDOW_DAYS.get(window, 30)
    t0 = time.time()

    def step(key, label, fn):
        emit({"type": "step", "key": key, "label": label, "status": "running"})
        out = fn()
        db.flush()
        emit({"type": "step", "key": key, "label": label, "status": "done"})
        return out

    step("data", "Analyse des données disponibles", lambda: matching.match_observations_to_products(db))
    step("anomalies", "Recherche des comportements inhabituels",
         lambda: (anomaly.detect_chapter_anomalies(db), anomaly.detect_unit_value_anomalies(db), fragmentation.detect_entry_anomalies(db)))
    step("small_flows", "Analyse des petits flux", lambda: (fragmentation.detect_fragmentation(db), fragmentation.detect_declared_values(db)))
    step("clusters", "Recherche de regroupements", lambda: clustering.geo_clusters(db))
    step("commerce", "Croisement avec le commerce numérique", lambda: matching.group_observations(db))
    step("entry", "Analyse des points d'entrée", lambda: fragmentation.detect_mode_shifts(db))
    step("business", "Vérification des entreprises", lambda: (verification.verify_businesses(db), verification.review_sellers(db, window)))
    step("priority", "Calcul des niveaux de priorité",
         lambda: (risk.compute_risk(db, window_days=days if days >= 7 else 7), advisor.compute_priorities(db, window=window)))
    step("reco", "Génération des recommandations", lambda: generate_alerts(db, window_days=days if days in (7, 30, 90) else 7))
    db.commit()
    return {"elapsed": round(time.time() - t0, 1)}
