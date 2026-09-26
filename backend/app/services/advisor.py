"""CONSEILLER IA — priority engine (max 3), recommendations, what changed, daily brief.

Pipeline: data → statistics → anomaly detection → clustering → fragmentation → risk engine →
priority engine → (AI wording) → human review. The wording layer never creates priorities.
A high priority = priority for human verification, never an accusation.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..ml.entry import entry_analysis
from ..models import (Anomaly, CustomsImport, CustomsRecord, PriorityScore, Product, Recommendation, RiskScore, Seller,
                      SellerReview)

MAX_PRIORITIES = 3
WINDOW_DAYS = {"today": 1, "7d": 7, "30d": 30, "90d": 90}
MODE_FR = {"SEA": "voie maritime", "AIR": "voie aérienne", "LAND": "voie terrestre"}
ACTIONS = {
    "REVIEW FRAGMENTATION": ("Analyser les petits flux répétés",
                             "Examiner plus attentivement les déclarations de faible valeur rapprochées dans le temps pour ce produit."),
    "CHECK DECLARED VALUE PATTERN": ("Vérifier les valeurs déclarées",
                                     "Comparer les valeurs unitaires déclarées avec les valeurs de référence avant dédouanement."),
    "REVIEW ENTRY POINT": ("Analyser le point d'entrée",
                           "Examiner l'évolution récente de ce produit au niveau du point d'entrée concerné."),
    "COMPARE ONLINE / CUSTOMS ACTIVITY": ("Comparer commerce observé et flux douaniers",
                                          "Rapprocher l'activité commerciale observée des flux déclarés sur la période."),
    "MONITOR PRODUCT": ("Surveiller le produit",
                        "Renforcer temporairement la surveillance analytique de ce produit et comparer avec la prochaine période."),
    "MONITOR COUNTRY → PRODUCT FLOW": ("Surveiller le flux pays → produit",
                                       "Suivre l'évolution du principal flux de provenance pour ce produit."),
    "MONITOR CATEGORY": ("Surveiller la catégorie",
                         "Maintenir la catégorie sous veille analytique ; aucune action immédiate n'est nécessaire."),
}


def _latest_month(db: Session) -> str | None:
    return db.query(func.max(CustomsRecord.period)).filter(CustomsRecord.dataset == "ins_chapter_month").scalar()


def _chapter_growth(db: Session, chapter: str, latest: str) -> float | None:
    y, m = latest.split("-")
    q = lambda a, b: db.query(func.sum(CustomsRecord.value)).filter(
        CustomsRecord.dataset == "ins_chapter_month", CustomsRecord.flow == "M", CustomsRecord.hs_code == chapter,
        CustomsRecord.period >= a, CustomsRecord.period <= b).scalar()
    cur, prev = q(f"{y}-01", latest), q(f"{int(y)-1}-01", f"{int(y)-1}-{m}")
    return (cur / prev - 1) if cur and prev else None


def _decl(db: Session) -> pd.DataFrame:
    rows = db.query(CustomsImport.declaration_date, CustomsImport.hs_code, CustomsImport.declared_value).all()
    return pd.DataFrame(rows, columns=["date", "hs", "value"]).assign(hs4=lambda d: d["hs"].str[:4]) if rows else pd.DataFrame()


def compute_priorities(db: Session, log=print, window: str = "30d") -> str:
    days = WINDOW_DAYS.get(window, 30)
    latest = _latest_month(db)
    risks = {r.product_id: r for r in db.query(RiskScore).all()}
    prods = {p.id: p for p in db.query(Product).filter(Product.monitored.is_(True))}
    year = db.query(func.max(CustomsRecord.period)).filter(CustomsRecord.dataset == "comtrade_hs4_partner").scalar()
    values = dict(db.query(CustomsRecord.hs_code, func.sum(CustomsRecord.value)).filter(
        CustomsRecord.dataset == "comtrade_hs4_partner", CustomsRecord.period == year).group_by(CustomsRecord.hs_code).all())
    decl = _decl(db)
    if not decl.empty:
        end = decl["date"].max()
        values = decl[decl["date"] > end - timedelta(days=days)].groupby("hs4")["value"].sum().to_dict() or values
    val_arr = np.array([v for v in values.values() if v])
    db.query(PriorityScore).delete()
    db.query(Recommendation).delete()
    cands = []
    for pid, p in prods.items():
        r = risks.get(pid)
        if not r or r.score is None or sum(1 for v in (r.factors or {}).values() if v.get("available")) < 2:
            continue  # a single signal is not enough to prioritise
        an = db.query(Anomaly).filter(Anomaly.subject_type == "HS_CHAPTER_MONTH", Anomaly.hs_code == p.chapter,
                                      Anomaly.period == latest).first() if latest else None
        dec_an = db.query(Anomaly).filter(Anomaly.hs_code == pid, Anomaly.is_anomaly.is_(True),
                                          Anomaly.subject_type.in_(["ENTRY", "DECLARED_VALUE", "MODE_SHIFT"])).order_by(Anomaly.score.desc()).first()
        anomaly_now = an.score if an else (dec_an.score if dec_an else None)
        growth = r.factors.get("temporal_change", {}).get("growth") if not latest else _chapter_growth(db, p.chapter, latest)
        exposure = float((val_arr < values.get(pid, 0)).mean() * 100) if len(val_arr) and values.get(pid) else None
        comps = {"risk_score": r.score, "anomaly_latest": anomaly_now,
                 "recent_growth": None if growth is None else float(max(0, min(100, 50 + growth * 150))),
                 "value_exposure": exposure, "data_confidence": {"HIGH": 100, "MEDIUM": 70, "LOW": 40}[r.confidence]}
        w = {"risk_score": 0.4, "anomaly_latest": 0.2, "recent_growth": 0.15, "value_exposure": 0.15}
        av = {k: v for k, v in comps.items() if k in w and v is not None}
        base = sum(v * w[k] for k, v in av.items()) / sum(w[k] for k in av)
        score = round(base * (0.8 + 0.2 * comps["data_confidence"] / 100), 1)
        db.add(PriorityScore(subject_type="PRODUCT", subject_id=pid, score=score, components=comps, window=window))
        cands.append((score, pid, p, r, an, dec_an, growth, comps))
    cands.sort(key=lambda c: -c[0])
    picked, cats = [], set()
    for c in cands:
        if c[2].category in cats and len(cands) > MAX_PRIORITIES * 2:
            continue
        picked.append(c)
        cats.add(c[2].category)
        if len(picked) == MAX_PRIORITIES:
            break
    for rank, (score, pid, p, r, an, dec_an, growth, comps) in enumerate(picked, 1):
        f = r.factors
        why, sources = [], set()
        for key in ("fragmentation", "low_value_shipments", "customs_gap", "declared_value_anomaly", "temporal_change",
                    "business_formalization", "anomaly", "geographic_concentration"):
            v = f.get(key, {})
            if v.get("available") and v.get("value", 0) >= 50 and len(why) < 3:
                why.append(v["detail"])
                sources.add(v.get("source", ""))
        if dec_an and len(why) < 3 and dec_an.reasons:
            why.append(dec_an.reasons[0])
        if growth is not None and len(why) < 3 and abs(growth) >= 0.05 and latest:
            why.append(f"Chapitre {p.chapter} : importations {growth*100:+.1f} % depuis le début de l'année")
            sources.add("INS (statistiques mensuelles)")
        if not why:
            why.append(f"Indice de priorité le plus élevé parmi les produits suivis ({score:.0f}/100)")
        if f.get("fragmentation", {}).get("available") and f["fragmentation"]["value"] >= 35:
            action = "REVIEW FRAGMENTATION"
        elif f.get("declared_value_anomaly", {}).get("available") and f["declared_value_anomaly"]["value"] >= 40:
            action = "CHECK DECLARED VALUE PATTERN"
        elif dec_an is not None and dec_an.subject_type in ("MODE_SHIFT", "ENTRY"):
            action = "REVIEW ENTRY POINT"
        elif f.get("customs_gap", {}).get("available") and f["customs_gap"]["value"] >= 50:
            action = "COMPARE ONLINE / CUSTOMS ACTIVITY"
        elif an and an.is_anomaly:
            action = "MONITOR PRODUCT"
        elif f.get("geographic_concentration", {}).get("value") and f["geographic_concentration"]["value"] >= 50:
            action = "MONITOR COUNTRY → PRODUCT FLOW"
        else:
            action = "MONITOR CATEGORY"
        ea = entry_analysis(db, pid, period_from=str((decl["date"].max() - timedelta(days=max(days, 30))).date()) if not decl.empty else None)
        if ea.get("available") and ea.get("top_entry_points"):
            tep = ea["top_entry_points"][0]
            where = f"{tep['name']} ({MODE_FR.get(tep['type'], tep['type'])}, {tep['share']*100:.0f} % de la valeur)"
        else:
            govs = Counter(s.governorate for s in db.query(Seller).filter(Seller.category == p.category) if s.governorate)
            g = govs.most_common(1)[0][0] if govs else None
            where = "Niveau national — point d'entrée non déterminable avec les données connectées" + (
                f" ; zone commerciale la plus représentée : {g}" if g else "")
        level = "Élevé" if score >= 65 else "Modéré" if score >= 45 else "Faible"
        ev = {"risk_factors": {k: v for k, v in f.items() if v.get("available")}, "priority_components": comps,
              "entry": {k: ea.get(k) for k in ("main_entry_mode", "modes", "top_entry_points", "records_analyzed", "period")} if ea.get("available") else None,
              "trend": "hausse" if (growth or 0) > 0.05 else "baisse" if (growth or 0) < -0.05 else "stable"}
        db.add(Recommendation(rank=rank, window=window, action=action, what=f"{p.short_name} — {p.category}",
                              where=where, why=why[:3], priority_score=score, risk_level=level,
                              confidence=round({"HIGH": 0.85, "MEDIUM": 0.65, "LOW": 0.45}[r.confidence], 2),
                              data_coverage=r.data_coverage, period=r.period, sources=sorted(s for s in sources if s) or ["Statistiques officielles"],
                              recommended_review=ACTIONS[action][1], product_id=pid, evidence=ev))
    db.flush()
    return f"{len(cands)} products prioritised; top {len(picked)} recommendations"


def recommendation_dict(r: Recommendation) -> dict:
    ev = r.evidence or {}
    return {"id": r.id, "rank": r.rank, "action": ACTIONS.get(r.action, (r.action,))[0], "what": r.what, "where": r.where,
            "why": r.why, "priority_score": r.priority_score, "level": r.risk_level, "confidence": r.confidence,
            "data_coverage": r.data_coverage, "period": r.period, "sources": r.sources, "trend": ev.get("trend"),
            "recommended_review": r.recommended_review, "product_id": r.product_id, "entry": ev.get("entry"),
            "evidence": ev}


# ---------------------------------------------------------------------------- CE QUI A CHANGÉ
def what_changed(db: Session, window: str = "30d") -> dict:
    decl = _decl(db)
    days = WINDOW_DAYS.get(window, 30)
    if not decl.empty:
        end = decl["date"].max()
        cur = decl[decl["date"] > end - timedelta(days=days)]
        prev = decl[(decl["date"] <= end - timedelta(days=days)) & (decl["date"] > end - timedelta(days=2 * days))]
        c, p = cur.groupby("hs4")["value"].agg(["sum", "size"]), prev.groupby("hs4")["value"].agg(["sum", "size"])
        prods = {x.id: x.short_name for x in db.query(Product)}
        changes = []
        for hs, row in c.iterrows():
            before = p.loc[hs] if hs in p.index else None
            pct = ((row["size"] / before["size"]) - 1) * 100 if before is not None and before["size"] else None
            if pct is None or abs(pct) >= 25:
                changes.append({"subject": prods.get(hs, f"SH {hs}"), "change_pct": pct, "vs": "période précédente",
                                "detail": f"{int(row['size'])} déclaration(s) contre {int(before['size']) if before is not None else 0}",
                                "value": float(row["sum"]), "metric": "nombre de déclarations"})
        changes.sort(key=lambda x: -(abs(x["change_pct"]) if x["change_pct"] is not None else 999))
        new = [{"hs": a.hs_code, "reasons": a.reasons, "score": a.score} for a in db.query(Anomaly).filter(
            Anomaly.subject_type.in_(["MODE_SHIFT", "DECLARED_VALUE", "ENTRY"]), Anomaly.is_anomaly.is_(True)).order_by(Anomaly.score.desc()).limit(5)]
        return {"window": window, "available": True, "granularity": "déclarations",
                "period": f"{(end - timedelta(days=days)).date():%d/%m/%Y} → {end.date():%d/%m/%Y}",
                "total": {"current": int(len(cur)), "previous": int(len(prev)),
                          "change_pct": ((len(cur) / len(prev)) - 1) * 100 if len(prev) else None, "label": "déclarations"},
                "changes": changes[:5], "country_flows": [], "new_anomalies": new, "source": "Déclarations douanières"}
    latest = _latest_month(db)
    if not latest:
        return {"window": window, "available": False, "changes": [], "message": "Données insuffisantes pour cette analyse."}
    note = None if window in ("30d", "90d") else ("Les statistiques officielles publiques sont mensuelles : la comparaison "
                                                   "porte sur le dernier mois publié.")
    y, m = map(int, latest.split("-"))
    prev_m = f"{y if m > 1 else y-1}-{(m-1 if m > 1 else 12):02d}"
    ly = f"{y-1}-{m:02d}"
    q = lambda per: dict(db.query(CustomsRecord.hs_code, CustomsRecord.value).filter(
        CustomsRecord.dataset == "ins_chapter_month", CustomsRecord.flow == "M", CustomsRecord.period == per).all())
    cur, prv, lyv = q(latest), q(prev_m), q(ly)
    desc = dict(db.query(CustomsRecord.hs_code, CustomsRecord.hs_description).filter(
        CustomsRecord.dataset == "ins_chapter_month", CustomsRecord.period == latest).all())
    changes = []
    for hs, v in cur.items():
        if not v or v < 20e6:
            continue
        yoy = v / lyv[hs] - 1 if lyv.get(hs) else None
        mom = v / prv[hs] - 1 if prv.get(hs) else None
        if yoy is not None and abs(yoy) >= 0.25:
            changes.append({"subject": f"Chapitre {hs} — {desc.get(hs, '')}", "change_pct": yoy * 100, "vs": f"{ly} (même mois, année précédente)",
                            "mom_pct": None if mom is None else mom * 100, "value_mtnd": v / 1e6, "metric": "valeur importée"})
    changes.sort(key=lambda c: -abs(c["change_pct"]) * c["value_mtnd"] ** 0.5)
    t_cur, t_ly = sum(cur.values()), sum(lyv.values())
    cq = lambda per: dict(db.query(CustomsRecord.partner_name, CustomsRecord.value).filter(
        CustomsRecord.dataset == "ins_country_month", CustomsRecord.flow == "M", CustomsRecord.period == per).all())
    cc, cl = cq(latest), cq(ly)
    cch = sorted([(k, v / cl[k] - 1, v) for k, v in cc.items() if cl.get(k) and v >= 50], key=lambda x: -abs(x[1]) * x[2] ** 0.5)[:3]
    unusual = db.query(Anomaly).filter(Anomaly.subject_type == "HS_CHAPTER_MONTH", Anomaly.period == latest, Anomaly.is_anomaly.is_(True)).all()
    return {"window": window, "available": True, "granularity": "mensuelle (publication officielle)", "note": note,
            "period": f"{latest} comparé à {ly}",
            "total": {"current_mtnd": t_cur / 1e6, "change_pct": (t_cur / t_ly - 1) * 100 if t_ly else None, "label": "importations (MTND)"},
            "changes": changes[:5],
            "country_flows": [{"country": k.title(), "change_pct": g * 100, "value_mtnd": v} for k, g, v in cch],
            "new_anomalies": [{"hs": a.hs_code, "reasons": a.reasons, "score": a.score} for a in unusual][:5],
            "source": "INS — Commerce extérieur aux prix courants"}


def focus(db: Session, window: str = "30d") -> dict:
    recs = db.query(Recommendation).order_by(Recommendation.rank).limit(MAX_PRIORITIES).all()
    return {"window": window, "headline": "Selon les données disponibles, concentrez votre attention sur :",
            "priorities": [recommendation_dict(r) for r in recs], "changes": what_changed(db, window)}


def value_gap(db: Session) -> dict:
    uv_all = db.query(Anomaly).filter(Anomaly.subject_type == "PARTNER_HS_UNIT_VALUE").all()
    low = [a for a in uv_all if a.features.get("uv_ratio", 1) <= 0.33]
    if low:
        gap = sum(max(0.0, (a.features["median_unit_value_usd_kg"] - a.features["unit_value_usd_kg"]) * a.features["net_weight_kg"]) for a in low)
        return {"value": gap, "unit": "USD", "label": f"Écart de valeur déclarée sur {len(low)} flux pays → produit",
                "caveat": "Montant à vérifier, pas une estimation de recettes : une valeur unitaire basse peut avoir des causes légitimes."}
    dv = db.query(Anomaly).filter(Anomaly.subject_type == "DECLARED_VALUE").all()
    if dv:
        rows = db.query(CustomsImport).all()
        gap = 0.0
        for a in dv:
            med = a.features["median_uv_hist"]
            for r in rows:
                if r.hs_code.startswith(a.hs_code) and r.quantity and r.declared_value / r.quantity < 0.5 * med:
                    gap += med * r.quantity - r.declared_value
        return {"value": gap, "unit": "TND", "label": f"Écart de valeur déclarée sur {len(dv)} produit(s)",
                "caveat": "Montant à vérifier, pas une estimation de recettes."}
    return {"value": None, "unit": None, "label": "Aucun écart de valeur détecté", "caveat": None}


def daily_brief(db: Session, window: str = "30d") -> dict:
    recs = [recommendation_dict(r) for r in db.query(Recommendation).order_by(Recommendation.rank).limit(3)]
    ch = what_changed(db, window)
    risks = db.query(RiskScore).filter(RiskScore.score.isnot(None)).order_by(RiskScore.score.desc()).all()
    prods = {p.id: p for p in db.query(Product)}
    prod_watch = prods.get(risks[0].product_id) if risks else None
    cat_scores, cat_counts = Counter(), Counter()
    for r in risks:
        cat_scores[prods[r.product_id].category] += r.score
        cat_counts[prods[r.product_id].category] += 1
    cat_watch = max(cat_scores, key=lambda c: cat_scores[c] / cat_counts[c]) if cat_scores else None
    entry = next((r["entry"] for r in recs if r.get("entry")), None)
    ep_watch = mode_watch = None
    if entry:
        ep_watch = entry["top_entry_points"][0]["name"] if entry.get("top_entry_points") else None
        mode_watch = MODE_FR.get(entry.get("main_entry_mode"), entry.get("main_entry_mode"))
    shift = db.query(Anomaly).filter(Anomaly.subject_type == "MODE_SHIFT").order_by(Anomaly.score.desc()).first()
    if shift:
        mode_watch = f"{MODE_FR.get(shift.features['mode'])} — {shift.reasons[0]}"
    uv = db.query(Anomaly).filter(Anomaly.subject_type == "PARTNER_HS_UNIT_VALUE", Anomaly.is_anomaly.is_(True)).all()
    flow = max(uv, key=lambda a: a.features["value_usd"]) if uv else None
    cov = float(np.mean([r.data_coverage for r in risks])) if risks else 0.0
    return {
        "date": datetime.utcnow().date().isoformat(), "title": "BRIEF DOUANIER IA", "window": window,
        "priorities": recs, "what_changed": ch,
        "product_to_watch": {"name": prod_watch.short_name, "score": risks[0].score, "why": risks[0].explanation[:2]} if prod_watch else None,
        "category_to_watch": cat_watch,
        "entry_mode_to_watch": mode_watch or "Non déterminable avec les données connectées",
        "entry_point_to_watch": ep_watch or "Non déterminable avec les données connectées",
        "flow_to_watch": ({"flow": f"{flow.features['partner']} → {prods.get(flow.hs_code).short_name if prods.get(flow.hs_code) else flow.hs_code}",
                           "reason": (flow.reasons or [""])[0], "period": flow.period} if flow else None),
        "revenue_to_verify": value_gap(db), "data_coverage": round(cov, 3),
    }


# backward-compatible name used elsewhere
morning_brief = daily_brief


def priorities_for_category(db: Session, category: str, window: str = "30d", limit: int = 3) -> list[dict]:
    """Top priorities restricted to one category (same engine, same scores; no new computation of evidence)."""
    days = WINDOW_DAYS.get(window, 30)
    prods = {p.id: p for p in db.query(Product).filter(Product.category == category)}
    scores = [ps for ps in db.query(PriorityScore).filter(PriorityScore.subject_id.in_(list(prods))).order_by(PriorityScore.score.desc())]
    risks = {r.product_id: r for r in db.query(RiskScore).filter(RiskScore.product_id.in_(list(prods)))}
    decl = _decl(db)
    out = []
    for rank, ps in enumerate(scores[:limit], 1):
        p, r = prods[ps.subject_id], risks.get(ps.subject_id)
        if not r:
            continue
        why = [v["detail"] for v in sorted((v for v in r.factors.values() if v.get("available") and v.get("value", 0) >= 50),
                                           key=lambda v: -v["value"] * v["weight"])][:3] or [f"Indice de priorité {ps.score:.0f}/100"]
        ea = entry_analysis(db, p.id, period_from=str((decl["date"].max() - timedelta(days=max(days, 30))).date()) if not decl.empty else None)
        growth = r.factors.get("temporal_change", {}).get("growth")
        out.append({"id": None, "rank": rank, "action": "Analyser plus en détail", "what": f"{p.short_name} — {p.category}",
                    "where": (ea["top_entry_points"][0]["name"] if ea.get("available") and ea.get("top_entry_points") else
                              "Niveau national — point d'entrée non déterminable avec les données connectées"),
                    "why": why, "priority_score": ps.score, "level": "Élevé" if ps.score >= 65 else "Modéré" if ps.score >= 45 else "Faible",
                    "confidence": {"HIGH": 0.85, "MEDIUM": 0.65, "LOW": 0.45}[r.confidence], "data_coverage": r.data_coverage,
                    "period": r.period, "sources": sorted({v.get("source", "") for v in r.factors.values() if v.get("available")} - {""}),
                    "trend": "hausse" if (growth or 0) > 0.05 else "baisse" if (growth or 0) < -0.05 else "stable",
                    "recommended_review": "Examiner plus attentivement l'évolution de ce produit sur la période récente.",
                    "product_id": p.id, "entry": {k: ea.get(k) for k in ("main_entry_mode", "modes", "top_entry_points", "records_analyzed", "period")} if ea.get("available") else None,
                    "evidence": {}})
    return out
