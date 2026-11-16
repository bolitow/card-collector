"""Inscription et connexion (F-28, F-29)."""

from fastapi import APIRouter, Request, Response
from sqlalchemy import delete, select

from app import security
from app.config import get_settings
from app.deps import CurrentSession, Db, rate_limit
from app.errors import AppError, Unauthorized
from app.models import User, UserSession
from app.schemas import EmailIn, LoginIn, RegisterIn, ResetPasswordIn, TokenIn, TotpIn
from app.services import accounts

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", status_code=201)
def register(body: RegisterIn, request: Request, response: Response, db: Db) -> dict:
    rate_limit(db, f"register:{security.client_ip(request)}", 10, 3600)
    if not body.accept_terms:
        raise AppError(code="terms_required")
    if not body.age_confirmed:
        raise AppError(code="age_required")  # section 2 : 15 ans ou plus, ou accord d'un parent
    user = accounts.register(db, body.email, body.password, body.pseudo, body.locale)
    accounts.send_link(db, user, "verify_email", "/verifier")
    if body.password:
        security.open_session(db, user, request, response)
    else:
        accounts.send_link(db, user, "magic_link", "/connexion/lien")
    return {"signed_in": bool(body.password)}


@router.post("/login")
def login(body: LoginIn, request: Request, response: Response, db: Db) -> dict:
    rate_limit(db, f"login:{security.client_ip(request)}", 30, 900)
    rate_limit(db, f"login:{body.email.lower()}", 10, 900)
    user = db.scalar(select(User).where(User.email == body.email))
    if user is None or not security.verify_password(user.password_hash, body.password):
        raise Unauthorized(code="invalid_credentials")
    if user.status != "active":
        raise Unauthorized(code="account_suspended")
    mfa = False
    if user.totp_enabled_at:
        if not body.totp:
            raise Unauthorized(code="totp_required")
        if not security.verify_totp(user.totp_secret, body.totp):
            raise Unauthorized(code="totp_invalid")
        mfa = True
    security.open_session(db, user, request, response, mfa=mfa)
    return {"signed_in": True}


@router.post("/logout", status_code=204)
def logout(session: CurrentSession, response: Response, db: Db) -> None:
    security.close_session(db, session, response)


@router.post("/totp", status_code=204)
def verify_totp(body: TotpIn, session: CurrentSession, request: Request, db: Db) -> None:
    """Élève la session en cours (connexion par lien, ou double authentification activée après coup)."""
    rate_limit(db, f"totp:{session.user_id}", 10, 900)
    if not security.verify_totp(session.user.totp_secret, body.code):
        raise Unauthorized(code="totp_invalid")
    session.mfa_verified = True


@router.post("/magic-link", status_code=204)
def magic_link(body: EmailIn, request: Request, db: Db) -> None:
    """Lien de connexion par e-mail. La réponse est la même que l'adresse soit connue ou non."""
    rate_limit(db, f"magic:{security.client_ip(request)}", 10, 3600)
    rate_limit(db, f"magic:{body.email.lower()}", 5, 3600)
    user = db.scalar(select(User).where(User.email == body.email, User.status == "active"))
    if user:
        accounts.send_link(db, user, "magic_link", "/connexion/lien")


@router.post("/magic-link/consume")
def consume_magic_link(body: TokenIn, request: Request, response: Response, db: Db) -> dict:
    token = security.consume_token(db, body.token, "magic_link")
    user = db.get(User, token.user_id)
    if user is None or user.status != "active":
        raise Unauthorized(code="token_invalid")
    user.email_verified_at = user.email_verified_at or security.now()  # le lien prouve l'adresse
    security.open_session(db, user, request, response)
    return {"signed_in": True}


@router.post("/verify-email", status_code=204)
def verify_email(body: TokenIn, db: Db) -> None:
    token = security.consume_token(db, body.token, "verify_email")
    user = db.get(User, token.user_id)
    new_email = token.payload.get("new_email")
    if new_email:
        if db.scalar(select(User).where(User.email == new_email, User.id != user.id)):
            raise AppError(code="email_taken")
        user.email = new_email
    user.email_verified_at = security.now()


@router.post("/forgot-password", status_code=204)
def forgot_password(body: EmailIn, request: Request, db: Db) -> None:
    rate_limit(db, f"forgot:{security.client_ip(request)}", 10, 3600)
    rate_limit(db, f"forgot:{body.email.lower()}", 5, 3600)
    user = db.scalar(select(User).where(User.email == body.email, User.status == "active"))
    if user:
        accounts.send_link(db, user, "reset_password", "/reinitialiser")


@router.post("/reset-password", status_code=204)
def reset_password(body: ResetPasswordIn, db: Db) -> None:
    password_hash = security.hash_password(body.password)
    token = security.consume_token(db, body.token, "reset_password")
    user = db.get(User, token.user_id)
    user.password_hash = password_hash
    user.email_verified_at = user.email_verified_at or security.now()
    # Un mot de passe réinitialisé ferme toutes les sessions ouvertes.
    db.execute(delete(UserSession).where(UserSession.user_id == user.id))


@router.get("/providers")
def providers() -> dict:
    """Connexions tierces configurées (F-28) : l'interface n'affiche que celles-ci."""
    settings = get_settings()
    return {"google": bool(settings.google_client_id), "apple": bool(settings.apple_client_id)}
