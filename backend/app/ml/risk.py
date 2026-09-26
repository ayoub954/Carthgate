"""Indice de priorité (0–100) per monitored product (HS heading).

A missing factor is N/A (never 0) and weights are re-normalised over available factors.
A high index = priority for HUMAN VERIFICATION, never an accusation.
Declaration-level factors are used when declaration data exists in the current store
(authorized extract).
"""
from __future__ import annotations

import math
from collections import Counter
from datetime import timedelta

import numpy as np
import pandas as pd
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..models import (Anomaly, Business, BusinessMatch, CommerceObservation, Country, CustomsImport, CustomsRecord,
                      FragmentationPattern, Product, RiskScore, Seller)

WEIGHTS = {
    "fragmentation": 20, "anomaly": 15, "online_activity": 10, "business_formalization": 10,
    "activity_consistency": 5, "geographic_concentration": 10, "low_value_shipments": 10,
    "customs_gap": 5, "declared_value_anomaly": 10, "temporal_change": 5,
}
LABELS = {
    "fragmentation": "Fragmentation possible des importations", "anomaly": "Comportement inhabituel des importations",
    "online_activity": "Présence dans le commerce observé", "business_formalization": "Formalisation des vendeurs",
    "activity_consistency": "Cohérence des activités", "geographic_concentration": "Concentration des pays fournisseurs",
    "low_value_shipments": "Petits flux de faible valeur", "customs_gap": "Écart commerce / douane",
    "declared_value_anomaly": "Valeurs déclarées à vérifier", "temporal_change": "Évolution récente des importations",
}
NA_REASON = {
    "fragmentation": "Source institutionnelle non connectée (déclarations détaillées)",
    "low_value_shipments": "Source institutionnelle non connectée (déclarations détaillées)",
    "business_formalization": "Source institutionnelle non connectée (registre des entreprises)",
    "activity_consistency": "Source institutionnelle non connectée (activités déclarées)",
    "customs_gap": "Données insuffisantes pour comparer commerce observé et flux douaniers",
}


def _growth_score(g: float | None) -> float | None:
    if g is None or math.isnan(g):
        return None
    return round(100 * (1 - math.exp(-max(g, 0) * 2)), 1)


def _decl_frame(db: Session) -> pd.DataFrame:
    rows = db.query(CustomsImport.declaration_date, CustomsImport.hs_code, CustomsImport.declared_value,
                    CustomsImport.quantity, CustomsImport.origin_iso3).all()
    return pd.DataFrame(rows, columns=["date", "hs", "value", "qty", "origin"]).assign(
        hs4=lambda d: d["hs"].str[:4]) if rows else pd.DataFrame()


def compute_risk(db: Session, log=print, window_days: int = 30) -> str:
    prods = db.query(Product).filter(Product.monitored.is_(True)).all()
    if not prods:
        return "no products"
    decl = _decl_frame(db)
    has_decl = not decl.empty
    has_rne = db.query(Business).count() > 0
    year = db.query(func.max(CustomsRecord.period)).filter(CustomsRecord.dataset == "comtrade_hs4_partner").scalar()
    prev = str(int(year) - 1) if year else None
    latest_month = db.query(func.max(Anomaly.period)).filter(Anomaly.subject_type == "HS_CHAPTER_MONTH").scalar()
    obs_counts = dict(db.query(CommerceObservation.product_id, func.count()).group_by(CommerceObservation.product_id).all())
    shop_counts = Counter(s.category for s in db.query(Seller.category).all())
    presence = {p.id: obs_counts.get(p.id, 0) + shop_counts.get(p.category, 0) / max(1, sum(1 for q in prods if q.category == p.category)) for p in prods}
    pres_vals = np.array(list(presence.values()))
    matches = {m.seller_id: m.status for m in db.query(BusinessMatch)}
    sellers = db.query(Seller).all()
    end = decl["date"].max() if has_decl else None
    db.query(RiskScore).delete()
    for p in prods:
        f: dict[str, dict] = {}
        # --- official monthly statistics (REAL store only)
        an = db.query(Anomaly).filter(Anomaly.subject_type == "HS_CHAPTER_MONTH", Anomaly.hs_code == p.chapter).order_by(
            Anomaly.period.desc()).limit(3).all()
        if an:
            top = max(an, key=lambda a: a.score)
            f["anomaly"] = {"value": top.score if top.is_anomaly else min(top.score, 60.0),
                            "detail": f"Chapitre {p.chapter}, {top.period} : " + ("; ".join(top.reasons or []) or "comportement habituel"),
                            "source": "INS (statistiques mensuelles)"}
        rows = db.query(CustomsRecord).filter(CustomsRecord.dataset == "comtrade_hs4_partner", CustomsRecord.hs_code == p.id,
                                              CustomsRecord.period == year).all() if year else []
        if rows:
            tot = sum(r.value or 0 for r in rows)
            hhi = sum(((r.value or 0) / tot) ** 2 for r in rows) if tot else None
            top_r = max(rows, key=lambda r: r.value or 0)
            if hhi is not None:
                tc = db.get(Country, top_r.partner_iso3) if top_r.partner_iso3 else None
                f["geographic_concentration"] = {"value": round(hhi * 100, 1),
                                                 "detail": f"Principal fournisseur : {(tc.name_fr or tc.name_en) if tc else top_r.partner_name} ({100*(top_r.value or 0)/tot:.0f} % en {year})",
                                                 "source": "Nations unies — statistiques du commerce"}
            uv = db.query(Anomaly).filter(Anomaly.subject_type == "PARTNER_HS_UNIT_VALUE", Anomaly.hs_code == p.id).all()
            if uv:
                low = [a for a in uv if (a.features or {}).get("uv_ratio", 1) <= 0.33]
                share_low = sum(a.features["value_usd"] for a in low) / tot if tot else 0
                gap = sum(max(0.0, (a.features["median_unit_value_usd_kg"] - a.features["unit_value_usd_kg"]) * a.features["net_weight_kg"]) for a in low)
                f["declared_value_anomaly"] = {"value": round(min(100.0, share_low * 200), 1),
                                               "detail": f"{share_low*100:.1f} % de la valeur importée déclarée à moins d'un tiers de la valeur unitaire médiane",
                                               "value_gap_usd": gap, "source": "Nations unies — statistiques du commerce"}
            prev_tot = sum(r.value or 0 for r in db.query(CustomsRecord).filter(
                CustomsRecord.dataset == "comtrade_hs4_partner", CustomsRecord.hs_code == p.id, CustomsRecord.period == prev))
            if prev_tot:
                g = tot / prev_tot - 1
                f["temporal_change"] = {"value": _growth_score(g), "detail": f"Importations {g*100:+.1f} % entre {prev} et {year}",
                                        "growth": g, "source": "Nations unies — statistiques du commerce"}
        # --- declaration-level factors
        if has_decl:
            d = decl[decl["hs4"] == p.id]
            if len(d):
                w = d[d["date"] > end - timedelta(days=window_days)]
                h = d[(d["date"] <= end - timedelta(days=window_days)) & (d["date"] > end - timedelta(days=window_days * 4))]
                if len(h):
                    rate_now, rate_before = len(w) / window_days, len(h) / (window_days * 3)
                    g = rate_now / rate_before - 1 if rate_before else 1.0
                    f["temporal_change"] = {"value": _growth_score(g), "growth": g,
                                            "detail": f"Rythme des déclarations {g*100:+.0f} % sur les {window_days} derniers jours",
                                            "source": "Déclarations douanières"}
                shares = d["origin"].value_counts(normalize=True)
                if len(shares):
                    ctry = db.get(Country, shares.index[0])
                    f["geographic_concentration"] = {"value": round(float((shares ** 2).sum()) * 100, 1),
                                                     "detail": f"Principal pays de provenance : {(ctry.name_fr or ctry.name_en) if ctry else shares.index[0]} ({shares.iloc[0]*100:.0f} %)",
                                                     "source": "Déclarations douanières"}
                dv = db.query(Anomaly).filter(Anomaly.subject_type == "DECLARED_VALUE", Anomaly.hs_code == p.id).first()
                f["declared_value_anomaly"] = {"value": dv.score if dv else 10.0,
                                               "detail": dv.reasons[0] if dv else "Valeurs déclarées conformes aux valeurs habituelles",
                                               "source": "Déclarations douanières"}
                obs_recent = sum(1 for o in db.query(CommerceObservation.observed_at).filter(CommerceObservation.product_id == p.id)
                                 if o[0] and o[0] >= end - timedelta(days=window_days))
                if obs_recent:
                    ratio = obs_recent / max(1, len(w))
                    f["customs_gap"] = {"value": round(min(100.0, 25 * ratio), 1),
                                        "detail": f"{obs_recent} observations commerciales pour {len(w)} déclaration(s) sur la période",
                                        "source": "Commerce observé × déclarations"}
            fp = db.query(FragmentationPattern).filter(FragmentationPattern.hs_code == p.id,
                                                       FragmentationPattern.window_days == window_days).first()
            if fp:
                status_fr = {"NORMAL": "Comportement habituel", "MONITOR": "Petits flux à surveiller",
                             "POSSIBLE FRAGMENTATION PATTERN": "Fragmentation possible des importations"}.get(fp.status, fp.status)
                top_reason = next(iter((fp.features or {}).get("reasons", [])), None)
                f["fragmentation"] = {"value": fp.score, "detail": status_fr + (f" : {top_reason.lower()}" if top_reason else ""),
                                      "source": "Déclarations douanières"}
                lv = (fp.features or {}).get("low_value_ratio")
                if lv is not None:
                    f["low_value_shipments"] = {"value": round(lv * 100, 1), "detail": f"{lv*100:.0f} % de déclarations de faible valeur",
                                                "source": "Déclarations douanières"}
        # --- formalization of sellers observed with this category (registry required)
        if has_rne:
            cat_sellers = [s for s in sellers if s.category == p.category and s.id in matches]
            if len(cat_sellers) >= 3:  # a rate over fewer than 3 sellers is not meaningful
                nf = sum(1 for s in cat_sellers if matches[s.id] == "NOT_FOUND") / len(cat_sellers)
                f["business_formalization"] = {"value": round(nf * 100, 1),
                                               "detail": f"{nf*100:.0f} % des vendeurs observés non retrouvés dans les données disponibles",
                                               "source": "Registre des entreprises"}
        f["online_activity"] = {"value": round(float((pres_vals < presence[p.id]).mean() * 100), 1),
                                "detail": f"{obs_counts.get(p.id, 0)} observation(s) de produits ; {shop_counts.get(p.category, 0)} commerce(s) de la catégorie",
                                "source": "Commerce observé (observation ≠ vente)"}
        factors = {}
        for k, w_ in WEIGHTS.items():
            if k in f and f[k]["value"] is not None:
                factors[k] = {**f[k], "weight": w_, "label": LABELS[k], "available": True}
            else:
                factors[k] = {"value": None, "weight": w_, "label": LABELS[k], "available": False,
                              "detail": NA_REASON.get(k, "Données insuffisantes pour cette analyse")}
        avail = {k: v for k, v in factors.items() if v["available"]}
        wsum = sum(v["weight"] for v in avail.values())
        coverage = wsum / sum(WEIGHTS.values())
        score = sum(v["value"] * v["weight"] for v in avail.values()) / wsum if wsum else None
        for v in avail.values():
            v["effective_weight"] = round(v["weight"] / wsum, 3)
        expl = sorted(avail.items(), key=lambda kv: abs(kv[1]["value"] - 50) * kv[1]["weight"], reverse=True)[:5]
        explanation = [{"sign": "+" if v["value"] >= 50 else "-", "factor": v["label"], "detail": v["detail"],
                        "value": v["value"]} for k, v in expl]
        explanation.sort(key=lambda e: (e["sign"] != "+", -abs(e["value"] - 50)))
        conf = "HIGH" if coverage >= 0.75 else "MEDIUM" if coverage >= 0.45 else "LOW"
        level = None if score is None else "HIGH" if score >= 65 else "MEDIUM" if score >= 40 else "LOW"
        per = f"statistiques annuelles {year} ; mensuelles jusqu'à {latest_month}" if year else (
            f"{(end - timedelta(days=window_days)).date():%d/%m/%Y} → {end.date():%d/%m/%Y}" if has_decl else None)
        db.add(RiskScore(product_id=p.id, score=None if score is None else round(score, 1), level=level, factors=factors,
                         explanation=explanation, data_coverage=round(coverage, 3), confidence=conf, period=per))
    db.flush()
    return f"{len(prods)} products scored (declarations: {'yes' if has_decl else 'no'}, registry: {'yes' if has_rne else 'no'})"
