"""/api/finance/* — reserved to ROLE_FINANCE. Finance only reads dossiers actually transmitted by the Douane."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Body, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from ..auth import ROLE_FINANCE, display_name, require_role
from ..db import get_db
from ..models import CaseEvent, CaseTransfer, Notification, Report, User
from ..services import finance as F
from ..services import reports
from ..services.insight import explain_rows
from ._stream import stream_job, stream_text

FINANCE = require_role(ROLE_FINANCE)
router = APIRouter(prefix="/api/finance", dependencies=[Depends(FINANCE)])


def _filters(product=None, category=None, zone=None, country=None, entry_point=None, status=None) -> dict:
    return {"product": product, "category": category, "zone": zone, "country": country, "entry_point": entry_point, "status": status}


@router.get("/overview")
def overview(db: Session = Depends(get_db)):
    return F.overview(db)


@router.get("/cases")
def cases(product: str | None = None, category: str | None = None, zone: str | None = None, country: str | None = None,
          entry_point: str | None = None, status: str | None = None, db: Session = Depends(get_db)):
    rows = F._rows(db, _filters(product, category, zone, country, entry_point, status))
    return {"items": [F.row_dict(t, s) for t, s in rows], "filters": F.filters_available(db)}


@router.get("/cases/{cid}")
def case(cid: int, user: User = Depends(FINANCE), db: Session = Depends(get_db)):
    t = db.query(CaseTransfer).filter(CaseTransfer.case_id == cid, CaseTransfer.receiver_institution == "FINANCE").order_by(CaseTransfer.id.desc()).first()
    if not t:
        raise HTTPException(404, "Dossier introuvable ou non transmis.")
    if t.status == "TRANSMIS":  # first consultation by a Finance agent = acknowledgement of receipt
        F.set_status(db, user, cid, "RECU", None)
    db.query(Notification).filter(Notification.institution == "FINANCE", Notification.case_id == cid, Notification.read_at.is_(None)).update(
        {Notification.read_at: datetime.utcnow()})
    db.commit()
    return F.case_detail(db, cid)


@router.post("/cases/{cid}/status")
def status(cid: int, payload: dict = Body(...), user: User = Depends(FINANCE), db: Session = Depends(get_db)):
    try:
        return F.set_status(db, user, cid, payload.get("status"), (payload.get("comment") or "").strip() or None)
    except LookupError:
        raise HTTPException(404, "Dossier introuvable ou non transmis.")
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/cases/{cid}/note")
def note(cid: int, payload: dict = Body(...), user: User = Depends(FINANCE), db: Session = Depends(get_db)):
    text = (payload.get("comment") or "").strip()[:2000]
    if not text or not db.query(CaseTransfer).filter_by(case_id=cid).first():
        raise HTTPException(400, "Note vide ou dossier non transmis.")
    db.add(CaseEvent(case_id=cid, user_id=user.id, actor=display_name(user), institution="FINANCE", action="Note d'analyse financière",
                     detail=text, visibility="FINANCE"))
    db.commit()
    return F.case_detail(db, cid)


@router.get("/analytics")
def analytics(granularity: str = "month", unit: str | None = None, product: str | None = None, category: str | None = None,
              zone: str | None = None, country: str | None = None, entry_point: str | None = None, status: str | None = None,
              db: Session = Depends(get_db)):
    return F.analytics(db, granularity, _filters(product, category, zone, country, entry_point, status), unit)


@router.post("/analysis/stream")
def analysis(payload: dict = Body(default={})):
    f = {k: payload.get(k) for k in ("product", "category", "zone", "country", "entry_point", "status")}
    return stream_job(lambda db, emit: F.analysis(db, emit, f, payload.get("granularity", "month"), payload.get("unit")))


@router.post("/explain-chart")
def explain_chart(payload: dict = Body(...)):
    return explain_rows(str(payload.get("title", ""))[:200], list(payload.get("rows") or [])[:200], payload.get("unit"),
                        payload.get("kind", "category"), payload.get("question"))


# ------------------------------------------------------------------ analyse économique (données officielles réelles)
@router.get("/economic")
def economic(db: Session = Depends(get_db)):
    from ..services import queries
    return {"history": queries.economic_history(db), "forecast": queries.economic_forecast(db)}


@router.post("/economic/explain/stream")
def economic_explain():
    def job(db, emit):
        from ..llm.explain import explain
        from ..services import queries
        emit({"type": "step", "key": "h", "label": "Analyse de l'historique officiel", "status": "running"})
        fc = queries.economic_forecast(db)
        emit({"type": "step", "key": "h", "label": "Analyse de l'historique officiel", "status": "done"})
        emit({"type": "step", "key": "p", "label": "Lecture des projections", "status": "running"})
        names = {"ins_imports": "Importations", "ins_exports": "Exportations"}
        findings = []
        for k, v in fc["forecasts"].items():
            if v.get("available"):
                a0, a1 = v["annual"][0], v["annual"][-1]
                acc = f" ; précision mesurée sur le passé : {v['accuracy_pct']:.0f} %" if v.get("accuracy_pct") is not None else ""
                findings.append(f"{names[k]} : {F._n(a0['predicted'], 0)} millions de dinars en {a0['year']}, projection "
                                f"{F._n(a1['predicted'], 0)} en {a1['year']} (intervalle {F._n(a1['lower'], 0)} – {F._n(a1['upper'], 0)}){acc}")
        emit({"type": "step", "key": "p", "label": "Lecture des projections", "status": "done"})
        emit({"type": "step", "key": "w", "label": "Rédaction de l'explication", "status": "running"})
        text = explain("Explique l'évolution projetée des importations et exportations pour un agent des Finances, en rappelant qu'une projection "
                       "n'est pas une certitude.", {"agents": [{"agent_name": "Analyse prédictive", "status": "OK", "findings": findings, "warnings": []}],
                                                   "cards": []})["text"]
        emit({"type": "step", "key": "w", "label": "Rédaction de l'explication", "status": "done"})
        stream_text(emit, text)
        return {"text": text}
    return stream_job(job)


# ------------------------------------------------------------------ statistiques
@router.get("/statistics")
def statistics(db: Session = Depends(get_db)):
    rows = F._rows(db)
    a = F.analytics(db, "month")
    delays = [(t.received_at - t.transferred_at).total_seconds() / 3600 for t, _ in rows if t.received_at]
    proc = [(t.processed_at - t.transferred_at).total_seconds() / 86400 for t, _ in rows if t.processed_at]
    return {"total": len(rows), "unit": a["unit"], "by_unit": [{"unit": u, **v} for u, v in F._amounts(rows).items()],
            "avg_reception_hours": sum(delays) / len(delays) if delays else None,
            "avg_processing_days": sum(proc) / len(proc) if proc else None, "charts": a["charts"],
            "table": [F.row_dict(t, s) for t, s in rows]}


# ------------------------------------------------------------------ rapports
@router.get("/reports")
def list_reports(db: Session = Depends(get_db)):
    return [{"id": r.id, "title": r.title, "created_at": r.created_at.isoformat(), "kind": (r.meta or {}).get("kind")}
            for r in db.query(Report).filter(Report.institution == "FINANCE").order_by(Report.id.desc())]


@router.post("/reports/stream")
def create_report(user: User = Depends(FINANCE)):
    uid = user.id
    return stream_job(lambda db, emit: {"id": (r := reports.finance_report(db, uid, emit)).id, "title": r.title})


@router.post("/cases/{cid}/report")
def case_report(cid: int, user: User = Depends(FINANCE), db: Session = Depends(get_db)):
    d = F.case_detail(db, cid)
    if not d:
        raise HTTPException(404, "Dossier introuvable ou non transmis.")
    snap = d["snapshot"] or {}
    r = reports.case_report(db, {**snap, "sources": snap.get("sources")}, "FINANCE", user.id)
    return {"id": r.id, "title": r.title}


@router.get("/reports/{rid}/download")
def download(rid: int, db: Session = Depends(get_db)):
    r = db.get(Report, rid)
    if not r or r.institution != "FINANCE" or not Path(r.path).exists():
        raise HTTPException(404, "Rapport introuvable.")
    return FileResponse(r.path, media_type="application/pdf", filename=Path(r.path).name)
