"""Photos (RG-14, T-04) et lecture d'une photo par l'IA (F-19)."""

from uuid import UUID

from fastapi import APIRouter, Response, UploadFile
from fastapi.responses import RedirectResponse
from sqlalchemy import select

from app.config import get_settings
from app.deps import CurrentUser, Db, rate_limit
from app.errors import AIUnavailable, AppError, Forbidden, NotFound
from app.models import CardRef, Photo, Series, UserSeries
from app.rules import codes
from app.rules.search import fold
from app.schemas import CandidateOut, PhotoOut, QuotaOut, ReadCardIn, ReadingOut
from app.services import ai, photos, sharing
from app.storage import get_storage

router = APIRouter(tags=["photos"])

MAX_SERIES_IN_PROMPT = 200


def serve(photo: Photo, size: str, public: bool) -> Response:
    """Sert une photo après contrôle d'accès : adresse signée (stockage objet) ou contenu (disque)."""
    content, url = photos.read(photo, size)
    if url:
        return RedirectResponse(url, status_code=302, headers={"Cache-Control": "private, max-age=240"})
    # Le contenu d'une photo ne change jamais ; côté visiteur le cache reste court, le partage
    # pouvant être retiré à tout moment.
    cache = "public, max-age=300" if public else "private, max-age=86400, immutable"
    return Response(content, media_type="image/webp", headers={"Cache-Control": cache})


@router.post("/photos", status_code=201)
async def upload(file: UploadFile, user: CurrentUser, db: Db) -> PhotoOut:
    rate_limit(db, f"upload:{user.id}", 120, 3600)  # S-04
    limit = get_settings().photo_max_bytes
    raw = await file.read(limit + 1)
    if len(raw) > limit:
        raise AppError(code="photo_too_large", max_bytes=limit)
    return PhotoOut.model_validate(photos.store(db, user, raw))


@router.get("/photos/{photo_id}/{size}")
def get_photo(photo_id: UUID, size: str, user: CurrentUser, db: Db) -> Response:
    photo = db.get(Photo, photo_id)
    if photo is None or photo.user_id != user.id:
        raise NotFound()  # RG-01 : la photo d'un autre n'existe pas
    return serve(photo, size, public=False)


@router.delete("/photos/{photo_id}", status_code=204)
def discard_photo(photo_id: UUID, user: CurrentUser, db: Db) -> None:
    """F-21 : si l'enregistrement de la carte échoue, la photo envoyée est supprimée.
    Sans effet sur une photo encore utilisée (RG-14)."""
    photos.release(db, photos.owned(db, user, photo_id).id)


@router.get("/public/photos/{photo_id}/{size}")
def get_public_photo(photo_id: UUID, size: str, db: Db, token: str | None = None) -> Response:
    """Photo d'une carte partagée (RG-02). Refusée dès que le partage est retiré."""
    photo = db.get(Photo, photo_id)
    if photo is None or not sharing.photo_is_public(db, photo, token):
        raise NotFound()
    return serve(photo, size, public=True)


# ---------------------------------------------------------------------- IA


@router.get("/ai/quota")
def quota(user: CurrentUser, db: Db) -> QuotaOut:
    return QuotaOut(**ai.quota(db, user))


def _candidates(db, reading: ai.CardReading) -> list[CandidateOut]:
    """Références du catalogue qui correspondent à la lecture (série, code, nom)."""
    series_rows: list[Series] = []
    if reading.serie:
        exact = db.scalar(select(Series).where(Series.name == reading.serie, Series.status == "published"))
        if exact:
            series_rows = [exact]
        else:
            words = [w for w in fold(reading.serie).split() if len(w) > 2]
            scored = [
                (sum(w in fold(s.name) for w in words), s)
                for s in db.scalars(select(Series).where(Series.status == "published"))
            ]
            best = max((score for score, _ in scored), default=0)
            if best >= max(2, len(words) - 1):
                series_rows = [s for score, s in scored if score == best][:3]

    candidates: list[CandidateOut] = []
    key = None
    if reading.numero:
        try:
            key = codes.code_key(reading.numero)
        except codes.InvalidCode:
            key = None
    for series in series_rows:
        ref = None
        if key:
            ref = db.scalar(
                select(CardRef).where(
                    CardRef.series_id == series.id, CardRef.code_key == key, CardRef.status == "active"
                )
            )
        candidates.append(
            CandidateOut(
                series_id=series.id,
                series_name=series.name,
                card_ref_id=ref.id if ref else None,
                code=ref.code if ref else reading.numero,
                name=ref.name if ref else reading.nom,
                group=ref.group.name if ref else "",
            )
        )
    return candidates


@router.post("/ai/read-card")
def read_card(body: ReadCardIn, user: CurrentUser, db: Db) -> ReadingOut:
    """F-19 : l'IA lit la photo et propose ; l'utilisateur choisit et valide (RG-19).

    Erreurs : `ai_unavailable` ou `ai_invalid` (503), `ai_quota_exceeded` (429). Dans tous les cas la
    saisie manuelle reste possible (IA-04, CA-14, CA-20).
    """
    provider = ai.get_provider()
    if provider is None:
        raise AIUnavailable()
    if user.email_verified_at is None:
        raise Forbidden(code="email_not_verified")
    photo = photos.owned(db, user, body.photo_id)
    image = get_storage().get(f"{photo.key_prefix}/medium.webp")  # 800 px : assez pour lire, peu de jetons

    # Séries proposées au modèle : celles de l'utilisateur d'abord, puis le reste du catalogue.
    followed = list(
        db.scalars(
            select(Series.name)
            .join(UserSeries, UserSeries.series_id == Series.id)
            .where(UserSeries.user_id == user.id, Series.status == "published")
        )
    )
    others = db.scalars(
        select(Series.name)
        .where(Series.status == "published", Series.name.not_in(followed))
        .order_by(Series.published_at.desc())
        .limit(MAX_SERIES_IN_PROMPT - len(followed))
    )
    names = [*followed, *others]

    reading = ai.run(db, user, "read_card", provider.photo_model, lambda: provider.read_card(image, names))
    return ReadingOut(
        series=reading.serie.strip(),
        code=reading.numero.strip().lstrip("#"),
        name=reading.nom.strip(),
        variant=reading.variante.strip(),
        candidates=_candidates(db, reading),
    )
