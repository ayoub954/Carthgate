"""Authentication + Role-Based Access Control.

- Passwords are stored as bcrypt hashes.
- A signed session token (HS256) carries only the user id; the role is ALWAYS re-read from the database
  on every request, so a deactivated account or a changed role takes effect immediately.
- The e-mail domain (@douane.com / @finance.com) is a naming convention checked at account creation;
  it is never used to grant access.
- Every protected route declares the role it requires; any other role receives 403 (and the attempt is logged).
"""
from __future__ import annotations

import re
import secrets
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from .config import DATA_DIR, settings
from .db import get_db
from .models import AccessLog, User

ROLE_DOUANE, ROLE_FINANCE, ROLE_ADMIN = "ROLE_DOUANE", "ROLE_FINANCE", "ROLE_ADMIN"
ROLES = {ROLE_DOUANE: "DOUANE", ROLE_FINANCE: "FINANCE", ROLE_ADMIN: "ADMINISTRATION"}
DOMAIN_CONVENTION = {ROLE_DOUANE: "@douane.com", ROLE_FINANCE: "@finance.com"}
HOME = {ROLE_DOUANE: "/douane", ROLE_FINANCE: "/finance", ROLE_ADMIN: "/administration"}
_ALGO = "HS256"


def _secret() -> str:
    if settings.session_secret:
        return settings.session_secret
    f = DATA_DIR / ".session_secret"
    if not f.exists():
        f.write_text(secrets.token_urlsafe(48), encoding="utf-8")
    return f.read_text(encoding="utf-8").strip()


def hash_password(pw: str) -> str:
    return bcrypt.hashpw(pw.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("ascii")


def verify_password(pw: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(pw.encode("utf-8"), hashed.encode("ascii"))
    except ValueError:
        return False


def validate_new_account(email: str, password: str, role: str) -> str:
    email = (email or "").strip().lower()
    if role not in ROLES:
        raise ValueError("Rôle inconnu.")
    if not re.fullmatch(r"[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}", email):
        raise ValueError("Adresse professionnelle invalide.")
    conv = DOMAIN_CONVENTION.get(role)
    if conv and not email.endswith(conv):
        raise ValueError(f"Les comptes de cet espace suivent la convention prenom.nom{conv}.")
    if len(password or "") < 10:
        raise ValueError("Le mot de passe doit contenir au moins 10 caractères.")
    return email


def create_user(db: Session, email: str, password: str, role: str, full_name: str | None = None) -> User:
    email = validate_new_account(email, password, role)
    if db.query(User).filter_by(email=email).first():
        raise ValueError("Un compte existe déjà avec cette adresse.")
    u = User(email=email, full_name=full_name, password_hash=hash_password(password), role=role,
             institution=ROLES[role], active=True)
    db.add(u)
    db.flush()
    return u


def issue_token(user: User) -> str:
    now = datetime.now(timezone.utc)
    return jwt.encode({"sub": str(user.id), "iat": now, "exp": now + timedelta(hours=settings.session_hours)},
                      _secret(), algorithm=_ALGO)


def log_access(db: Session, event: str, user: User | None = None, email: str | None = None, path: str | None = None,
               detail: str | None = None) -> None:
    db.add(AccessLog(event=event, user_id=user.id if user else None, email=email or (user.email if user else None),
                     path=path, detail=detail))
    db.commit()


def current_user(request: Request, db: Session = Depends(get_db)) -> User:
    auth = request.headers.get("authorization") or ""
    token = auth[7:] if auth.lower().startswith("bearer ") else None
    if not token:
        raise HTTPException(401, "Veuillez vous connecter.")
    try:
        payload = jwt.decode(token, _secret(), algorithms=[_ALGO])
    except jwt.PyJWTError:
        raise HTTPException(401, "Votre session a expiré. Veuillez vous reconnecter.")
    user = db.get(User, int(payload.get("sub", 0)))
    if not user or not user.active:
        raise HTTPException(401, "Compte inactif ou inexistant.")
    return user


def require_role(*roles: str):
    """Dependency factory: the authenticated user must hold one of `roles`, otherwise 403."""

    def dep(request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)) -> User:
        if user.role not in roles:
            log_access(db, "FORBIDDEN", user, path=request.url.path, detail=f"rôle {user.role}")
            raise HTTPException(403, "Accès refusé : cet espace est réservé à une autre institution.")
        return user

    return dep


def user_dict(u: User) -> dict:
    return {"id": u.id, "email": u.email, "full_name": u.full_name, "role": u.role, "institution": u.institution,
            "active": u.active, "home": HOME.get(u.role, "/"),
            "created_at": u.created_at.isoformat() if u.created_at else None,
            "last_login": u.last_login.isoformat() if u.last_login else None}


def display_name(u: User) -> str:
    if u.full_name:
        return u.full_name
    local = u.email.split("@")[0]
    return " ".join(p.capitalize() for p in re.split(r"[._-]", local) if p)
