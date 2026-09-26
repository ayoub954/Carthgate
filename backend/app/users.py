"""Account management (command line).

  python -m app.users create <email> <role> [--name "Prénom Nom"]     (password asked interactively,
                                                                     or read from DIWANA_NEW_PASSWORD)
  python -m app.users list
  python -m app.users password <email>
  python -m app.users disable <email> | enable <email>

Roles: ROLE_DOUANE (prenom.nom@douane.com) · ROLE_FINANCE (prenom.nom@finance.com) · ROLE_ADMIN
"""
from __future__ import annotations

import getpass
import os
import sys

from .auth import ROLES, create_user, hash_password
from .db import init_db, session_scope
from .models import User


def _password() -> str:
    pw = os.environ.get("DIWANA_NEW_PASSWORD")
    if pw:
        return pw
    a = getpass.getpass("Mot de passe : ")
    if a != getpass.getpass("Confirmer : "):
        sys.exit("Les mots de passe ne correspondent pas.")
    return a


def main(argv: list[str]) -> None:
    init_db()
    if not argv or argv[0] not in ("create", "list", "password", "disable", "enable"):
        sys.exit(__doc__)
    cmd = argv[0]
    with session_scope() as db:
        if cmd == "list":
            for u in db.query(User).order_by(User.role, User.email):
                print(f"{u.email:40} {u.role:14} {'actif' if u.active else 'désactivé'}")
            return
        if cmd == "create":
            if len(argv) < 3 or argv[2] not in ROLES:
                sys.exit(f"Usage : create <email> <{'|'.join(ROLES)}> [--name \"Prénom Nom\"]")
            name = argv[argv.index("--name") + 1] if "--name" in argv else None
            try:
                u = create_user(db, argv[1], _password(), argv[2], name)
            except ValueError as e:
                sys.exit(str(e))
            print(f"Compte créé : {u.email} ({u.role})")
            return
        u = db.query(User).filter_by(email=argv[1].strip().lower()).first() if len(argv) > 1 else None
        if not u:
            sys.exit("Compte introuvable.")
        if cmd == "password":
            pw = _password()
            if len(pw) < 10:
                sys.exit("Le mot de passe doit contenir au moins 10 caractères.")
            u.password_hash = hash_password(pw)
        else:
            u.active = cmd == "enable"
        print("Modification enregistrée.")


if __name__ == "__main__":
    main(sys.argv[1:])
