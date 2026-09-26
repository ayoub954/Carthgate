"""/api/admin/* — reserved to ROLE_ADMIN: accounts, security journal, data sources, data refresh."""
from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import pipeline
from ..auth import ROLE_ADMIN, ROLES, create_user, hash_password, require_role, user_dict
from ..db import get_db
from ..models import AccessLog, DataSource, User

ADMIN = require_role(ROLE_ADMIN)
router = APIRouter(prefix="/api/admin", dependencies=[Depends(ADMIN)])
EVENT_FR = {"LOGIN_OK": "Connexion", "LOGIN_FAILED": "Échec de connexion", "FORBIDDEN": "Accès refusé"}


@router.get("/users")
def users(db: Session = Depends(get_db)):
    return {"items": [user_dict(u) for u in db.query(User).order_by(User.role, User.email)],
            "roles": [{"value": k, "label": {"ROLE_DOUANE": "Douane", "ROLE_FINANCE": "Finance", "ROLE_ADMIN": "Administration"}[k]} for k in ROLES]}


@router.post("/users")
def add_user(payload: dict = Body(...), db: Session = Depends(get_db)):
    try:
        u = create_user(db, payload.get("email", ""), payload.get("password", ""), payload.get("role", ""), payload.get("full_name") or None)
    except ValueError as e:
        raise HTTPException(400, str(e))
    db.commit()
    return user_dict(u)


@router.patch("/users/{uid}")
def update_user(uid: int, payload: dict = Body(...), admin: User = Depends(ADMIN), db: Session = Depends(get_db)):
    u = db.get(User, uid)
    if not u:
        raise HTTPException(404, "Compte introuvable.")
    if "active" in payload:
        if u.id == admin.id and not payload["active"]:
            raise HTTPException(400, "Vous ne pouvez pas désactiver votre propre compte.")
        u.active = bool(payload["active"])
    if payload.get("password"):
        if len(payload["password"]) < 10:
            raise HTTPException(400, "Le mot de passe doit contenir au moins 10 caractères.")
        u.password_hash = hash_password(payload["password"])
    db.commit()
    return user_dict(u)


@router.get("/access-logs")
def access_logs(db: Session = Depends(get_db)):
    return [{"at": a.at.isoformat(), "email": a.email, "event": EVENT_FR.get(a.event, a.event), "path": a.path, "detail": a.detail}
            for a in db.query(AccessLog).order_by(AccessLog.id.desc()).limit(200)]


@router.get("/sources")
def sources(db: Session = Depends(get_db)):
    from ..services.queries import SOURCE_INFO, status_fr
    out = []
    for d in db.query(DataSource):
        info = SOURCE_INFO.get(d.key)
        if info is None:
            continue
        out.append({"key": d.key, "name": info[0], "description": info[1], "status": status_fr(d.status, d.access_type),
                    "connected": d.status == "CONNECTED", "period": d.period, "records": d.records,
                    "updated": d.last_updated.strftime("%d/%m/%Y") if d.last_updated else None, "url": d.url})
    return sorted(out, key=lambda r: (not r["connected"], r["name"]))


@router.post("/refresh")
def refresh():
    return {"started": pipeline.run_in_background(providers=True, analytics_=True)}


@router.get("/refresh/status")
def refresh_status():
    labels = {"provider": "Mise à jour des sources", "analytics": "Analyse des données"}
    step = pipeline.STATE.get("step") or ""
    return {"running": pipeline.STATE["running"], "step": labels.get(step.split(":")[0]) if step else None}
