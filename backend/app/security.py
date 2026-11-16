"""Mots de passe, jetons et sessions (S-01)."""

import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta

import pyotp
from argon2 import PasswordHasher
from argon2.exceptions import Argon2Error, InvalidHashError
from fastapi import Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.errors import AppError
from app.models import AuthToken, User, UserSession

_hasher = PasswordHasher()  # Argon2id, paramètres recommandés par la bibliothèque

MIN_PASSWORD_LENGTH = 10


def now() -> datetime:
    return datetime.now(UTC)


def hash_password(password: str) -> str:
    if len(password) < MIN_PASSWORD_LENGTH:
        raise AppError(code="password_too_short", min=MIN_PASSWORD_LENGTH)
    return _hasher.hash(password)


def verify_password(password_hash: str | None, password: str) -> bool:
    if not password_hash:
        return False
    try:
        return _hasher.verify(password_hash, password)
    except (Argon2Error, InvalidHashError):
        return False


def new_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    """Seule l'empreinte est stockée : une copie de la base ne donne ni session ni lien valide."""
    return hashlib.sha256(token.encode()).hexdigest()


# ---------------------------------------------------------------- sessions


def open_session(db: Session, user: User, request: Request, response: Response, mfa: bool = False) -> None:
    settings = get_settings()
    token = new_token()
    expires = now() + timedelta(days=settings.session_days)
    db.add(
        UserSession(
            user_id=user.id,
            token_hash=hash_token(token),
            user_agent=request.headers.get("user-agent", "")[:300],
            ip=client_ip(request),
            mfa_verified=mfa,
            expires_at=expires,
        )
    )
    response.set_cookie(
        settings.session_cookie,
        token,
        max_age=settings.session_days * 86400,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )


def close_session(db: Session, session: UserSession, response: Response) -> None:
    db.delete(session)
    response.delete_cookie(get_settings().session_cookie, path="/")


def find_session(db: Session, request: Request) -> UserSession | None:
    token = request.cookies.get(get_settings().session_cookie)
    if not token:
        return None
    session = db.scalar(select(UserSession).where(UserSession.token_hash == hash_token(token)))
    if session is None or session.expires_at < now():
        return None
    if now() - session.last_seen_at > timedelta(minutes=10):  # évite une écriture par requête
        session.last_seen_at = now()
        session.user.last_seen_at = now()
    return session


def client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()[:64]
    return request.client.host if request.client else ""


# ------------------------------------------------- jetons à usage unique

TOKEN_LIFETIMES = {
    "verify_email": timedelta(days=3),
    "reset_password": timedelta(hours=1),
    "magic_link": timedelta(minutes=20),
}


def issue_token(db: Session, user: User, kind: str, payload: dict | None = None) -> str:
    token = new_token()
    db.add(
        AuthToken(
            user_id=user.id,
            kind=kind,
            token_hash=hash_token(token),
            payload=payload or {},
            expires_at=now() + TOKEN_LIFETIMES[kind],
        )
    )
    return token


def consume_token(db: Session, token: str, kind: str) -> AuthToken:
    row = db.scalar(
        select(AuthToken)
        .where(AuthToken.token_hash == hash_token(token), AuthToken.kind == kind)
        .with_for_update()
    )
    if row is None or row.used_at is not None or row.expires_at < now():
        raise AppError(code="token_invalid")
    row.used_at = now()
    return row


# ---------------------------------------------------------------- TOTP


def new_totp_secret() -> str:
    return pyotp.random_base32()


def totp_uri(user: User, secret: str) -> str:
    return pyotp.TOTP(secret).provisioning_uri(name=user.email, issuer_name=get_settings().product_name)


def verify_totp(secret: str | None, code: str) -> bool:
    return bool(secret) and pyotp.TOTP(secret).verify(code.replace(" ", ""), valid_window=1)


def user_by_id(db: Session, user_id: uuid.UUID) -> User | None:
    return db.get(User, user_id)
