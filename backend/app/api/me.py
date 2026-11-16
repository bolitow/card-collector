"""Compte et paramètres (F-30, F-31), partage (F-42, F-44)."""

from uuid import UUID

from fastapi import APIRouter, Response
from sqlalchemy import select

from app import security
from app.config import get_settings
from app.deps import CurrentSession, CurrentUser, Db, rate_limit
from app.errors import AppError, Conflict, Forbidden, NotFound, Unauthorized
from app.models import Job, ShareLink, User, UserSeries, UserSession
from app.schemas import (
    ChangeEmailIn,
    DeleteAccountIn,
    JobOut,
    MeIn,
    MeOut,
    PasswordIn,
    PublicProfileOut,
    SessionOut,
    ShareLinkOut,
    SharingCollectionOut,
    SharingOut,
    TotpIn,
    TotpSetupOut,
)
from app.services import accounts, ai, collections, jobs, photos, sharing
from app.storage import get_storage

router = APIRouter(prefix="/me", tags=["me"])


def _admin_access(session: UserSession) -> str | None:
    user = session.user
    if user.role != "admin":
        return None
    if not get_settings().admin_require_totp:
        return "ok"
    if user.totp_enabled_at is None:
        return "totp_setup_required"
    return "ok" if session.mfa_verified else "totp_required"


def _me(db, session: UserSession) -> MeOut:
    user = session.user
    return MeOut(
        id=user.id,
        email=user.email,
        email_verified=user.email_verified_at is not None,
        pseudo=user.pseudo,
        locale=user.locale,
        currency=user.currency,
        theme=user.theme,
        role=user.role,
        avatar_photo_id=user.avatar_photo_id,
        public_profile=user.public_profile,
        share_singles=user.share_singles,
        notify_series_published=user.notify_series_published,
        has_password=user.password_hash is not None,
        totp_enabled=user.totp_enabled_at is not None,
        admin_access=_admin_access(session),
        ai=ai.quota(db, user),
        ai_available=ai.get_provider() is not None,
    )


@router.get("")
def me(session: CurrentSession, db: Db) -> MeOut:
    return _me(db, session)


@router.patch("")
def update_me(body: MeIn, session: CurrentSession, db: Db) -> MeOut:
    user = session.user
    data = body.model_dump(exclude_unset=True)
    if "pseudo" in data and data["pseudo"]:
        user.pseudo = accounts.check_pseudo(db, data.pop("pseudo"), user)
    if data.get("public_profile") and user.email_verified_at is None:
        raise Forbidden(code="email_not_verified")  # un profil public demande une adresse confirmée
    if "avatar_photo_id" in data and data["avatar_photo_id"] != user.avatar_photo_id:
        photos.owned(db, user, data["avatar_photo_id"])
        previous, user.avatar_photo_id = user.avatar_photo_id, data.pop("avatar_photo_id")
        photos.release(db, previous)
    for field in (
        "locale",
        "currency",
        "theme",
        "public_profile",
        "share_singles",
        "notify_series_published",
    ):
        if data.get(field) is not None:
            setattr(user, field, data[field])
    db.flush()
    return _me(db, session)


@router.post("/password", status_code=204)
def change_password(body: PasswordIn, session: CurrentSession, db: Db) -> None:
    user = session.user
    if user.password_hash and not security.verify_password(user.password_hash, body.current or ""):
        raise Unauthorized(code="invalid_credentials")
    user.password_hash = security.hash_password(body.new)
    # Les autres sessions sont fermées.
    for other in db.scalars(
        select(UserSession).where(UserSession.user_id == user.id, UserSession.id != session.id)
    ):
        db.delete(other)


@router.post("/email", status_code=204)
def change_email(body: ChangeEmailIn, user: CurrentUser, db: Db) -> None:
    """La nouvelle adresse ne remplace l'ancienne qu'après confirmation par le lien reçu."""
    rate_limit(db, f"email:{user.id}", 5, 3600)
    if db.scalar(select(User).where(User.email == body.email)):
        raise Conflict(code="email_taken")
    accounts.send_link(
        db, user, "verify_email", "/verifier", to=body.email, payload={"new_email": body.email}
    )


@router.post("/verification", status_code=204)
def resend_verification(user: CurrentUser, db: Db) -> None:
    rate_limit(db, f"verify:{user.id}", 5, 3600)
    if user.email_verified_at is None:
        accounts.send_link(db, user, "verify_email", "/verifier")


# ---------------------------------------------------------------- sessions


@router.get("/sessions")
def sessions(session: CurrentSession, db: Db) -> list[SessionOut]:
    rows = db.scalars(
        select(UserSession)
        .where(UserSession.user_id == session.user_id)
        .order_by(UserSession.last_seen_at.desc())
    )
    return [SessionOut.model_validate(r).model_copy(update={"current": r.id == session.id}) for r in rows]


@router.delete("/sessions/{session_id}", status_code=204)
def close_session(session_id: int, session: CurrentSession, db: Db) -> None:
    other = db.get(UserSession, session_id)
    if other is None or other.user_id != session.user_id:
        raise NotFound()
    db.delete(other)


# ------------------------------------------------- double authentification


@router.post("/totp/setup")
def totp_setup(user: CurrentUser) -> TotpSetupOut:
    if user.totp_enabled_at:
        raise Conflict(code="totp_already_enabled")
    user.totp_secret = security.new_totp_secret()
    return TotpSetupOut(secret=user.totp_secret, uri=security.totp_uri(user, user.totp_secret))


@router.post("/totp/enable", status_code=204)
def totp_enable(body: TotpIn, session: CurrentSession) -> None:
    user = session.user
    if not security.verify_totp(user.totp_secret, body.code):
        raise AppError(code="totp_invalid")
    user.totp_enabled_at = security.now()
    session.mfa_verified = True


@router.post("/totp/disable", status_code=204)
def totp_disable(body: TotpIn, user: CurrentUser) -> None:
    if user.role == "admin" and get_settings().admin_require_totp:
        raise Forbidden(code="totp_mandatory_for_admins")  # S-01
    if not security.verify_totp(user.totp_secret, body.code):
        raise AppError(code="totp_invalid")
    user.totp_secret, user.totp_enabled_at = None, None


# ------------------------------------------------- export et suppression


@router.post("/exports", status_code=202)
def start_export(user: CurrentUser, db: Db) -> JobOut:
    rate_limit(db, f"export:{user.id}", 3, 86400)
    return JobOut.model_validate(jobs.enqueue(db, "export_data", user_id=user.id))


@router.get("/exports")
def exports(user: CurrentUser, db: Db) -> list[JobOut]:
    rows = db.scalars(
        select(Job)
        .where(Job.user_id == user.id, Job.kind == "export_data")
        .order_by(Job.created_at.desc())
        .limit(5)
    )
    return [
        JobOut.model_validate(r).model_copy(update={"result": {"bytes": r.result.get("bytes")}}) for r in rows
    ]


@router.get("/exports/{job_id}/download")
def download_export(job_id: UUID, user: CurrentUser, db: Db) -> Response:
    job = db.get(Job, job_id)
    if job is None or job.user_id != user.id or job.kind != "export_data" or job.status != "done":
        raise NotFound()
    data = get_storage().get(job.result["key"])
    headers = {"Content-Disposition": 'attachment; filename="mes-donnees.zip"', "Cache-Control": "no-store"}
    return Response(data, media_type="application/zip", headers=headers)


@router.post("/delete", status_code=202)
def delete_account(body: DeleteAccountIn, user: CurrentUser, response: Response, db: Db) -> dict:
    accounts.request_deletion(db, user, body.word)
    response.delete_cookie(get_settings().session_cookie, path="/")
    return {"days": get_settings().account_deletion_days}


# ----------------------------------------------------------------- partage


@router.get("/sharing")
def get_sharing(user: CurrentUser, db: Db) -> SharingOut:
    links: dict[int, list[ShareLink]] = {}
    for link in db.scalars(
        select(ShareLink).where(ShareLink.user_id == user.id, ShareLink.revoked_at.is_(None))
    ):
        links.setdefault(link.user_series_id, []).append(link)
    rows = db.scalars(
        select(UserSeries)
        .where(
            UserSeries.user_id == user.id, UserSeries.series_id.is_not(None), UserSeries.status == "followed"
        )
        .order_by(UserSeries.created_at)
    )
    return SharingOut(
        public_profile=user.public_profile,
        share_singles=user.share_singles,
        pseudo=user.pseudo,
        collections=[
            SharingCollectionOut(
                id=c.id,
                name=c.series.name,
                shared=c.shared,
                share_photos_only=c.share_photos_only,
                share_missing=c.share_missing,
                links=[ShareLinkOut.model_validate(x) for x in links.get(c.id, [])],
            )
            for c in rows
        ],
    )


@router.get("/sharing/preview")
def sharing_preview(user: CurrentUser, db: Db) -> PublicProfileOut:
    """F-44 « Aperçu » : exactement ce que voient les visiteurs, même si le profil n'est pas activé."""
    return PublicProfileOut.model_validate(sharing.profile_view(db, user))


@router.post("/collections/{collection_id}/links", status_code=201)
def create_link(collection_id: int, user: CurrentUser, db: Db) -> ShareLinkOut:
    collection = collections.get_collection(db, user, collection_id)
    if collection.series_id is None:
        raise AppError(code="personal_collection_not_shareable")
    if user.email_verified_at is None:
        raise Forbidden(code="email_not_verified")
    return ShareLinkOut.model_validate(sharing.create_link(db, user, collection))


@router.delete("/links/{link_id}", status_code=204)
def revoke_link(link_id: int, user: CurrentUser, db: Db) -> None:
    sharing.revoke_link(db, user, link_id)
