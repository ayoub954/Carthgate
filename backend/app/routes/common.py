"""Routes shared by every authenticated user: login, profile, notifications of the user's institution, about page."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Body, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from ..auth import current_user, issue_token, log_access, user_dict, verify_password
from ..db import get_db
from ..models import Notification, User

router = APIRouter(prefix="/api")


@router.post("/auth/login")
def login(request: Request, payload: dict = Body(...), db: Session = Depends(get_db)):
    email = (payload.get("email") or "").strip().lower()[:255]
    pw = payload.get("password") or ""
    u = db.query(User).filter_by(email=email).first()
    if not u or not u.active or not verify_password(pw, u.password_hash):
        log_access(db, "LOGIN_FAILED", email=email, path=request.url.path)
        raise HTTPException(401, "Adresse professionnelle ou mot de passe incorrect.")
    u.last_login = datetime.utcnow()
    db.commit()
    log_access(db, "LOGIN_OK", u, path=request.url.path)
    return {"token": issue_token(u), "user": user_dict(u)}


@router.get("/auth/me")
def me(user: User = Depends(current_user)):
    return user_dict(user)


# Notifications are scoped to the institution of the authenticated user (never another institution's).
@router.get("/notifications")
def notifications(user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.query(Notification).filter(Notification.institution == user.institution).order_by(Notification.created_at.desc()).limit(30).all()
    return {"unread": sum(1 for n in rows if not n.read_at),
            "items": [{"id": n.id, "kind": n.kind, "title": n.title, "body": n.body, "case_id": n.case_id,
                       "created_at": n.created_at.isoformat(), "read": bool(n.read_at)} for n in rows]}


@router.post("/notifications/read-all")
def notifications_read(user: User = Depends(current_user), db: Session = Depends(get_db)):
    db.query(Notification).filter(Notification.institution == user.institution, Notification.read_at.is_(None)).update(
        {Notification.read_at: datetime.utcnow()})
    db.commit()
    return {"ok": True}


@router.get("/about")
def about(user: User = Depends(current_user)):
    return {
        "problem": "De grandes activités commerciales peuvent être cachées derrière de nombreuses petites importations et ventes en ligne. "
                   "Prises séparément, ces opérations semblent normales ; analysées ensemble, elles révèlent des schémas à vérifier.",
        "question": "Comment détecter une activité commerciale importante fragmentée derrière de nombreuses petites opérations "
                    "difficiles à identifier individuellement ?",
        "themes": [
            {"code": "T1", "label": "Data Mining et analyse des risques", "how": "Croisement des statistiques officielles, recherche d'anomalies, classement de chaque situation."},
            {"code": "T11", "label": "Cyberpatrouille et commerce en ligne", "how": "Observation des produits et commerces publiquement visibles, comparée aux flux déclarés."},
            {"code": "T20", "label": "Scoring dynamique du risque", "how": "Indice de priorité recalculé à chaque analyse, expliqué et assorti de ses preuves."},
            {"code": "T21", "label": "E-commerce transfrontalier et petits envois", "how": "Détection de fragmentation : petites opérations répétées, rapprochées, similaires."},
        ],
        "rules": ["Anomalie ≠ fraude", "Observation ≠ vente", "Corrélation ≠ preuve", "Projection ≠ certitude",
                  "Priorité élevée = priorité de vérification humaine", "L'IA ne transmet jamais un dossier : seul un agent de la Douane le fait"],
    }
