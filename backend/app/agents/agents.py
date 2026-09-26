"""Agents. Each agent computes from the data of the current store and returns an AgentResult.

AgentResult: agent_name, status, confidence, findings, evidence, sources, warnings, execution_time.
`label` is the business wording shown to users (no technical names).
"""
from __future__ import annotations

import time
from collections import Counter
from dataclasses import asdict, dataclass, field
from typing import Any, Callable

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..ml import matching
from ..ml.entry import INSUFFICIENT_FR, entry_analysis
from ..models import (Anomaly, CommerceObservation, CustomsImport, EntryPoint, FragmentationPattern, Product, Seller)
from ..services import advisor, queries

MODE_FR = {"SEA": "voie maritime", "AIR": "voie aérienne", "LAND": "voie terrestre"}


@dataclass
class AgentResult:
    agent_name: str
    label: str = ""
    status: str = "OK"
    confidence: float | None = None
    findings: list[str] = field(default_factory=list)
    evidence: dict[str, Any] = field(default_factory=dict)
    sources: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    execution_time: float = 0.0

    def dict(self):
        return asdict(self)


def agent(name: str, label: str):
    def deco(fn: Callable[..., AgentResult]):
        def run(*a, **k) -> AgentResult:
            t = time.time()
            try:
                r = fn(*a, **k)
            except Exception as e:  # an agent failure never breaks the investigation
                r = AgentResult(name, status="ERROR", warnings=["Analyse momentanément indisponible"],
                                evidence={"error": e.__class__.__name__})
            r.agent_name, r.label = name, label
            r.execution_time = round(time.time() - t, 3)
            return r
        run.agent_name, run.label = name, label
        return run
    return deco


def _usd(v):
    return f"{v/1e6:,.1f} M USD".replace(",", " ") if v is not None else "N/D"


@agent("Product Intelligence Agent", "Identification du produit")
def product_intelligence(db: Session, text: str) -> AgentResult:
    p, s = matching.match_question_to_product(db, text)
    if not p or s < 0.30:
        return AgentResult("", status="INSUFFICIENT_DATA", confidence=s, warnings=["Aucun produit suivi ne correspond à la question."])
    return AgentResult("", confidence=round(s, 2), findings=[f"Produit identifié : {p.short_name} (position SH {p.id}, {p.category})"],
                       evidence={"product_id": p.id, "product": p.short_name, "category": p.category}, sources=["Nomenclature du Système harmonisé"])


@agent("HS Classification Agent", "Recherche du classement tarifaire")
def hs_classification(db: Session, text: str) -> AgentResult:
    sug = matching.suggest_hs(db, text)
    if not sug:
        return AgentResult("", status="INSUFFICIENT_DATA")
    return AgentResult("", confidence=sug[0]["similarity"],
                       findings=[f"Position SH suggérée : {sug[0]['hs_code']} — suggestion IA, validation douanière requise"],
                       evidence={"suggestions": sug}, sources=["Nomenclature du Système harmonisé"])


@agent("Commerce Discovery Agent", "Analyse du commerce numérique")
def commerce_discovery(db: Session, window: str = "all", category: str | None = None) -> AgentResult:
    top = queries.top_observed_products(db, window)
    items = [i for i in top["items"] if not category or i["category"] == category]
    if not items:
        return AgentResult("", status="INSUFFICIENT_DATA", warnings=["Aucune observation commerciale sur cette période."])
    f = [f"{i['product']} : {i['observations']} observations, {i['unique_sellers']} vendeur(s)/page(s), plateformes : {', '.join(i['platforms'])}"
         for i in items[:4]]
    return AgentResult("", status="OK", confidence=0.6, findings=f, evidence={"top": items[:10], "window": window},
                       sources=sorted({p for i in items for p in i["platforms"]}), warnings=["Observation ≠ vente"])


@agent("Seller Intelligence Agent", "Analyse des vendeurs")
def seller_intelligence(db: Session, category: str | None) -> AgentResult:
    q = db.query(Seller)
    if category:
        q = q.filter(Seller.category == category)
    n = q.count()
    govs = Counter(s.governorate for s in q if s.governorate).most_common(3)
    return AgentResult("", status="OK" if n else "INSUFFICIENT_DATA", confidence=0.8,
                       findings=[f"{n} commerce(s) ou vendeur(s) observé(s)" + (f" — zones principales : {', '.join(g for g, _ in govs)}" if govs else "")],
                       evidence={"count": n, "governorates": dict(govs)}, sources=["Localisations commerciales publiques"])


@agent("Business Verification Agent", "Vérification des entreprises")
def business_verification(db: Session) -> AgentResult:
    b = queries.businesses(db)
    if not b["businesses_loaded"]:
        return AgentResult("", status="ACCESS_REQUIRED", findings=["Formalisation non vérifiable : registre des entreprises non connecté."])
    return AgentResult("", findings=[f"{k} : {v}" for k, v in b["verification_counts"].items()], evidence=b, sources=["Registre des entreprises"])


@agent("Location Intelligence Agent", "Analyse géographique")
def location_intelligence(db: Session, category: str | None = None) -> AgentResult:
    from ..models import Cluster
    cl = db.query(Cluster).filter(Cluster.kind == "GEO_COMMERCIAL").order_by(Cluster.size.desc()).all()
    if category:
        cl = [c for c in cl if category in (c.summary or {}).get("categories", {})]
    return AgentResult("", status="OK" if cl else "INSUFFICIENT_DATA", confidence=0.75,
                       findings=[f"{c.label} : {c.size} commerces regroupés" for c in cl[:3]],
                       evidence={"clusters": [{"label": c.label, "size": c.size} for c in cl[:8]]}, sources=["Localisations commerciales publiques"])


@agent("Customs Matching Agent", "Croisement avec les données douanières")
def customs_matching(db: Session, product_id: str) -> AgentResult:
    d = queries.product_360(db, product_id, "customs")["sections"]["customs"]
    o = queries.product_360(db, product_id, "origin")["sections"]["origin"]
    by = d["import_value_by_year_usd"]
    f = []
    if by:
        ys = sorted(by)
        f.append(f"Importations {ys[-1]} : {_usd(by[ys[-1]])}" + (f" ({(by[ys[-1]]/by[ys[-2]]-1)*100:+.1f} % par rapport à {ys[-2]})" if len(ys) > 1 and by[ys[-2]] else ""))
    if o["countries"]:
        f.append("Principaux pays de provenance : " + ", ".join(f"{c['country']} {c['share']*100:.0f} %" for c in o["countries"][:3] if c["share"] is not None))
        f.append(f"Continent principal : {o['top_continent']}")
    if not f:
        return AgentResult("", status="INSUFFICIENT_DATA", warnings=["Données douanières insuffisantes pour ce produit."])
    return AgentResult("", confidence=0.85, findings=f, evidence={"by_year": by, "origin": o}, sources=o.get("sources_names") or ["Statistiques douanières"])


@agent("Entry Point Intelligence Agent", "Analyse des points d'entrée")
def entry_point_intelligence(db: Session, product_id: str | None, mode: str | None = None) -> AgentResult:
    ea = entry_analysis(db, product_id)
    if not ea.get("available"):
        return AgentResult("", status="INSUFFICIENT_DATA", findings=[INSUFFICIENT_FR], evidence={"records_analyzed": ea.get("records_analyzed", 0)},
                           sources=["Référentiel officiel des points d'entrée"])
    f = [("Répartition (ensemble des produits) : " if not product_id else "Répartition : ") + ", ".join(f"{MODE_FR.get(m, m)} {v['share_value']*100:.0f} %" for m, v in ea["modes"].items())]
    f += [f"{t['name']} : {t['share']*100:.0f} % de la valeur" for t in ea["top_entry_points"][:3]]
    return AgentResult("", confidence={"HIGH": 0.9, "MEDIUM": 0.7, "LOW": 0.45}[ea["confidence"]], findings=f,
                       evidence={k: ea[k] for k in ("main_entry_mode", "modes", "top_entry_points", "records_analyzed", "period", "data_coverage")},
                       sources=["Déclarations douanières"])


@agent("Fragmentation Agent", "Recherche de fragmentation")
def fragmentation_agent(db: Session, product_id: str | None = None, window_days: int = 30) -> AgentResult:
    q = db.query(FragmentationPattern).filter(FragmentationPattern.window_days == window_days)
    if product_id:
        q = q.filter_by(hs_code=product_id)
    rows = [r for r in q.order_by(FragmentationPattern.score.desc()).all() if r.status != "NORMAL"]
    prods = {p.id: p.short_name for p in db.query(Product)}
    if not rows and not db.query(CustomsImport).count():
        return AgentResult("", status="INSUFFICIENT_DATA", findings=["Données insuffisantes : les déclarations détaillées ne sont pas connectées."])
    lab = {"MONITOR": "à surveiller", "POSSIBLE FRAGMENTATION PATTERN": "fragmentation possible"}
    return AgentResult("", confidence=0.7, findings=[f"{prods.get(r.hs_code, r.hs_code)} : {lab.get(r.status, r.status)}" for r in rows[:4]]
                       or ["Aucun schéma de fragmentation détecté sur la période."],
                       evidence={"patterns": [{"hs": r.hs_code, "status": r.status, "score": r.score, "reasons": (r.features or {}).get("reasons")} for r in rows[:6]]},
                       sources=["Déclarations douanières"])


@agent("Anomaly Agent", "Recherche de comportements inhabituels")
def anomaly_agent(db: Session, chapter: str | None = None, product_id: str | None = None, limit: int = 5) -> AgentResult:
    q = db.query(Anomaly).filter(Anomaly.is_anomaly.is_(True))
    if chapter or product_id:
        q = q.filter(Anomaly.hs_code.in_([x for x in (chapter, product_id) if x]))
    rows = q.order_by(Anomaly.period.desc(), Anomaly.score.desc()).limit(limit).all()
    if not rows:
        return AgentResult("", findings=["Aucun comportement inhabituel détecté pour ce périmètre."])
    prods = {p.id: p.short_name for p in db.query(Product)}
    f = [f"{prods.get(a.hs_code) or (a.features or {}).get('description') or 'Chapitre ' + a.hs_code} ({a.period}) : {(a.reasons or ['comportement inhabituel'])[0]}" for a in rows]
    return AgentResult("", confidence=0.65, findings=f, evidence={"anomalies": [queries.anomaly_dict(a) for a in rows]},
                       sources=sorted({queries.SOURCE_FR.get(a.source_key, "Statistiques officielles") for a in rows}),
                       warnings=["Comportement inhabituel ≠ fraude"])


@agent("Network Agent", "Analyse des relations")
def network_agent(db: Session, product_id: str) -> AgentResult:
    from ..ml.network import product_constellation
    g = product_constellation(db, product_id)
    return AgentResult("", status="OK" if g["nodes"] else "INSUFFICIENT_DATA", confidence=0.7,
                       findings=[f"Parcours commercial reconstitué : {len(g['nodes'])} éléments reliés"],
                       evidence={"size": [len(g["nodes"]), len(g["edges"])]}, sources=["Croisement des sources"])


@agent("Risk Agent", "Calcul de l'indice de priorité")
def risk_agent(db: Session, product_id: str) -> AgentResult:
    r = queries.risk_dict(db, product_id)
    if r.get("score") is None:
        return AgentResult("", status="INSUFFICIENT_DATA")
    f = [f"Indice de priorité {r['score']:.0f}/100 — couverture des données {r['data_coverage']*100:.0f} %"]
    f += [f"{w['factor']} : {w['detail']}" for w in r["why"][:3] if w["sign"] == "+"]
    return AgentResult("", confidence={"HIGH": 0.85, "MEDIUM": 0.65, "LOW": 0.45}[r["confidence"]], findings=f, evidence=r)


@agent("Customs Advisor Agent", "Génération des recommandations")
def customs_advisor(db: Session, window: str = "30d", category: str | None = None) -> AgentResult:
    fo = advisor.focus(db, window)
    pr = fo["priorities"]
    if category:
        pr = advisor.priorities_for_category(db, category, window) or pr
    if not pr:
        return AgentResult("", status="INSUFFICIENT_DATA")
    f = [f"Priorité {p['rank']} : {p['what']} — {p['action']} — {p['why'][0]}" for p in pr]
    return AgentResult("", confidence=float(sum(p["confidence"] for p in pr) / len(pr)), findings=f,
                       evidence={"priorities": pr, "changes": fo["changes"]}, sources=sorted({s for p in pr for s in p["sources"]}),
                       warnings=["Une priorité élevée signifie une priorité de vérification, jamais une preuve de fraude."])


@agent("What Changed Agent", "Analyse des évolutions")
def what_changed_agent(db: Session, window: str = "30d") -> AgentResult:
    ch = advisor.what_changed(db, window)
    if not ch.get("available"):
        return AgentResult("", status="INSUFFICIENT_DATA", findings=[ch.get("message", "")])
    f = [f"{c['subject'][:70]} : {c['change_pct']:+.0f} %" if c.get("change_pct") is not None else f"{c['subject']} : nouveau flux" for c in ch["changes"][:4]]
    return AgentResult("", confidence=0.85, findings=f or ["Aucun changement important."], evidence=ch, sources=[ch.get("source", "")])


@agent("Economic Intelligence Agent", "Analyse économique")
def economic_intelligence(db: Session) -> AgentResult:
    from ..db import session_for
    real = session_for("REAL")  # economic context is always official real data
    try:
        m = queries.economic_history(real)["monthly_ins"]
    finally:
        real.close()
    if not m:
        return AgentResult("", status="INSUFFICIENT_DATA")
    last = m[-1]
    return AgentResult("", confidence=0.9, findings=[
        f"Dernier mois publié ({last['period']}) : importations {last['imports']:,.0f} MTND, exportations {last['exports']:,.0f} MTND, taux de couverture {last['coverage_rate']*100:.1f} %".replace(",", " ")],
        evidence={"latest": last}, sources=["INS — Commerce extérieur"])


@agent("Forecast Agent", "Analyse prédictive")
def forecast_agent(db: Session) -> AgentResult:
    from ..db import session_for
    real = session_for("REAL")
    try:
        fc = queries.economic_forecast(real)
    finally:
        real.close()
    f = []
    names = {"ins_imports": "Importations", "ins_exports": "Exportations"}
    for ind, d in fc["forecasts"].items():
        y = next((a for a in d.get("annual", []) if a["year"] == 2035), None)
        if y:
            f.append(f"{names[ind]} 2035 (projection) : {y['predicted']:,.0f} MTND, intervalle {y['lower']:,.0f} – {y['upper']:,.0f}".replace(",", " "))
    return AgentResult("", status="OK" if f else "INSUFFICIENT_DATA", confidence=0.5, findings=f, sources=["INS — Commerce extérieur"],
                       warnings=["Une projection n'est pas une certitude."])
