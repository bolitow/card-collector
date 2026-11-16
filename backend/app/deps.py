"""Dépendances FastAPI : utilisateur courant, administrateur, limitation du débit."""

from datetime import timedelta
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app import security
from app.config import get_settings
from app.db import get_db
from app.errors import Forbidden, TooManyRequests, Unauthorized
from app.models import RateLimit, User, UserSession

Db = Annotated[Session, Depends(get_db)]


def optional_session(request: Request, db: Db) -> UserSession | None:
    return security.find_session(db, request)


def current_session(session: Annotated[UserSession | None, Depends(optional_session)]) -> UserSession:
    if session is None:
        raise Unauthorized()
    if session.user.status != "active":
        raise Forbidden(code="account_suspended")
    return session


def current_user(session: Annotated[UserSession, Depends(current_session)]) -> User:
    return session.user


def optional_user(session: Annotated[UserSession | None, Depends(optional_session)]) -> User | None:
    return session.user if session and session.user.status == "active" else None


def admin_user(session: Annotated[UserSession, Depends(current_session)]) -> User:
    user = session.user
    if user.role != "admin":
        raise Forbidden()
    # S-01 : la double authentification est obligatoire pour les administrateurs.
    if get_settings().admin_require_totp:
        if user.totp_enabled_at is None:
            raise Forbidden(code="totp_setup_required")
        if not session.mfa_verified:
            raise Forbidden(code="totp_required")
    return user


CurrentUser = Annotated[User, Depends(current_user)]
OptionalUser = Annotated[User | None, Depends(optional_user)]
AdminUser = Annotated[User, Depends(admin_user)]
CurrentSession = Annotated[UserSession, Depends(current_session)]


def rate_limit(db: Session, key: str, limit: int, window_seconds: int) -> None:
    """S-04 : au plus `limit` appels par fenêtre fixe pour cette clé. Compteur en base, donc
    partagé entre les processus."""
    now = security.now()
    window = now - timedelta(seconds=now.timestamp() % window_seconds, microseconds=now.microsecond)
    statement = (
        insert(RateLimit)
        .values(key=key, window_start=window, count=1)
        .on_conflict_do_update(index_elements=["key", "window_start"], set_={"count": RateLimit.count + 1})
        .returning(RateLimit.count)
    )
    if db.scalar(statement) > limit:
        raise TooManyRequests(retry_after=window_seconds)


def purge_rate_limits(db: Session) -> None:
    db.execute(RateLimit.__table__.delete().where(RateLimit.window_start < func.now() - timedelta(days=1)))


def count_rows(db: Session, statement) -> int:
    return db.scalar(select(func.count()).select_from(statement.subquery())) or 0
