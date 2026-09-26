"""VOIR LES PREUVES — sources consultées → données brutes → traitement → analyse → résultat (vocabulaire métier).

Ids: anomaly:<id> | risk:<product_id> | recommendation:<id> | forecast:<indicator> | product:<id>
"""
from __future__ import annotations

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..db import session_for
from ..models import Anomaly, CommerceObservation, CustomsImport, DataSource, Forecast, RawRecord, Recommendation, RiskScore
from .queries import SOURCE_INFO


def _source(key: str) -> dict:
    real = session_for("REAL")
    try:
        d = real.query(DataSource).filter_by(key=key).first()
        raws = real.query(func.count(RawRecord.id), func.max(RawRecord.retrieved_at)).filter(RawRecord.source_key == key).first()
    finally:
        real.close()
    name = (SOURCE_INFO.get(key) or (key,))[0]
    return {"name": name, "url": d.url if d else None, "period": d.period if d else None,
            "files": raws[0], "updated": raws[1].strftime("%d/%m/%Y") if raws[1] else None}


def _demo_block(db: Session) -> dict | None:
    return None  # single real-data store: no simulated block


def lineage(db: Session, lid: str) -> dict:
    kind, _, ident = lid.partition(":")
    demo = _demo_block(db)
    if kind == "anomaly":
        a = db.get(Anomaly, int(ident))
        if not a:
            return {"error": "not found"}
        if a.subject_type == "HS_CHAPTER_MONTH":
            chain = [{"stage": "Sources consultées", **_source("ins_trade")},
                     {"stage": "Données utilisées", "detail": "Publications mensuelles du commerce extérieur par chapitre (valeurs et poids)"},
                     {"stage": "Traitement", "detail": "Calcul des valeurs mensuelles, évolution sur un an et par rapport aux 3 mois précédents, valeur unitaire"},
                     {"stage": "Analyse", "detail": "Analyse des anomalies par intelligence artificielle"}]
        elif a.subject_type == "PARTNER_HS_UNIT_VALUE":
            chain = [{"stage": "Sources consultées", **_source("un_comtrade")},
                     {"stage": "Données utilisées", "detail": "Importations tunisiennes par produit et par pays (valeur, poids net)"},
                     {"stage": "Traitement", "detail": "Valeur unitaire comparée à la médiane des autres pays fournisseurs"},
                     {"stage": "Analyse", "detail": "Analyse des anomalies par intelligence artificielle"}]
        else:
            chain = [demo or {"stage": "Sources consultées", "name": "Déclarations douanières détaillées"},
                     {"stage": "Traitement", "detail": "Regroupement par produit, point d'entrée et période"},
                     {"stage": "Analyse", "detail": "Recherche de comportements inhabituels"}]
        chain.append({"stage": "Résultat", "detail": f"{a.period} — {'comportement inhabituel' if a.is_anomaly else 'comportement habituel'}", "why": a.reasons})
        return {"id": lid, "chain": chain}
    if kind in ("risk", "product"):
        r = db.query(RiskScore).filter_by(product_id=ident).first()
        if not r:
            return {"error": "not found"}
        srcs = sorted({v.get("source", "") for v in (r.factors or {}).values() if v.get("available")})
        chain = [demo] if demo else [{"stage": "Sources consultées", **_source(k)} for k in ("ins_trade", "un_comtrade", "osm_shops", "open_facts")]
        chain += [{"stage": "Données utilisées", "detail": " · ".join(s for s in srcs if s)},
                  {"stage": "Traitement", "detail": "Chaque indicateur est ramené sur une échelle de 0 à 100 ; les indicateurs sans données sont exclus (et non comptés à zéro)"},
                  {"stage": "Analyse", "detail": "Croisement des indicateurs par intelligence artificielle"},
                  {"stage": "Résultat", "detail": f"Indice de priorité {r.score:.0f}/100 — couverture des données {r.data_coverage*100:.0f} %",
                   "why": [f"{w['factor']} : {w['detail']}" for w in (r.explanation or [])]}]
        return {"id": lid, "chain": chain}
    if kind == "recommendation":
        rec = db.get(Recommendation, int(ident))
        if not rec:
            return {"error": "not found"}
        chain = [demo] if demo else [{"stage": "Sources consultées", "name": " · ".join(rec.sources)}]
        chain += [{"stage": "Traitement", "detail": "Analyse statistique, recherche d'anomalies, regroupements, petits flux"},
                  {"stage": "Analyse", "detail": "Calcul de l'indice de priorité et hiérarchisation (3 priorités maximum)"},
                  {"stage": "Résultat", "detail": f"Priorité {rec.rank} : {rec.what}", "why": rec.why}]
        return {"id": lid, "chain": chain}
    if kind == "forecast":
        f = db.query(Forecast).filter_by(indicator=ident).first()
        if not f:
            return {"error": "not found"}
        return {"id": lid, "chain": [
            {"stage": "Sources consultées", **_source("ins_trade")},
            {"stage": "Données utilisées", "detail": f"Série mensuelle officielle {(f.metrics or {}).get('train_period', '')}"},
            {"stage": "Analyse", "detail": "Analyse prédictive : plusieurs méthodes comparées sur le passé, la plus précise est retenue"},
            {"stage": "Résultat", "detail": "Projection annuelle jusqu'en 2035 avec intervalle d'incertitude"}]}
    return {"error": "unknown id"}
