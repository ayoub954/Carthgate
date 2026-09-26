"""/api/douane/* — reserved to ROLE_DOUANE (any other role receives 403)."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Body, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from ..auth import ROLE_DOUANE, display_name, require_role
from ..db import get_db
from ..models import Case, CaseEvent, CaseTransfer, Notification, Product, Report, User
from ..services import cases as C
from ..services import douane as D
from ..services import finance as F
from ..services import reports
from ..services.insight import explain_rows
from ._stream import stream_job, stream_text

DOUANE = require_role(ROLE_DOUANE)
router = APIRouter(prefix="/api/douane", dependencies=[Depends(DOUANE)])

TRANSITIONS = {"A_ANALYSER": ["EN_COURS", "CLASSE"], "EN_COURS": ["A_VERIFIER", "CLASSE"], "A_VERIFIER": ["EN_COURS", "CLASSE"],
               "CLASSE": ["EN_COURS"], "TRANSMIS": []}
TRANSFER_ITEMS = ["Synthèse", "Produits", "Opérations concernées", "Valeurs disponibles", "Graphiques", "Sources", "Analyse IA"]


# ------------------------------------------------------------------ vue d'ensemble / analyse
@router.get("/overview")
def overview(db: Session = Depends(get_db)):
    return D.overview(db)


@router.post("/analyze/stream")
def analyze():
    return stream_job(lambda db, emit: D.run_analysis(db, emit))


@router.get("/charts")
def charts(db: Session = Depends(get_db)):
    return D.charts(db)


@router.post("/explain-chart")
def explain_chart(payload: dict = Body(...)):
    return explain_rows(str(payload.get("title", ""))[:200], list(payload.get("rows") or [])[:200], payload.get("unit"),
                        payload.get("kind", "category"), payload.get("question"))


@router.get("/catalog")
def catalog(db: Session = Depends(get_db)):
    prods = db.query(Product).filter(Product.monitored.is_(True)).order_by(Product.category, Product.short_name).all()
    return {"products": [{"id": p.id, "name": p.short_name, "category": p.category} for p in prods],
            "categories": sorted({p.category for p in prods if p.category})}


# ------------------------------------------------------------------ investigation IA
@router.post("/investigate/stream")
def investigate(payload: dict = Body(...)):
    q = (payload.get("question") or "").strip()[:1000]
    if not q:
        raise HTTPException(400, "Veuillez saisir une question.")

    def job(db, emit):
        from ..agents.orchestrator import investigate as run
        res = run(db, q, emit)
        pid = next((c["product_id"] for c in res["cards"] if c.get("product_id")), None)
        o = D.origins(db, product=pid) if pid else D.origins(db)
        res["charts"] = {
            "priorities": [{"label": c["product"], "value": c["priority_score"]} for c in res["cards"] if c.get("priority_score") is not None],
            "origins": [{"label": c["country"], "value": c["value"]} for c in o["countries"][:8]],
            "origins_period": o["year"], "origins_scope": next((c["product"] for c in res["cards"] if c.get("product_id") == pid), "Produits suivis"),
        }
        res["map_zones"] = sorted({c["zone"] for c in res["cards"] if c.get("zone")})
        res["recommendation"] = next((c["recommended_review"] for c in res["cards"] if c.get("recommended_review")),
                                     "Aucune recommandation spécifique : les données disponibles ne font pas ressortir de priorité.")
        return res
    return stream_job(job)


# ------------------------------------------------------------------ commerce en ligne
@router.get("/commerce")
def commerce(db: Session = Depends(get_db)):
    return D.commerce(db)


# ------------------------------------------------------------------ dossiers
@router.get("/cases")
def list_cases(status: str | None = None, classification: str | None = None, category: str | None = None, q: str | None = None,
               db: Session = Depends(get_db)):
    qs = db.query(Case)
    if status:
        qs = qs.filter(Case.status == status)
    if classification:
        qs = qs.filter(Case.classification == classification)
    if category:
        qs = qs.filter(Case.category == category)
    if q:
        qs = qs.filter((Case.product.ilike(f"%{q}%")) | (Case.case_ref.ilike(f"%{q}%")) | (Case.motif.ilike(f"%{q}%")))
    rows = qs.order_by(Case.priority_score.desc()).all()
    return {"items": [C.case_row(c) for c in rows], "statuses": [{"value": k, "label": v} for k, v in C.STATUS_FR.items()],
            "classifications": [{"value": k, "label": C.CLASS_FR[k]} for k in ("PRIORITAIRE", "A_VERIFIER")],
            "categories": sorted({c.category for c in db.query(Case) if c.category})}


def _case(db: Session, cid: int) -> Case:
    c = db.get(Case, cid)
    if not c:
        raise HTTPException(404, "Dossier introuvable.")
    return c


@router.get("/cases/{cid}")
def get_case(cid: int, db: Session = Depends(get_db)):
    c = _case(db, cid)
    out = C.case_full(db, c, "DOUANE")
    out["next_status"] = [{"value": s, "label": C.STATUS_FR[s]} for s in TRANSITIONS.get(c.status, [])]
    out["transfer_items"] = TRANSFER_ITEMS
    t = db.query(CaseTransfer).filter_by(case_id=cid).order_by(CaseTransfer.id.desc()).first()
    out["transfer"] = {"at": t.transferred_at.isoformat(), "status": C.FIN_STATUS_FR.get(t.status), "comment": t.comment} if t else None
    return out


@router.post("/cases/{cid}/status")
def set_status(cid: int, payload: dict = Body(...), user: User = Depends(DOUANE), db: Session = Depends(get_db)):
    c = _case(db, cid)
    new = payload.get("status")
    if new not in TRANSITIONS.get(c.status, []):
        raise HTTPException(400, "Changement de statut non autorisé.")
    comment = (payload.get("comment") or "").strip()[:2000] or None
    if new == "CLASSE" and not comment:
        raise HTTPException(400, "Un commentaire est nécessaire pour classer un dossier.")
    old = c.status
    c.status, c.updated_at = new, datetime.utcnow()
    if new == "EN_COURS" and not c.assigned_customs_user:
        c.assigned_customs_user = user.id
    db.add(CaseEvent(case_id=cid, user_id=user.id, actor=display_name(user), institution="DOUANE",
                     action=f"Statut : {C.STATUS_FR[old]} → {C.STATUS_FR[new]}", detail=comment, visibility="DOUANE"))
    db.commit()
    return get_case(cid, db)


@router.post("/cases/{cid}/transfer")
def transfer(cid: int, payload: dict = Body(...), user: User = Depends(DOUANE), db: Session = Depends(get_db)):
    """Human decision only: the AI never transmits a dossier."""
    c = _case(db, cid)
    if c.classification not in ("A_VERIFIER", "PRIORITAIRE"):
        raise HTTPException(400, "Seuls les dossiers nécessitant une vérification peuvent être transmis.")
    if c.status not in ("EN_COURS", "A_VERIFIER"):
        raise HTTPException(400, "Le dossier doit d'abord être pris en charge et vérifié par un agent.")
    if payload.get("verified") is not True:
        raise HTTPException(400, "Veuillez confirmer que le dossier a été vérifié.")
    motif = (payload.get("motif") or "").strip()[:500]
    if not motif:
        raise HTTPException(400, "Le motif de transmission est obligatoire.")
    comment = (payload.get("comment") or "").strip()[:2000] or None
    now = datetime.utcnow()
    t = CaseTransfer(case_id=cid, sender_user_id=user.id, sender_institution="DOUANE", receiver_institution="FINANCE", motif=motif,
                     comment=comment, items=TRANSFER_ITEMS, snapshot=F.snapshot(c, motif, comment), transferred_at=now, status="TRANSMIS")
    db.add(t)
    c.status, c.finance_status, c.updated_at = "TRANSMIS", "TRANSMIS", now
    db.add(CaseEvent(case_id=cid, user_id=user.id, actor=display_name(user), institution="DOUANE", action="Transmis à Finance",
                     detail=f"Motif : {motif}" + (f" — {comment}" if comment else ""), visibility="ALL"))
    db.add(Notification(institution="FINANCE", kind="NEW_CASE", title="Nouveau dossier reçu", case_id=cid,
                        body={"ref": c.case_ref, "date": now.isoformat(), "category": c.category,
                              "priority": C.CLASS_FR.get(c.classification), "product": c.product}))
    db.commit()
    return get_case(cid, db)


@router.get("/transfers")
def transfers(db: Session = Depends(get_db)):
    return {"items": D.transfers(db)}


# ------------------------------------------------------------------ carte / géographie
@router.get("/map")
def control_map(db: Session = Depends(get_db)):
    return D.control_map(db)


@router.get("/zones/{gov}")
def zone(gov: str, db: Session = Depends(get_db)):
    return D.zone_detail(db, gov)


@router.post("/geo/analyze/stream")
def geo_analyze():
    return stream_job(lambda db, emit: D.geo_analysis(db, emit))


@router.get("/origins")
def origins(category: str | None = None, product: str | None = None, year: str | None = None, db: Session = Depends(get_db)):
    return D.origins(db, category, product, year)


@router.get("/flows")
def flows(product: str | None = None, category: str | None = None, year: str | None = None, db: Session = Depends(get_db)):
    return D.flows(db, product, category, year)


# ------------------------------------------------------------------ produits
@router.get("/products")
def products(db: Session = Depends(get_db)):
    return D.products_observed(db)


@router.get("/products/{pid}")
def product(pid: str, db: Session = Depends(get_db)):
    r = D.product_360(db, pid)
    if not r:
        raise HTTPException(404, "Produit introuvable.")
    return r


@router.post("/products/{pid}/analyze/stream")
def product_analyze(pid: str):
    return stream_job(lambda db, emit: D.analyze_product(db, pid, emit))


@router.get("/pathway")
def pathway(product: str | None = None, db: Session = Depends(get_db)):
    return D.pathway(db, product)


# ------------------------------------------------------------------ conseiller IA
@router.post("/advisor/stream")
def advisor():
    def job(db, emit):
        r = D.advisor(db, emit)
        stream_text(emit, r["text"])
        return r
    return stream_job(job)


# ------------------------------------------------------------------ preuves
@router.get("/evidence/{lid}")
def evidence(lid: str, db: Session = Depends(get_db)):
    from ..services import lineage
    r = lineage.lineage(db, lid)
    if r.get("error"):
        raise HTTPException(404, "Preuves indisponibles.")
    return r


# ------------------------------------------------------------------ déclarations détaillées (extrait autorisé)
@router.post("/customs/import")
async def customs_import(file: UploadFile = File(...), user: User = Depends(DOUANE), db: Session = Depends(get_db)):
    from ..providers.institutional import import_customs_extract
    content = await file.read()
    try:
        res = import_customs_extract(db, content, file.filename or "extrait.csv", datetime.utcnow().strftime("lot_%Y%m%d%H%M%S"))
        db.commit()
    except ValueError as e:
        db.rollback()
        raise HTTPException(400, str(e))
    except Exception:
        db.rollback()
        raise HTTPException(400, "Le fichier n'a pas pu être lu. Vérifiez qu'il s'agit d'un fichier CSV ou Excel.")
    return {"rows": res["rows"], "message": f"{res['rows']} déclaration(s) importée(s). Lancez l'analyse pour les prendre en compte."}


# ------------------------------------------------------------------ rapports
@router.get("/reports")
def list_reports(db: Session = Depends(get_db)):
    return [{"id": r.id, "title": r.title, "created_at": r.created_at.isoformat(), "kind": (r.meta or {}).get("kind")}
            for r in db.query(Report).filter(Report.institution == "DOUANE").order_by(Report.id.desc())]


@router.post("/reports/stream")
def create_report(user: User = Depends(DOUANE)):
    uid = user.id
    return stream_job(lambda db, emit: {"id": (r := reports.douane_report(db, uid, emit)).id, "title": r.title})


@router.post("/cases/{cid}/report")
def case_report(cid: int, user: User = Depends(DOUANE), db: Session = Depends(get_db)):
    c = _case(db, cid)
    r = reports.case_report(db, C.case_full(db, c, "DOUANE"), "DOUANE", user.id)
    return {"id": r.id, "title": r.title}


@router.get("/reports/{rid}/download")
def download(rid: int, db: Session = Depends(get_db)):
    r = db.get(Report, rid)
    if not r or r.institution != "DOUANE" or not Path(r.path).exists():
        raise HTTPException(404, "Rapport introuvable.")
    return FileResponse(r.path, media_type="application/pdf", filename=Path(r.path).name)
