"""Orchestrateur IA: question → sources → agents → computations → prioritisation → explanation.

Every progress event emitted to the UI corresponds to an agent actually executing.
Intent detection: AI intent extraction when available, otherwise transparent keyword rules.
The wording layer only explains computed agent results; it never produces figures.
"""
from __future__ import annotations

import re
import time
from collections import Counter

from sqlalchemy.orm import Session

from ..llm import explain as llm_explain
from ..ml.entry import entry_analysis
from ..models import AgentRun, CommerceObservation, CustomsImport, CustomsRecord, Product, Seller
from ..services import advisor, queries
from . import agents as A

INTENTS = ["top_observed_products", "compare_online_customs", "entry_mode", "fragmentation", "anomalies",
           "country_supply", "focus_priorities", "what_changed", "economic_outlook", "product_path",
           "hs_classification", "product_overview", "sellers"]
SCHEMA = f"""Return JSON: {{"intents": [subset of {INTENTS}], "product_text": string|null, "category": string|null,
"window": "today"|"7d"|"30d"|"90d"|null}}"""
RULES = [
    ("focus_priorities", r"concentr|focus|priorit|surveill|attention|devrait|nécessit|necessit|cette semaine|aujourd"),
    ("what_changed", r"chang|évolu|evolu|hausse|augment|derniers jours"),
    ("entry_mode", r"par où|par quel|entrent|entrée|entree|port|aéroport|frontière|terrestre|maritime|aérien|flux .*(mer|air|terre)"),
    ("fragmentation", r"fragment|petits (envois|flux)|petites importations|faible valeur"),
    ("anomalies", r"anomal|inhabituel|anormal|suspect"),
    ("country_supply", r"pays|fournit|fournisseur|provenance|origine|continent"),
    ("top_observed_products", r"observ|en ligne|numérique|numerique|réseaux|facebook|instagram|tiktok|populaire|présents"),
    ("compare_online_customs", r"compar"),
    ("economic_outlook", r"économ|econom|prévision|projection|2035|perspective|croissance|balance"),
    ("product_path", r"parcours|jusqu"),
    ("hs_classification", r"code sh|nomenclature|classement tarifaire|position tarifaire"),
    ("sellers", r"vendeur|commerçant|boutique|entreprise"),
]
CATEGORY_WORDS = {"Électronique": r"électron|electron|smartphone|téléphone|ordinateur|écouteur",
                  "Cosmétiques": r"cosmét|cosmet|parfum|maquillage|crème|creme",
                  "Textile et habillement": r"vêtement|textile|habill",
                  "Chaussures": r"chaussure|basket",
                  "Bijoux et montres": r"montre|bijou"}
WINDOW_WORDS = [("today", r"aujourd"), ("7d", r"semaine|7 jours"), ("90d", r"90 jours|trimestre"), ("30d", r"30 jours|mois")]


def _rules(q: str) -> dict:
    ql = q.lower()
    intents = [i for i, pat in RULES if re.search(pat, ql)]
    cat = next((c for c, pat in CATEGORY_WORDS.items() if re.search(pat, ql)), None)
    win = next((w for w, pat in WINDOW_WORDS if re.search(pat, ql)), "30d")
    return {"intents": intents[:4] or ["product_overview"], "product_text": q, "category": cat, "window": win, "method": "rules"}


def plan(q: str) -> dict:
    llm = llm_explain.classify(q, SCHEMA)
    if llm and isinstance(llm.get("intents"), list) and llm["intents"]:
        base = _rules(q)
        return {"intents": [i for i in llm["intents"] if i in INTENTS][:4] or base["intents"],
                "product_text": llm.get("product_text") or q, "category": base["category"],
                "window": llm.get("window") or base["window"], "method": "ai"}
    return _rules(q)


def _cards(db: Session, recs: list[dict]) -> list[dict]:
    """Result cards: product, image, country, entry mode, entry point, commercial zone, trend, index, reasons."""
    out = []
    for r in recs:
        pid = r.get("product_id")
        p = db.get(Product, pid) if pid else None
        img = db.query(CommerceObservation.image_url).filter(CommerceObservation.product_id == pid,
                                                              CommerceObservation.image_url.isnot(None)).first() if pid else None
        country = None
        decl = db.query(CustomsImport.origin_iso3).filter(CustomsImport.hs_code.like(f"{pid}%")).all() if pid else []
        from ..models import Country
        if decl:
            iso = Counter(d[0] for d in decl if d[0]).most_common(1)[0][0]
            c = db.get(Country, iso)
            country = (c.name_fr or c.name_en) if c else iso
        elif pid:
            year = queries.latest_comtrade_year(db)
            top = db.query(CustomsRecord).filter(CustomsRecord.dataset == "comtrade_hs4_partner", CustomsRecord.hs_code == pid,
                                                 CustomsRecord.period == year).order_by(CustomsRecord.value.desc()).first()
            if top:
                c = db.get(Country, top.partner_iso3) if top.partner_iso3 else None
                country = (c.name_fr or c.name_en) if c else top.partner_name
        ea = r.get("entry") or {}
        zone = Counter(s.governorate for s in db.query(Seller).filter(Seller.category == (p.category if p else None)) if s.governorate).most_common(1)
        out.append({
            "rank": r["rank"], "product_id": pid, "product": p.short_name if p else r["what"], "category": p.category if p else None,
            "image_url": img[0] if img else None, "country": country,
            "entry_mode": A.MODE_FR.get(ea.get("main_entry_mode")) if ea else None,
            "entry_modes": {A.MODE_FR.get(m, m): v["share_value"] for m, v in (ea.get("modes") or {}).items()} if ea else {},
            "entry_point": (ea.get("top_entry_points") or [{}])[0].get("name") if ea else None,
            "zone": zone[0][0] if zone else None, "trend": r.get("trend"), "priority_score": r["priority_score"],
            "level": r["level"], "why": r["why"], "action": r["action"], "recommended_review": r["recommended_review"],
            "confidence": r["confidence"], "data_coverage": r["data_coverage"], "period": r["period"], "recommendation_id": r["id"],
        })
    return out


def investigate(db: Session, question: str, emit=None, mode: str = "REAL") -> dict:
    emit = emit or (lambda e: None)
    t0 = time.time()
    results: list[A.AgentResult] = []

    def run(fn, *a, **k):
        emit({"type": "step", "key": fn.agent_name, "label": fn.label, "status": "running"})
        r = fn(*a, **k)
        results.append(r)
        emit({"type": "step", "key": fn.agent_name, "label": fn.label, "status": "done",
              "summary": (r.findings or r.warnings or [""])[0][:160], "state": r.status})
        return r

    emit({"type": "step", "key": "plan", "label": "Recherche des données disponibles", "status": "running"})
    p = plan(question)
    emit({"type": "step", "key": "plan", "label": "Recherche des données disponibles", "status": "done",
          "summary": "Sources identifiées"})
    intents = set(p["intents"])
    product = None
    if intents & {"entry_mode", "country_supply", "product_path", "product_overview", "compare_online_customs", "hs_classification"}:
        r = run(A.product_intelligence, db, p.get("product_text") or question)
        if r.status == "OK":
            product = db.get(Product, r.evidence["product_id"])
    if "hs_classification" in intents:
        run(A.hs_classification, db, p.get("product_text") or question)
    if intents & {"top_observed_products", "compare_online_customs", "focus_priorities", "sellers"}:
        run(A.commerce_discovery, db, "all", p.get("category"))
    if product and intents & {"country_supply", "compare_online_customs", "product_overview", "product_path"}:
        run(A.customs_matching, db, product.id)
    if intents & {"entry_mode", "product_path", "focus_priorities"}:
        run(A.entry_point_intelligence, db, product.id if product else None)
    if intents & {"sellers", "focus_priorities"}:
        run(A.seller_intelligence, db, p.get("category"))
        run(A.business_verification, db)
    if "product_path" in intents and product:
        run(A.network_agent, db, product.id)
        run(A.location_intelligence, db, product.category)
    if intents & {"fragmentation", "focus_priorities"}:
        run(A.fragmentation_agent, db, product.id if product else None)
    if intents & {"anomalies", "focus_priorities", "what_changed"}:
        run(A.anomaly_agent, db, product.chapter if product else None, product.id if product else None)
    if product and intents & {"product_overview", "compare_online_customs"}:
        run(A.risk_agent, db, product.id)
    if intents & {"what_changed", "focus_priorities"}:
        run(A.what_changed_agent, db, p.get("window") or "30d")
    if "economic_outlook" in intents:
        run(A.economic_intelligence, db)
        run(A.forecast_agent, db)
    advice = None
    if intents & {"focus_priorities", "anomalies", "fragmentation", "compare_online_customs", "sellers"} or p.get("category"):
        advice = run(A.customs_advisor, db, p.get("window") or "30d", p.get("category"))

    cards = _cards(db, advice.evidence["priorities"]) if advice and advice.status == "OK" else []
    if product and not cards:
        rd = queries.risk_dict(db, product.id)
        ea = entry_analysis(db, product.id)
        cards = _cards(db, [{"id": None, "rank": 1, "product_id": product.id, "what": product.short_name, "priority_score": rd.get("score"),
                             "level": rd.get("level"), "why": [w["detail"] for w in rd.get("why", []) if w["sign"] == "+"][:3] or ["—"],
                             "action": "Analyser plus en détail", "recommended_review": "", "confidence": None,
                             "data_coverage": rd.get("data_coverage"), "period": rd.get("period"), "trend": None,
                             "entry": ea if ea.get("available") else None}])

    # evidence (business vocabulary)
    obs_n = db.query(CommerceObservation).count()
    links = [u for (u,) in db.query(CommerceObservation.post_url).filter(CommerceObservation.post_url.isnot(None),
                                                                         CommerceObservation.product_id == (product.id if product else None)).limit(5)]
    evidence = {
        "sources": sorted({s for r in results for s in r.sources if s}),
        "period": next((c["period"] for c in cards if c.get("period")), None),
        "observations": obs_n, "records": sum(int(r.evidence.get("records_analyzed") or 0) for r in results),
        "updated": time.strftime("%d/%m/%Y"), "data_used": [r.label for r in results if r.status in ("OK", "PARTIAL")],
        "insufficient": [r.label for r in results if r.status in ("INSUFFICIENT_DATA", "ACCESS_REQUIRED")],
        "links": links,
    }
    emit({"type": "step", "key": "write", "label": "Rédaction de la synthèse", "status": "running"})
    facts = {"question": question, "mode": "données réelles",
             "agents": [{"agent_name": r.label, "status": r.status, "findings": r.findings, "warnings": r.warnings} for r in results],
             "cards": [{k: c[k] for k in ("product", "country", "entry_mode", "entry_point", "zone", "priority_score", "why")} for c in cards],
             "evidence": evidence}
    rep = llm_explain.explain(question, facts)
    emit({"type": "step", "key": "write", "label": "Rédaction de la synthèse", "status": "done", "summary": "Analyse terminée"})
    text = rep["text"]
    for i in range(0, len(text), 24):
        emit({"type": "text", "delta": text[i:i + 24]})
    run_row = AgentRun(question=question, intent=",".join(p["intents"]), plan=p,
                       results=[r.dict() for r in results], answer=text,
                       evidence={**evidence, "cards": cards, "generated_by_ai": bool(rep.get("llm"))},
                       llm_used=rep.get("llm"), status="DONE", execution_time=round(time.time() - t0, 2))
    db.add(run_row)
    db.commit()
    return run_dict(run_row)


def run_dict(run: AgentRun) -> dict:
    ev = run.evidence or {}
    return {"id": run.id, "question": run.question, "answer": run.answer, "cards": ev.get("cards", []),
            "steps": [{"label": r.get("label"), "state": r.get("status"), "summary": (r.get("findings") or r.get("warnings") or [""])[0]}
                      for r in (run.results or [])],
            "evidence": {k: v for k, v in ev.items() if k != "cards"}, "execution_time": run.execution_time,
            "created_at": run.created_at.isoformat() if run.created_at else None}
