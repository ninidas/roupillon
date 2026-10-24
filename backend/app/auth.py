import hashlib
import hmac
import os
import secrets
from datetime import datetime, timedelta

import bcrypt
from fastapi import Depends, Header, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from . import models
from .database import SessionLocal, get_db

ALGORITHM = "HS256"
# Appli de téléphone : on reste connecté un an, la déconnexion passe par le changement de mot de passe
TOKEN_DAYS = 365
PASSWORD_MIN = 12
PASSWORD_MAX_BYTES = 72   # bcrypt ignore la suite
_secret: str | None = None
bearer = HTTPBearer(auto_error=False)


def secret_key() -> str:
    global _secret
    if _secret:
        return _secret
    if key := os.environ.get("SECRET_KEY"):
        _secret = key
        return key
    db = SessionLocal()
    try:
        row = db.get(models.AppConfig, "secret_key")
        if not row:
            row = models.AppConfig(key="secret_key", value=secrets.token_hex(32))
            db.add(row)
            db.commit()
        _secret = row.value
        return _secret
    finally:
        db.close()


def password_problem(pw: str) -> str | None:
    if len(pw) < PASSWORD_MIN:
        return f"Le mot de passe doit faire au moins {PASSWORD_MIN} caractères"
    if len(pw.encode()) > PASSWORD_MAX_BYTES:
        return "Le mot de passe est trop long"
    return None


def hash_password(pw: str) -> str:
    return bcrypt.hashpw(pw.encode(), bcrypt.gensalt()).decode()


def verify_password(pw: str, hashed: str) -> bool:
    return bcrypt.checkpw(pw.encode(), hashed.encode())


_DUMMY = bcrypt.hashpw(b"roupillon-dummy-password", bcrypt.gensalt()).decode()


def burn_password_check(pw: str) -> None:
    """Même durée de réponse pour un identifiant inconnu."""
    bcrypt.checkpw(pw.encode(), _DUMMY.encode())


def create_token(user: models.User) -> str:
    payload = {"sub": str(user.id), "sk": user.session_key, "exp": datetime.utcnow() + timedelta(days=TOKEN_DAYS)}
    return jwt.encode(payload, secret_key(), algorithm=ALGORITHM)


def current_user(cred: HTTPAuthorizationCredentials | None = Depends(bearer), db: Session = Depends(get_db)) -> models.User:
    if cred:
        try:
            payload = jwt.decode(cred.credentials, secret_key(), algorithms=[ALGORITHM])
            user = db.get(models.User, int(payload.get("sub")))
        except (JWTError, TypeError, ValueError):
            user = None
        if user and hmac.compare_digest(str(payload.get("sk")), user.session_key):
            return user
    raise HTTPException(status_code=401, detail="Session expirée, reconnectez-vous")


def key_hash(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def new_widget_key() -> str:
    return "rp_" + secrets.token_urlsafe(24)


# Ancien nom d'en-tête encore accepté (widgets et Raccourcis déjà installés), réglé par variable d'environnement
EXTRA_KEY_HEADER = os.environ.get("EXTRA_KEY_HEADER", "")


def widget_user(request: Request, x_roupillon_key: str | None = Header(default=None),
                db: Session = Depends(get_db)) -> models.User:
    """Widget Scriptable et Raccourcis : clé personnelle dans l'en-tête X-Roupillon-Key."""
    key = x_roupillon_key or (request.headers.get(EXTRA_KEY_HEADER) if EXTRA_KEY_HEADER else None)
    if key:
        user = db.query(models.User).filter_by(widget_key_hash=key_hash(key)).first()
        if user:
            return user
    raise HTTPException(status_code=401, detail="Clé du widget inconnue")
