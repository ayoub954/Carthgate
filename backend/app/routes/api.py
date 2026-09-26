"""REST API. All AI calls happen server-side. The store (REAL / DEMO) is selected by the X-Data-Mode header.

Streaming endpoints return NDJSON events: {"type": "step"|"text"|"result"|"error", ...}; each step event is
emitted when the corresponding computation actually starts / finishes.
"""
from __future__ import annotations

import json
import queue
import threading
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Body, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, Response, StreamingResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from .. import pipeline
from ..agents.orchestrator import investigate as run_investigation, run_dict
from ..db import get_db, get_real_db, request_mode, session_for
from ..ml import matching
from ..ml.network import product_constellation, sankey
from ..ml.verification import review_dict, review_sellers
from ..models import (AgentRun, Alert, Anomaly, CustomsImport, CustomsRecord, DataSource, EntryPoint, Feedback,
                      FragmentationPattern, Recommendation, Report, SellerReview)
from ..services import advisor, analytics, economics, exports, lineage, queries, reports

router = APIRouter(prefix="/api")
WINDOW = "^(today|7d|30d|90d)$"


# ---------------------------------------------------------------- streaming helper
def stream_job(mode: str, job):
    """Run job(db, emit) in a worker thread and stream its events as NDJSON."""
    q: queue.Queue = queue.Queue()

    def worker():
        db = session_for(mode)
        try:
            res = job(db, q.put)
            q.put({"type": "result", "data": res})
        except Exception as e:  # never expose internals
            q.put({"type": "error", "message": "L'analyse n'a pas pu aboutir. Veuillez réessayer."})
            import traceback
            traceback.print_exc()
        finally:
            db.close()
            q.put(None)

    threading.Thread(target=worker, daemon=True).start()

    def gen():
        while True:
            ev = q.get()
            if ev is None:
                break
            yield json.dumps(ev, ensure_ascii=False, default=str) + "\n"

    return StreamingResponse(gen(), media_type="application/x-ndjson")


def _stream_text(emit, text: str, size: int = 22):
    for i in range(0, len(text), size):
        emit({"type": "text", "delta": text[i:i + size]})


# ---------------------------------------------------------------- mode / overview
@router.get("/mode")
def mode_info():
    demo = session_for("DEMO")
    try:
        n = demo.query(CustomsImport).count()
    finally:
        demo.close()
    return {"modes": ["REAL", "DEMO"], "demo_available": n > 0}


@router.get("/dashboard")
def dashboard(db: Session = Depends(get_db)):
    return queries.dashboard(db)


# ---------------------------------------------------------------- investigation IA
@router.post("/investigate/stream")
def investigate_stream(payload: dict = Body(...), mode: str = Depends(request_mode)):
    q = (payload.get("question") or "").strip()[:1000]
    if not q:
        raise HTTPException(400, "Question vide")
    return stream_job(mode, lambda db, emit: run_investigation(db, q, emit, mode))


@router.post("/investigate")
def investigate(payload: dict = Body(...), db: Session = Depends(get_db), mode: str = Depends(request_mode)):
    q = (payload.get("question") or "").strip()
    if not q:
        raise HTTPException(400, "Question vide")
    return run_investigation(db, q[:1000], None, mode)


@router.get("/investigate/{run_id}")
def get_investigation(run_id: int, db: Session = Depends(get_db)):
    r = db.get(AgentRun, run_id)
    if not r:
        raise HTTPException(404)
    return run_dict(r)


@router.get("/investigations")
def list_investigations(db: Session = Depends(get_db)):
    return [{"id": r.id, "question": r.question, "created_at": r.created_at.isoformat()} for r in db.query(AgentRun).order_by(AgentRun.id.desc()).limit(10)]


# ---------------------------------------------------------------- intelligence commerciale
@router.get("/products")
def products(window: str = "all", db: Session = Depends(get_db)):
    return {"top_observed": queries.top_observed_products(db, window), "monitored": queries.products_list(db), "data_mode": queries.data_mode(db)}


@router.get("/products/{pid}")
def product(pid: str, section: str | None = None, db: Session = Depends(get_db)):
    r = queries.product_360(db, pid, section)
    if r.get("error"):
        raise HTTPException(404)
    return r


@router.get("/commerce")
def commerce(window: str = "all", db: Session = Depends(get_db)):
    return queries.digital_commerce(db, window)


@router.get("/sellers")
def sellers(q: str | None = None, category: str | None = None, governorate: str | None = None, with_links: bool = False,
            limit: int = 200, db: Session = Depends(get_db)):
    return queries.sellers(db, q, category, governorate, with_links, min(limit, 2000))


@router.get("/sellers/{sid}")
def seller(sid: int, db: Session = Depends(get_db)):
    r = queries.seller_360(db, sid)
    if r.get("error"):
        raise HTTPException(404)
    return r


@router.post("/sellers/review/stream")
def sellers_review_stream(window: str = Query("30d", pattern=WINDOW), mode: str = Depends(request_mode)):
    def job(db, emit):
        steps = []

        def step(label):
            if steps:
                emit({"type": "step", "label": steps[-1], "status": "done"})
            steps.append(label)
            emit({"type": "step", "label": label, "status": "running"})
        from ..ml.verification import verify_businesses
        emit({"type": "step", "label": "Vérification de la formalisation", "status": "running"})
        verify_businesses(db)
        emit({"type": "step", "label": "Vérification de la formalisation", "status": "done"})
        res = review_sellers(db, window, emit=step)
        db.commit()
        if steps:
            emit({"type": "step", "label": steps[-1], "status": "done"})
        return res
    return stream_job(mode, job)


@router.get("/sellers-review")
def sellers_review(window: str = Query("30d", pattern=WINDOW), db: Session = Depends(get_db)):
    rows = db.query(SellerReview).filter_by(window=window).order_by(SellerReview.score.desc()).all()
    return {"available": bool(rows), "items": [review_dict(r) for r in rows]}


@router.get("/businesses")
def businesses(db: Session = Depends(get_db)):
    return queries.businesses(db)


@router.get("/countries")
def countries(db: Session = Depends(get_real_db)):
    return queries.countries(db)


@router.get("/entry-points")
def entry_points(db: Session = Depends(get_db)):
    return {"items": [{"id": e.entry_point_id, "name": e.official_name, "type": queries.ENTRY_TYPE_FR.get(e.entry_type),
                       "governorate": e.governorate, "lat": e.latitude, "lon": e.longitude, "source_url": e.source_url}
                      for e in db.query(EntryPoint).order_by(EntryPoint.entry_type, EntryPoint.official_name)]}


@router.get("/entry-analysis")
def entry_analysis_route(hs: str | None = None, db: Session = Depends(get_db)):
    return queries.entry_view(db, hs)


@router.get("/map")
def map_route(product_id: str | None = None, db: Session = Depends(get_db)):
    return queries.map_data(db, light=False, product_id=product_id)


@router.get("/network/{product_id}")
def network(product_id: str, db: Session = Depends(get_db)):
    return product_constellation(db, product_id)


@router.get("/sankey")
def sankey_route(metric: str = "value", category: str | None = None, db: Session = Depends(get_db)):
    return sankey(db, metric, category)


# ---------------------------------------------------------------- risques et alertes
def _risk_overview(db: Session, window: str) -> dict:
    recs = [advisor.recommendation_dict(r) for r in db.query(Recommendation).order_by(Recommendation.rank).limit(3)]
    alerts = [analytics.alert_dict(a) for a in db.query(Alert).order_by(Alert.severity, Alert.id)]
    reviews = [review_dict(r) for r in db.query(SellerReview).filter_by(window=window).order_by(SellerReview.score.desc()).limit(6)]
    from ..models import RiskScore, Product
    prods = {p.id: p for p in db.query(Product)}
    watch = [{"product_id": r.product_id, "product": prods[r.product_id].short_name, "category": prods[r.product_id].category,
              "score": r.score, "level": queries._level(r.score), "why": [w["detail"] for w in (r.explanation or []) if w["sign"] == "+"][:2]}
             for r in db.query(RiskScore).filter(RiskScore.score.isnot(None)).order_by(RiskScore.score.desc())
             if sum(1 for v in (r.factors or {}).values() if v.get("available")) >= 2][:5]
    eps = {}
    for r in recs:
        for t in ((r.get("entry") or {}).get("top_entry_points") or [])[:2]:
            eps.setdefault(t["name"], {"name": t["name"], "type": queries.ENTRY_TYPE_FR.get({"SEA": "SEAPORT", "AIR": "AIRPORT", "LAND": "LAND_BORDER"}.get(t["type"])),
                                       "products": [], "records": 0})
            eps[t["name"]]["products"].append(r["what"].split(" — ")[0])
            eps[t["name"]]["records"] += t["records"]
    for a in db.query(Anomaly).filter(Anomaly.subject_type == "MODE_SHIFT"):
        eps.setdefault("Changement de mode d'entrée", {"name": "Changement de mode d'entrée", "type": None, "products": [], "records": 0})
        eps["Changement de mode d'entrée"]["products"].append(prods[a.hs_code].short_name if a.hs_code in prods else a.hs_code)
    situations = len(alerts) + sum(1 for r in reviews if r["level"] in ("Prioritaire", "Élevé"))
    return {"window": window, "data_mode": queries.data_mode(db), "situations": situations, "priorities": recs, "alerts": alerts,
            "sellers": reviews, "products": watch, "entry_points": list(eps.values()), "map": queries.map_data(db, light=True),
            "changes": advisor.what_changed(db, window)}


def _recommendation_text(db: Session, ov: dict) -> str:
    from ..llm.explain import explain
    demo = ov["data_mode"] == "DEMO"
    cards = [{"product": p["what"], "priority_score": p["priority_score"], "why": p["why"],
              "entry_point": ((p.get("entry") or {}).get("top_entry_points") or [{}])[0].get("name"), "country": None} for p in ov["priorities"]]
    facts = {"mode": "données simulées de démonstration" if demo else "données réelles", "cards": cards,
             "agents": [{"agent_name": "Alertes", "status": "OK", "findings": [f"{a['type']} : {a['title']}" for a in ov["alerts"][:6]], "warnings": []},
                        {"agent_name": "Vendeurs à vérifier", "status": "OK" if ov["sellers"] else "INSUFFICIENT_DATA",
                         "findings": [f"{s['public_name']} : {s['level']}" for s in ov["sellers"][:3]], "warnings": []}]}
    return explain("Quelle recommandation donner à la Douane pour la période analysée ? Explique quoi examiner en priorité et où.", facts)["text"]


@router.post("/risk/analyze/stream")
def risk_analyze_stream(window: str = Query("30d", pattern=WINDOW), mode: str = Depends(request_mode)):
    def job(db, emit):
        analytics.run_risk_analysis(db, window, emit)
        ov = _risk_overview(db, window)
        emit({"type": "overview", "data": ov})
        emit({"type": "step", "key": "advice", "label": "Rédaction de la recommandation IA", "status": "running"})
        text = _recommendation_text(db, ov)
        emit({"type": "step", "key": "advice", "label": "Rédaction de la recommandation IA", "status": "done"})
        _stream_text(emit, text)
        return {"recommendation": text}
    return stream_job(mode, job)


@router.get("/risk/overview")
def risk_overview(window: str = Query("30d", pattern=WINDOW), db: Session = Depends(get_db)):
    return _risk_overview(db, window)


@router.get("/anomalies")
def anomalies(limit: int = 100, db: Session = Depends(get_db)):
    return {"items": [queries.anomaly_dict(a) for a in db.query(Anomaly).filter(Anomaly.is_anomaly.is_(True)).order_by(
        Anomaly.period.desc()).limit(limit)]}


@router.get("/fragmentation")
def fragmentation(db: Session = Depends(get_db)):
    rows = db.query(FragmentationPattern).order_by(FragmentationPattern.score.desc()).all()
    return {"available": bool(rows), "items": [{"hs_code": f.hs_code, "window_days": f.window_days, "state": queries.FRAG_FR.get(f.status, f.status),
                                                "reasons": (f.features or {}).get("reasons", [])} for f in rows]}


@router.get("/risk/{product_id}")
def risk(product_id: str, db: Session = Depends(get_db)):
    return queries.risk_dict(db, product_id)


@router.get("/alerts")
def alerts(db: Session = Depends(get_db)):
    return [analytics.alert_dict(a) for a in db.query(Alert).order_by(Alert.severity, Alert.id)]


@router.get("/recommendations")
def recommendations(db: Session = Depends(get_db)):
    return [advisor.recommendation_dict(r) for r in db.query(Recommendation).order_by(Recommendation.rank)]


@router.get("/focus")
def focus(window: str = Query("30d", pattern=WINDOW), db: Session = Depends(get_db)):
    return advisor.focus(db, window)


@router.get("/changes")
def changes(window: str = Query("30d", pattern=WINDOW), db: Session = Depends(get_db)):
    return advisor.what_changed(db, window)


@router.get("/morning-brief")
def morning_brief(window: str = Query("30d", pattern=WINDOW), db: Session = Depends(get_db)):
    return advisor.daily_brief(db, window)


@router.post("/brief/stream")
def brief_stream(window: str = Query("30d", pattern=WINDOW), mode: str = Depends(request_mode)):
    def job(db, emit):
        for key, label, fn in (("prio", "Analyse des priorités", lambda: advisor.compute_priorities(db, window=window)),
                               ("changes", "Analyse des évolutions", lambda: advisor.what_changed(db, window)),
                               ("value", "Recettes potentielles à vérifier", lambda: advisor.value_gap(db))):
            emit({"type": "step", "key": key, "label": label, "status": "running"})
            fn()
            emit({"type": "step", "key": key, "label": label, "status": "done"})
        db.commit()
        emit({"type": "step", "key": "brief", "label": "Rédaction du brief", "status": "running"})
        b = advisor.daily_brief(db, window)
        emit({"type": "step", "key": "brief", "label": "Rédaction du brief", "status": "done"})
        return b
    return stream_job(mode, job)


@router.post("/feedback")
def feedback(payload: dict = Body(...), db: Session = Depends(get_db)):
    verdict = payload.get("verdict")
    if verdict not in ("USEFUL", "NOT_USEFUL", "INVESTIGATE", "FALSE_POSITIVE", "WATCH"):
        raise HTTPException(400, "Avis invalide")
    fb = Feedback(target_type=payload.get("target_type", "recommendation"), target_id=str(payload.get("target_id")),
                  verdict=verdict, comment=payload.get("comment"))
    db.add(fb)
    db.commit()
    return {"ok": True, "id": fb.id}


@router.get("/watches")
def watches(db: Session = Depends(get_db)):
    return [{"id": f.id, "target": f.target_id, "comment": f.comment, "created_at": f.created_at.isoformat()}
            for f in db.query(Feedback).filter_by(verdict="WATCH").order_by(Feedback.id.desc())]


# ---------------------------------------------------------------- perspectives économiques (données réelles)
@router.get("/economic/history")
def econ_history(db: Session = Depends(get_real_db)):
    return queries.economic_history(db)


@router.get("/economic/forecast")
def econ_forecast(db: Session = Depends(get_real_db)):
    return queries.economic_forecast(db)


@router.post("/economic/scenario")
def econ_scenario(payload: dict = Body(default={}), db: Session = Depends(get_real_db)):
    return economics.run_scenario(db, payload.get("preset", "MODERATE"), payload.get("assumptions"))


@router.get("/economic/scenario/presets")
def econ_presets(db: Session = Depends(get_real_db)):
    return {"presets": economics.PRESETS, "labels": economics.SCENARIO_FR, "effective_duty_rate": economics.effective_duty_rate(db)}


@router.post("/economic/explain/stream")
def econ_explain_stream():
    def job(db, emit):
        from ..llm.explain import explain
        emit({"type": "step", "label": "Analyse de l'historique", "status": "running"})
        fc = queries.economic_forecast(db)
        emit({"type": "step", "label": "Analyse de l'historique", "status": "done"})
        names = {"ins_imports": "Importations", "ins_exports": "Exportations"}
        findings = []
        for k, v in fc["forecasts"].items():
            if v.get("available"):
                a0, a1 = v["annual"][0], v["annual"][-1]
                findings.append(f"{names[k]} : {a0['predicted']:,.0f} millions de dinars en {a0['year']} (en partie estimé), projection {a1['predicted']:,.0f} en {a1['year']} "
                                f"(intervalle {a1['lower']:,.0f} – {a1['upper']:,.0f}) ; précision mesurée sur le passé : {v['accuracy_pct']:.0f} %".replace(",", " "))
        emit({"type": "step", "label": "Rédaction de l'explication", "status": "running"})
        text = explain("Explique l'évolution projetée des importations et exportations, les facteurs historiques, "
                       "et précise qu'il s'agit d'une projection.", {"agents": [{"agent_name": "Analyse prédictive", "status": "OK",
                                                                               "findings": findings, "warnings": []}], "cards": []})["text"]
        emit({"type": "step", "label": "Rédaction de l'explication", "status": "done"})
        _stream_text(emit, text)
        return {"text": text}
    return stream_job("REAL", job)


# ---------------------------------------------------------------- sources, preuves, exports, rapports
@router.get("/sources")
def sources(db: Session = Depends(get_real_db)):
    rows = []
    for d in db.query(DataSource).all():
        info = queries.SOURCE_INFO.get(d.key)
        if info is None:
            continue
        rows.append({"key": d.key, "name": info[0], "description": info[1], "status": queries.status_fr(d.status, d.access_type),
                     "connected": d.status == "CONNECTED", "period": d.period, "records": d.records,
                     "updated": d.last_updated.strftime("%d/%m/%Y") if d.last_updated else None, "url": d.url})
    rows.sort(key=lambda r: (not r["connected"], r["name"]))
    return rows


@router.get("/data-sources")
def data_sources(db: Session = Depends(get_real_db)):
    return sources(db)


@router.get("/evidence/{lid}")
def evidence(lid: str, db: Session = Depends(get_db)):
    r = lineage.lineage(db, lid)
    if r.get("error"):
        raise HTTPException(404, "Preuves indisponibles")
    return r


@router.get("/data-lineage/{lid}")
def data_lineage(lid: str, db: Session = Depends(get_db)):
    return evidence(lid, db)


@router.get("/explorer")
def explorer(dataset: str = "customs_records", hs: str | None = None, country: str | None = None, period_from: str | None = None,
             period_to: str | None = None, governorate: str | None = None, category: str | None = None, limit: int = 300,
             db: Session = Depends(get_db)):
    df = exports.dataset_frame(db, dataset, {"hs": hs, "country": country, "period_from": period_from, "period_to": period_to,
                                             "governorate": governorate, "category": category, "limit": 100000})
    total = len(df)
    df = df.head(min(limit, 2000))
    return {"dataset": dataset, "total": total, "columns": list(df.columns), "rows": df.astype(object).where(df.notna(), None).to_dict("records")}


@router.get("/export")
def export(dataset: str = "customs_records", format: str = Query("csv", pattern="^(csv|xlsx|json)$"), hs: str | None = None,
           country: str | None = None, governorate: str | None = None, category: str | None = None, db: Session = Depends(get_db)):
    content, mime, name = exports.export(db, dataset, format, {"hs": hs, "country": country, "governorate": governorate, "category": category})
    return Response(content, media_type=mime, headers={"Content-Disposition": f'attachment; filename="{name}"'})


@router.get("/reports")
def list_reports(db: Session = Depends(get_db)):
    return [{"id": r.id, "title": r.title, "created_at": r.created_at.isoformat(), "demo": (r.meta or {}).get("demo", False)}
            for r in db.query(Report).order_by(Report.id.desc())]


@router.post("/reports/stream")
def reports_stream(window: str = Query("30d", pattern=WINDOW), mode: str = Depends(request_mode)):
    def job(db, emit):
        r = reports.generate_report(db, window, True, emit)
        return {"id": r.id, "title": r.title}
    return stream_job(mode, job)


@router.post("/reports")
def create_report(payload: dict = Body(default={}), db: Session = Depends(get_db)):
    r = reports.generate_report(db, payload.get("window", "30d"), payload.get("with_llm", True))
    return {"id": r.id, "title": r.title}


@router.get("/reports/{rid}/download")
def download_report(rid: int, inline: bool = False, db: Session = Depends(get_db)):
    r = db.get(Report, rid)
    if not r or not Path(r.path).exists():
        raise HTTPException(404)
    return FileResponse(r.path, media_type="application/pdf", filename=Path(r.path).name,
                        content_disposition_type="inline" if inline else "attachment")


# ---------------------------------------------------------------- administration (not shown in the UI)
@router.get("/models/status")
def models_status():
    from ..llm import router as ai_router
    from ..ml import embeddings
    return {"semantic": embeddings.status(), "language": ai_router.status()}


@router.get("/providers/health")
def providers_health():
    from ..providers.registry import all_providers
    out = []
    for p in all_providers():
        try:
            st = p.health()
            out.append({"key": p.key, "status": st.status, "message": st.message})
        except Exception as e:
            out.append({"key": p.key, "status": "ERROR", "message": str(e)[:200]})
    return out


@router.post("/refresh")
def refresh(payload: dict = Body(default={})):
    started = pipeline.run_in_background(providers=payload.get("providers", True), analytics_=True)
    return {"started": started}


@router.get("/refresh/status")
def refresh_status():
    labels = {"provider": "Mise à jour des sources", "analytics": "Analyse des données"}
    step = pipeline.STATE.get("step") or ""
    return {"running": pipeline.STATE["running"], "step": labels.get(step.split(":")[0]) if step else None}


@router.post("/customs/import")
async def customs_import(file: UploadFile = File(...), mode: str = Depends(request_mode)):
    from ..providers.institutional import import_customs_extract
    content = await file.read()
    db = session_for(mode)
    try:
        res = import_customs_extract(db, content, file.filename or "extrait.csv", datetime.utcnow().strftime("lot_%Y%m%d%H%M%S"))
        db.commit()
    except ValueError as e:
        raise HTTPException(400, str(e))
    finally:
        db.close()
    return {**res}


@router.post("/hs/suggest")
def hs_suggest(payload: dict = Body(...), db: Session = Depends(get_db)):
    text = " ".join(filter(None, [payload.get("product"), payload.get("description"), payload.get("brand"), payload.get("category")]))
    return {"suggestions": matching.suggest_hs(db, text)}


@router.get("/meta")
def meta(db: Session = Depends(get_real_db)):
    latest = db.query(func.max(CustomsRecord.period)).filter(CustomsRecord.dataset == "ins_chapter_month").scalar()
    return {"latest_month": latest}
