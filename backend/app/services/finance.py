"""ESPACE FINANCE — works only on dossiers actually transmitted by the Douane.

Finance never reads Douane-internal tools (online observations, sellers, control map, advisor). What Finance
receives is the snapshot frozen at transfer time: synthesis, products, operations, available values,
charts data, sources and the AI analysis.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timedelta

import numpy as np
from sqlalchemy.orm import Session

from ..models import Case, CaseEvent, CaseTransfer, Notification
from .cases import CLASS_FR, FIN_STATUS_FR, _n

NA = "Information non disponible"
FIN_FLOW = {"TRANSMIS": ["RECU"], "RECU": ["EN_ANALYSE"], "EN_ANALYSE": ["TRAITE"], "TRAITE": []}
GRAN = {"day": "Jour", "week": "Semaine", "month": "Mois", "year": "Année"}


def snapshot(c: Case, transfer_motif: str, comment: str | None) -> dict:
    """What Finance receives (frozen at transfer time)."""
    ev = c.evidence or {}
    return {"ref": c.case_ref, "product": c.product, "product_id": c.product_id, "category": c.category, "period": c.period,
            "motif": c.motif, "kind": c.kind, "explanation": c.explanation, "classification": CLASS_FR.get(c.classification),
            "priority_score": c.priority_score, "confidence": c.confidence, "zone": c.geographic_zone, "country": c.country,
            "continent": c.continent, "entry_points": [e.get("name") for e in (c.entry_points or [])],
            "operations": [{k: o.get(k) for k in ("date", "label", "value", "unit", "quantity", "quantity_unit", "country", "entry_point", "mode")}
                           for o in (c.operations or [])],
            "value_concerned": c.value_concerned, "gap_to_verify": c.gap_to_verify, "amount_unit": c.amount_unit,
            "indicators": [{"label": i.get("label"), "relation": i.get("relation"), "source": i.get("source")}
                           for i in (c.risk_indicators or []) if i.get("source") != "Commerce observé"],
            "sources": ev.get("sources", []), "information_used": ev.get("information_used", []), "method": ev.get("method"),
            "transfer_motif": transfer_motif, "agent_comment": comment}


def _rows(db: Session, f: dict | None = None) -> list[tuple[CaseTransfer, dict]]:
    f = {k: v for k, v in (f or {}).items() if v}
    out = []
    for t in db.query(CaseTransfer).filter(CaseTransfer.receiver_institution == "FINANCE").order_by(CaseTransfer.transferred_at.desc()):
        s = t.snapshot or {}
        if f.get("product") and s.get("product") != f["product"]:
            continue
        if f.get("category") and s.get("category") != f["category"]:
            continue
        if f.get("zone") and s.get("zone") != f["zone"]:
            continue
        if f.get("country") and s.get("country") != f["country"]:
            continue
        if f.get("entry_point") and f["entry_point"] not in (s.get("entry_points") or []):
            continue
        if f.get("status") and t.status != f["status"]:
            continue
        out.append((t, s))
    return out


def row_dict(t: CaseTransfer, s: dict) -> dict:
    return {"transfer_id": t.id, "case_id": t.case_id, "ref": s.get("ref"), "product": s.get("product"), "category": s.get("category"),
            "zone": s.get("zone"), "country": s.get("country"), "motif": s.get("motif"), "classification": s.get("classification"),
            "priority_score": s.get("priority_score"), "value_concerned": s.get("value_concerned"), "gap_to_verify": s.get("gap_to_verify"),
            "amount_unit": s.get("amount_unit"), "status": t.status, "status_label": FIN_STATUS_FR.get(t.status, t.status),
            "transferred_at": t.transferred_at.isoformat(), "received_at": t.received_at.isoformat() if t.received_at else None,
            "processed_at": t.processed_at.isoformat() if t.processed_at else None}


def filters_available(db: Session) -> dict:
    rows = _rows(db)
    pick = lambda k: sorted({s.get(k) for _, s in rows if s.get(k)})
    return {"product": pick("product"), "category": pick("category"), "zone": pick("zone"), "country": pick("country"),
            "entry_point": sorted({e for _, s in rows for e in (s.get("entry_points") or [])}),
            "status": [{"value": k, "label": v} for k, v in FIN_STATUS_FR.items()],
            "units": sorted({s.get("amount_unit") for _, s in rows if s.get("amount_unit")})}


def _amounts(rows) -> dict:
    by = defaultdict(lambda: {"value": 0.0, "gap": 0.0, "n": 0})
    for _, s in rows:
        u = s.get("amount_unit")
        if not u:
            continue
        by[u]["value"] += s.get("value_concerned") or 0
        by[u]["gap"] += s.get("gap_to_verify") or 0
        by[u]["n"] += 1
    return dict(by)


def overview(db: Session) -> dict:
    rows = _rows(db)
    st = Counter(t.status for t, _ in rows)
    am = _amounts([r for r in rows if r[0].status != "TRAITE"])
    unread = db.query(Notification).filter(Notification.institution == "FINANCE", Notification.read_at.is_(None)).count()
    return {"kpis": [
        {"key": "received", "label": "Dossiers reçus", "value": len(rows), "detail": f"{unread} nouveau(x) non consulté(s)"},
        {"key": "to_analyse", "label": "Dossiers à analyser", "value": st.get("TRANSMIS", 0) + st.get("RECU", 0) + st.get("EN_ANALYSE", 0),
         "detail": f"{st.get('EN_ANALYSE', 0)} en cours d'analyse"},
        {"key": "amounts", "label": "Montants à vérifier", "values": [{"unit": u, "value": v["value"], "gap": v["gap"], "cases": v["n"]} for u, v in am.items()],
         "detail": "Valeur des opérations concernées par les dossiers non traités"},
        {"key": "done", "label": "Dossiers traités", "value": st.get("TRAITE", 0), "detail": "Analyse financière terminée"},
    ], "recent": [row_dict(t, s) for t, s in rows[:6]], "filters": filters_available(db)}


def _bucket(d: datetime, g: str) -> str:
    if g == "day":
        return d.strftime("%Y-%m-%d")
    if g == "week":
        return (d - timedelta(days=d.weekday())).strftime("%Y-%m-%d")
    if g == "year":
        return d.strftime("%Y")
    return d.strftime("%Y-%m")


def analytics(db: Session, granularity: str = "month", f: dict | None = None, unit: str | None = None) -> dict:
    g = granularity if granularity in GRAN else "month"
    rows = _rows(db, f)
    units = sorted({s.get("amount_unit") for _, s in rows if s.get("amount_unit")})
    unit = unit if unit in units else (Counter(s.get("amount_unit") for _, s in rows if s.get("amount_unit")).most_common(1) or [(None,)])[0][0]
    money = [(t, s) for t, s in rows if s.get("amount_unit") == unit]
    val = lambda s: s.get("value_concerned") or 0
    series_v, series_g, series_n = defaultdict(float), defaultdict(float), Counter()
    for t, s in money:
        b = _bucket(t.transferred_at, g)
        series_v[b] += val(s)
        series_g[b] += s.get("gap_to_verify") or 0
    for t, _ in rows:
        series_n[_bucket(t.transferred_at, "month")] += 1
    cat_v, zone_n, zone_v, ep_n, country_v, cont_v, prod_v = Counter(), Counter(), Counter(), Counter(), Counter(), Counter(), Counter()
    matrix = defaultdict(Counter)
    for t, s in money:
        cat_v[s.get("category") or NA] += val(s)
        zone_v[s.get("zone") or NA] += val(s)
        country_v[s.get("country") or NA] += val(s)
        cont_v[s.get("continent") or NA] += val(s)
        prod_v[s.get("product") or NA] += val(s)
        matrix[s.get("category") or NA][s.get("classification") or NA] += val(s)
    for t, s in rows:
        zone_n[s.get("zone") or NA] += 1
        for e in (s.get("entry_points") or [NA]):
            ep_n[e] += 1
    prio = Counter(s.get("classification") or NA for _, s in rows)
    stat = Counter(FIN_STATUS_FR.get(t.status, t.status) for t, _ in rows)
    lst = lambda c, n=12: [{"label": k, "value": v} for k, v in c.most_common(n)]
    ts = lambda d: [{"label": k, "value": round(v, 2)} for k, v in sorted(d.items())]
    ep_only_na = set(ep_n) <= {NA}
    return {
        "granularity": g, "unit": unit, "units": units, "total": len(rows), "filters": filters_available(db),
        "charts": {
            "amounts_time": {"rows": ts(series_v), "unit": unit, "kind": "time"},
            "categories": {"rows": lst(cat_v), "unit": unit, "kind": "category"},
            "zones": {"rows": lst(zone_n), "unit": "dossiers", "kind": "category", "values": lst(zone_v)},
            "monthly": {"rows": ts(series_n), "unit": "dossiers", "kind": "time"},
            "entry_points": {"rows": [] if ep_only_na else lst(ep_n), "unit": "dossiers", "kind": "category",
                             "message": "Les dossiers transmis ne comportent pas de point d'entrée : les statistiques officielles publiques ne l'indiquent pas." if ep_only_na and rows else None},
            "origins": {"rows": lst(country_v), "unit": unit, "kind": "category", "continents": lst(cont_v)},
            "priority": {"rows": [{"label": k, "value": prio.get(k, 0)} for k in ("Prioritaire", "Anomalie à vérifier") if k in prio] +
                                 [{"label": k, "value": v} for k, v in prio.items() if k not in ("Prioritaire", "Anomalie à vérifier")], "unit": "dossiers", "kind": "category"},
            "status": {"rows": [{"label": v, "value": stat.get(v, 0)} for v in FIN_STATUS_FR.values()], "unit": "dossiers", "kind": "category"},
            "category_amount": {"rows": [{"category": k, **dict(v)} for k, v in matrix.items()], "levels": sorted({l for v in matrix.values() for l in v}),
                                "unit": unit, "kind": "matrix"},
            "gaps_time": {"rows": ts(series_g), "unit": unit, "kind": "time"},
            "products": {"rows": lst(prod_v, 10), "unit": unit, "kind": "category"},
        },
        "forecast": forecast(ts(series_v), g, unit),
    }


def forecast(series: list[dict], g: str, unit: str | None) -> dict:
    """Indicative trend projection of the amounts to verify. Refused when the history is too short."""
    if len(series) < 6:
        return {"available": False, "message": f"Prévision non calculée : au moins 6 périodes d'historique sont nécessaires "
                                                 f"({len(series)} disponible(s)). Aucune projection n'est inventée."}
    y = np.array([p["value"] for p in series], dtype=float)
    x = np.arange(len(y))
    a, b = np.polyfit(x, y, 1)
    resid = y - (a * x + b)
    sd = float(resid.std(ddof=1)) if len(y) > 2 else 0.0
    out = []
    for k in range(1, 4):
        v = max(0.0, a * (len(y) - 1 + k) + b)
        out.append({"step": k, "value": v, "low": max(0.0, v - 1.28 * sd), "high": v + 1.28 * sd})
    return {"available": True, "unit": unit, "slope": a, "points": out,
            "message": "Projection indicative (tendance linéaire, intervalle à 80 %) : une projection n'est pas une certitude."}


def analysis(db: Session, emit, f: dict | None = None, granularity: str = "month", unit: str | None = None) -> dict:
    from .douane import _stepper
    step = _stepper(emit)
    step("Lecture des dossiers transmis")
    a = analytics(db, granularity, f, unit)
    rows = _rows(db, f)
    step("Analyse des montants")
    ch = a["charts"]
    u = a["unit"] or ""
    total_v = sum(r["value"] for r in ch["categories"]["rows"])
    step("Recherche des concentrations")
    sections = {}
    if not rows:
        step(None)
        return {"sections": {"Synthèse": ["Aucun dossier transmis ne correspond à la sélection : aucune analyse ne peut être produite."]},
                "priorities": [], "analytics": a}
    st = Counter(t.status for t, _ in rows)
    sections["Synthèse"] = [
        f"{len(rows)} dossier(s) transmis par la Douane correspondent à la sélection, dont {st.get('TRAITE', 0)} traité(s).",
        f"Valeur totale des opérations concernées : {_n(total_v / 1e6, 2)} M {u}." if total_v else "Aucun montant disponible pour cette unité.",
    ]
    gaps = sum(r["value"] for r in ch["gaps_time"]["rows"])
    if gaps:
        sections["Synthèse"].append(f"Écarts potentiels à vérifier : {_n(gaps / 1e6, 2)} M {u} (estimation à vérifier, pas un montant dû).")
    conc = []
    if ch["categories"]["rows"] and total_v:
        top = ch["categories"]["rows"][0]
        conc.append(f"La catégorie « {top['label']} » concentre {top['value'] / total_v * 100:.0f} % des montants de la période sélectionnée.")
    if ch["origins"]["rows"] and total_v:
        top = ch["origins"]["rows"][0]
        conc.append(f"Le pays d'origine le plus représenté est {top['label']} ({top['value'] / total_v * 100:.0f} % des montants).")
    if ch["zones"]["rows"]:
        top = ch["zones"]["rows"][0]
        conc.append(f"La zone la plus fréquente est {top['label']} ({top['value']} dossier(s)).")
    sections["Concentrations"] = conc or ["Aucune concentration significative."]
    step("Analyse des évolutions")
    tv = ch["amounts_time"]["rows"]
    if len(tv) >= 2:
        d = tv[-1]["value"] - tv[-2]["value"]
        sections["Évolutions"] = [f"Entre {tv[-2]['label']} et {tv[-1]['label']}, les montants à vérifier ont {'augmenté' if d > 0 else 'diminué'} "
                                  f"de {_n(abs(d) / 1e6, 2)} M {u}."]
    else:
        sections["Évolutions"] = ["Une seule période de transmission est disponible : l'évolution n'est pas encore mesurable."]
    fc = a["forecast"]
    sections["Tendances"] = [fc["message"]] if not fc["available"] else [
        f"La tendance {'haussière' if fc['slope'] > 0 else 'baissière'} projette {_n(fc['points'][0]['value'] / 1e6, 2)} M {u} "
        f"pour la période suivante (entre {_n(fc['points'][0]['low'] / 1e6, 2)} et {_n(fc['points'][0]['high'] / 1e6, 2)}).", fc["message"]]
    step("Sélection des dossiers prioritaires")
    open_rows = [(t, s) for t, s in rows if t.status != "TRAITE"]
    open_rows.sort(key=lambda r: (-(r[1].get("priority_score") or 0), -(r[1].get("value_concerned") or 0)))
    prios = [row_dict(t, s) for t, s in open_rows[:3]]
    sections["Points importants"] = [
        "Les montants correspondent à la valeur des opérations concernées ; ils ne constituent ni une créance ni une estimation de recettes.",
        "Les dossiers en dollars (statistiques internationales) et en dinars (déclarations) sont analysés séparément, sans conversion.",
    ]
    sections["Explication des graphiques"] = [
        "Évolution des montants : valeur cumulée des dossiers reçus par période de transmission.",
        "Répartition par catégorie : où se concentrent les montants ; une barre dominante signale une concentration.",
        "Niveaux de priorité : combien de dossiers sont « Prioritaires » par rapport aux « Anomalies à vérifier ».",
    ]
    step("Rédaction de l'analyse")
    from ..llm.explain import explain
    facts = {"agents": [{"agent_name": k, "status": "OK", "findings": v, "warnings": []} for k, v in sections.items()], "cards": []}
    llm = explain("Rédige une synthèse financière courte des dossiers transmis, à partir des faits.", facts)
    step(None)
    return {"sections": sections, "priorities": prios, "narrative": llm["text"] if llm.get("llm") else None, "analytics": a}


def case_detail(db: Session, case_id: int) -> dict | None:
    t = db.query(CaseTransfer).filter(CaseTransfer.case_id == case_id, CaseTransfer.receiver_institution == "FINANCE").order_by(CaseTransfer.id.desc()).first()
    if not t:
        return None
    events = db.query(CaseEvent).filter(CaseEvent.case_id == case_id, CaseEvent.visibility.in_(["ALL", "FINANCE"])).order_by(CaseEvent.at).all()
    return {**row_dict(t, t.snapshot or {}), "snapshot": t.snapshot, "finance_comment": t.finance_comment,
            "next_status": [{"value": s, "label": FIN_STATUS_FR[s]} for s in FIN_FLOW.get(t.status, [])],
            "history": [{"at": e.at.isoformat(), "actor": e.actor, "institution": e.institution, "action": e.action, "detail": e.detail} for e in events]}


def set_status(db: Session, user, case_id: int, status: str, comment: str | None) -> dict:
    from ..auth import display_name
    t = db.query(CaseTransfer).filter(CaseTransfer.case_id == case_id, CaseTransfer.receiver_institution == "FINANCE").order_by(CaseTransfer.id.desc()).first()
    if not t:
        raise LookupError
    if status not in FIN_FLOW.get(t.status, []):
        raise ValueError("Changement de statut non autorisé.")
    now = datetime.utcnow()
    t.status = status
    if status == "RECU":
        t.received_at, t.received_by = now, user.id
    if status == "TRAITE":
        t.processed_at = now
    if comment:
        t.finance_comment = comment[:2000]
    c = db.get(Case, case_id)
    if c:
        c.finance_status, c.updated_at = status, now
    db.add(CaseEvent(case_id=case_id, user_id=user.id, actor=display_name(user), institution="FINANCE", action=f"Statut Finance : {FIN_STATUS_FR[status]}",
                     detail=None, visibility="ALL"))
    if comment:
        db.add(CaseEvent(case_id=case_id, user_id=user.id, actor=display_name(user), institution="FINANCE", action="Note d'analyse financière",
                         detail=comment[:2000], visibility="FINANCE"))
    db.commit()
    return case_detail(db, case_id)
