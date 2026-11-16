"""Catalogue commun, accessible sans compte (F-32 à F-34), et signalements (RG-03, F-45)."""

from fastapi import APIRouter, Query, Request, Response
from sqlalchemy import func, select

from app import security
from app.deps import CurrentUser, Db, OptionalUser, rate_limit
from app.errors import NotFound
from app.models import (
    CardRef,
    CardRefTeam,
    ChaseMark,
    Photo,
    Publisher,
    Report,
    Series,
    SeriesRequest,
    SeriesRequestVote,
    Universe,
    User,
    UserSeries,
)
from app.schemas import (
    CatalogOut,
    ChaseOut,
    GroupOut,
    ReportIn,
    SeriesDetailOut,
    SeriesOut,
    SeriesRequestIn,
    SeriesRequestOut,
)
from app.services import catalog, collections

router = APIRouter(tags=["catalog"])


def series_out(series: Series, followed: bool = False) -> dict:
    return {
        "id": series.id,
        "name": series.name,
        "short_name": collections.short_series_name(series),
        "publisher": series.publisher.name,
        "universe_id": series.universe_id,
        "season": series.season,
        "card_count": series.card_count,
        "version": series.version,
        "followed": followed,
    }


def _followed_ids(db, user: User | None) -> set[int]:
    if user is None:
        return set()
    return set(
        db.scalars(
            select(UserSeries.series_id).where(UserSeries.user_id == user.id, UserSeries.status == "followed")
        )
    )


@router.get("/catalog")
def catalog_index(db: Db, response: Response) -> CatalogOut:
    response.headers["Cache-Control"] = "public, max-age=300"
    in_use = select(Series.publisher_id).where(Series.status == "published")
    return CatalogOut(
        universes=list(db.scalars(select(Universe).order_by(Universe.position, Universe.name))),
        publishers=list(
            db.scalars(select(Publisher).where(Publisher.id.in_(in_use)).order_by(Publisher.name))
        ),
        seasons=list(
            db.scalars(
                select(Series.season)
                .where(Series.status == "published", Series.season != "")
                .group_by(Series.season)
                .order_by(Series.season.desc())
            )
        ),
    )


@router.get("/catalog/series")
def list_series(
    db: Db,
    user: OptionalUser,
    universe: int | None = None,
    publisher: int | None = None,
    season: str = "",
    q: str = Query("", max_length=100),
) -> list[SeriesOut]:
    followed = _followed_ids(db, user)
    return [
        SeriesOut(**series_out(s, s.id in followed))
        for s in catalog.list_series(db, universe, publisher, season, q)
    ]


@router.get("/catalog/series/{series_id}")
def series_detail(series_id: int, db: Db, user: OptionalUser) -> SeriesDetailOut:
    """F-33 : fiche d'une série."""
    series = catalog.get_published(db, series_id)
    counts: dict[str, int] = {}
    for group in series.groups:
        counts[group.kind] = counts.get(group.kind, 0) + group.card_count
    chase = db.execute(
        select(CardRef.id, CardRef.code, CardRef.name, ChaseMark.reason)
        .join(ChaseMark, ChaseMark.card_ref_id == CardRef.id)
        .where(CardRef.series_id == series.id, CardRef.status == "active")
        .order_by(CardRef.position)
    ).all()
    has_teams = bool(
        db.scalar(
            select(CardRefTeam.team_id)
            .join(CardRef, CardRef.id == CardRefTeam.card_ref_id)
            .where(CardRef.series_id == series.id)
            .limit(1)
        )
    )
    collection_id = None
    if user:
        collection_id = db.scalar(
            select(UserSeries.id).where(
                UserSeries.user_id == user.id,
                UserSeries.series_id == series.id,
                UserSeries.status == "followed",
            )
        )
    return SeriesDetailOut(
        **series_out(series, collection_id is not None),
        release_date=series.release_date,
        source=series.source,
        source_date=series.source_date,
        groups=[GroupOut(name=g.name, kind=g.kind, card_count=g.card_count) for g in series.groups],
        counts=counts,
        chase=[ChaseOut(card_ref_id=r.id, code=r.code, name=r.name, reason=r.reason) for r in chase],
        has_teams=has_teams,
        collection_id=collection_id,
    )


@router.get("/catalog/series/{series_id}/cards")
def series_cards(series_id: int, db: Db, v: int | None = None) -> Response:
    """Checklist complète d'une série. Demandée avec sa version, la réponse ne change jamais :
    le navigateur et le service worker la gardent (ENF-06)."""
    series = catalog.get_published(db, series_id)
    immutable = v == series.version
    cache = "public, max-age=31536000, immutable" if immutable else "no-cache"
    return Response(
        catalog.series_cards(db, series), media_type="application/json", headers={"Cache-Control": cache}
    )


# ------------------------------------------------------ demandes de séries


def _request_out(db, request: SeriesRequest, user: User) -> SeriesRequestOut:
    votes = set(
        db.scalars(select(SeriesRequestVote.user_id).where(SeriesRequestVote.request_id == request.id))
    )
    return SeriesRequestOut(
        id=request.id,
        name=request.name,
        url=request.url,
        status=request.status,
        admin_reply=request.admin_reply if request.user_id == user.id else "",
        votes=len(votes) + 1,
        mine=request.user_id == user.id,
        voted=user.id in votes,
        series_id=request.series_id,
        created_at=request.created_at,
    )


@router.get("/catalog/requests")
def list_requests(user: CurrentUser, db: Db) -> list[SeriesRequestOut]:
    """Les demandes de l'utilisateur, puis celles des autres encore ouvertes : il peut s'y associer
    plutôt que de créer un doublon."""
    rows = db.scalars(
        select(SeriesRequest)
        .where((SeriesRequest.user_id == user.id) | SeriesRequest.status.in_(("open", "accepted")))
        .order_by(SeriesRequest.created_at.desc())
        .limit(100)
    )
    return [_request_out(db, r, user) for r in rows]


@router.post("/catalog/requests", status_code=201)
def create_request(body: SeriesRequestIn, user: CurrentUser, db: Db) -> SeriesRequestOut:
    """F-34 : demander l'ajout d'une série."""
    rate_limit(db, f"request:{user.id}", 10, 86400)
    request = SeriesRequest(
        user_id=user.id, name=body.name.strip(), url=body.url.strip(), note=body.note.strip()
    )
    db.add(request)
    db.flush()
    return _request_out(db, request, user)


@router.post("/catalog/requests/{request_id}/vote", status_code=204)
def vote(request_id: int, user: CurrentUser, db: Db) -> None:
    request = db.get(SeriesRequest, request_id)
    if request is None or request.status not in ("open", "accepted"):
        raise NotFound()
    if request.user_id != user.id and not db.get(SeriesRequestVote, (request_id, user.id)):
        db.add(SeriesRequestVote(request_id=request_id, user_id=user.id))


# ------------------------------------------------------------ signalements


@router.post("/reports", status_code=201)
def report(body: ReportIn, request: Request, user: OptionalUser, db: Db) -> dict:
    """« Signaler une erreur » sur une référence (RG-03) ou un contenu public (F-45).

    Ouvert aux visiteurs pour les contenus publics, avec une limite de débit par adresse.
    """
    key = f"report:{user.id}" if user else f"report:{security.client_ip(request)}"
    rate_limit(db, key, 20 if user else 5, 86400)
    if body.kind == "catalog" and user is None:
        raise NotFound()
    target_id = None
    if body.pseudo:
        target_id = db.scalar(select(User.id).where(User.pseudo == body.pseudo, User.public_profile))
    if body.photo_id and target_id is None:
        target_id = db.scalar(select(Photo.user_id).where(Photo.id == body.photo_id))
    db.add(
        Report(
            reporter_id=user.id if user else None,
            kind=body.kind,
            series_id=body.series_id,
            card_ref_id=body.card_ref_id,
            target_user_id=target_id,
            photo_id=body.photo_id,
            message=body.message.strip(),
        )
    )
    return {"received": True}


def open_queue_count(db) -> int:
    requests = db.scalar(select(func.count()).where(SeriesRequest.status == "open"))
    reports = db.scalar(select(func.count()).where(Report.status == "open"))
    return (requests or 0) + (reports or 0)
