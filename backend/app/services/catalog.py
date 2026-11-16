"""Catalogue commun : lecture, recherche, demandes de séries (RG-03, F-25, F-32 à F-34)."""

import json
from collections import defaultdict
from typing import Any

from sqlalchemy import Text, and_, cast, func, literal, select, update
from sqlalchemy.dialects.postgresql import TSQUERY
from sqlalchemy.orm import Session

from app.errors import NotFound
from app.models import (
    CardRef,
    CardRefTeam,
    ChaseMark,
    Purchase,
    Series,
    SeriesGroup,
    Team,
    User,
    UserCard,
    UserSeries,
)
from app.rules import search

SEARCH_LIMIT = 150  # F-25

_payload_cache: dict[tuple[int, int], bytes] = {}


def get_published(db: Session, series_id: int) -> Series:
    series = db.get(Series, series_id)
    if series is None or series.status != "published":
        raise NotFound(code="series_not_found")
    return series


def list_series(
    db: Session,
    universe_id: int | None = None,
    publisher_id: int | None = None,
    season: str = "",
    q: str = "",
) -> list[Series]:
    """F-32 : parcourir le catalogue par univers, éditeur et saison, et y chercher une série."""
    statement = select(Series).where(Series.status == "published")
    if universe_id:
        statement = statement.where(Series.universe_id == universe_id)
    if publisher_id:
        statement = statement.where(Series.publisher_id == publisher_id)
    if season:
        statement = statement.where(Series.season == season)
    for word in search.fold(q).split():
        statement = statement.where(func.unaccent(cast(Series.name, Text)).ilike(f"%{word}%"))
    return list(db.scalars(statement.order_by(Series.season.desc(), Series.name)))


def series_cards(db: Session, series: Series) -> bytes:
    """Checklist d'une série en tableaux compacts, mise en cache par version.

    Format : `cards` = [id, code, nom, indice de sous-série, [indices d'équipes], drapeaux]
    (drapeaux : 1 = rookie, 2 = recherchée éditoriale).
    """
    key = (series.id, series.version)
    if key in _payload_cache:
        return _payload_cache[key]

    groups = list(series.groups)
    group_index = {g.id: i for i, g in enumerate(groups)}
    team_rows = db.execute(
        select(CardRefTeam.card_ref_id, Team.name)
        .join(Team, Team.id == CardRefTeam.team_id)
        .join(CardRef, CardRef.id == CardRefTeam.card_ref_id)
        .where(CardRef.series_id == series.id)
    ).all()
    teams = sorted({name for _, name in team_rows})
    team_index = {name: i for i, name in enumerate(teams)}
    card_teams: dict[int, list[int]] = defaultdict(list)
    for ref_id, name in team_rows:
        card_teams[ref_id].append(team_index[name])

    chase = dict(
        db.execute(
            select(ChaseMark.card_ref_id, ChaseMark.reason)
            .join(CardRef, CardRef.id == ChaseMark.card_ref_id)
            .where(CardRef.series_id == series.id)
        ).all()
    )
    rows = db.execute(
        select(CardRef.id, CardRef.code, CardRef.name, CardRef.group_id, CardRef.rookie)
        .join(SeriesGroup, SeriesGroup.id == CardRef.group_id)
        .where(CardRef.series_id == series.id, CardRef.status == "active")
        .order_by(SeriesGroup.position, CardRef.position)
    ).all()
    payload = {
        "series_id": series.id,
        "version": series.version,
        "groups": [{"id": g.id, "name": g.name, "kind": g.kind} for g in groups],
        "teams": teams,
        "cards": [
            [
                r.id,
                r.code,
                r.name,
                group_index[r.group_id],
                sorted(card_teams.get(r.id, [])),
                r.rookie + 2 * (r.id in chase),
            ]
            for r in rows
        ],
        "chase": {str(ref_id): reason for ref_id, reason in chase.items()},
    }
    data = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()
    if len(_payload_cache) >= 64:
        _payload_cache.pop(next(iter(_payload_cache)))
    _payload_cache[key] = data
    return data


def reindex_series(db: Session, series_id: int) -> None:
    """Recalcule les jetons de recherche et les compteurs d'une série (après publication)."""
    teams: dict[int, list[str]] = defaultdict(list)
    for ref_id, name in db.execute(
        select(CardRefTeam.card_ref_id, Team.name)
        .join(Team, Team.id == CardRefTeam.team_id)
        .join(CardRef, CardRef.id == CardRefTeam.card_ref_id)
        .where(CardRef.series_id == series_id)
    ):
        teams[ref_id].append(name)
    rows = db.execute(
        select(CardRef.id, CardRef.code, CardRef.name, SeriesGroup.name.label("group_name"))
        .join(SeriesGroup, SeriesGroup.id == CardRef.group_id)
        .where(CardRef.series_id == series_id)
    ).all()
    if rows:
        db.execute(
            update(CardRef),
            [
                {
                    "id": r.id,
                    "search_tokens": search.card_tokens(r.code, r.name, r.group_name, teams.get(r.id)),
                }
                for r in rows
            ],
        )
    counts = dict(
        db.execute(
            select(CardRef.group_id, func.count())
            .where(CardRef.series_id == series_id, CardRef.status == "active")
            .group_by(CardRef.group_id)
        ).all()
    )
    for group in db.scalars(select(SeriesGroup).where(SeriesGroup.series_id == series_id)):
        group.card_count = counts.get(group.id, 0)
    series = db.get(Series, series_id)
    series.card_count = sum(counts.values())


# ------------------------------------------------------------- recherche


def _match(terms: list[tuple[str, str]]):
    return CardRef.search_tsv.op("@@")(cast(literal(search.to_tsquery(terms)), TSQUERY))


def search_mine(db: Session, user: User, query: str, only: str = "all") -> dict[str, Any]:
    """F-25 : recherche sur les collections de l'utilisateur (suivies et en réserve) et ses achats
    hors collection. Détenues en premier ; 150 résultats au plus."""
    terms = search.parse_query(query)
    empty = {"results": [], "counts": {"all": 0, "owned": 0, "missing": 0}, "truncated": False}
    if not terms:
        return empty

    is_owned = func.coalesce(UserCard.owned, False)
    base = (
        select(CardRef, UserCard, UserSeries.id.label("collection_id"))
        .join(UserSeries, and_(UserSeries.series_id == CardRef.series_id, UserSeries.user_id == user.id))
        .outerjoin(UserCard, and_(UserCard.card_ref_id == CardRef.id, UserCard.user_id == user.id))
        .where(CardRef.status == "active", _match(terms))
    )
    total, owned_count = db.execute(
        select(func.count(), func.count().filter(is_owned))
        .select_from(CardRef)
        .join(UserSeries, and_(UserSeries.series_id == CardRef.series_id, UserSeries.user_id == user.id))
        .outerjoin(UserCard, and_(UserCard.card_ref_id == CardRef.id, UserCard.user_id == user.id))
        .where(CardRef.status == "active", _match(terms))
    ).one()

    loose = [
        p
        for p in db.scalars(
            select(Purchase).where(
                Purchase.user_id == user.id, Purchase.applied.is_(False), Purchase.sold.is_(False)
            )
        )
        if search.matches(terms, search.card_tokens(p.code, p.name, p.variant, [p.series_name]))
    ]

    statement = base
    if only == "owned":
        statement = statement.where(is_owned)
    elif only == "missing":
        statement = statement.where(~is_owned)
    rows = db.execute(
        statement.order_by(is_owned.desc(), CardRef.series_id, CardRef.position).limit(SEARCH_LIMIT + 1)
    ).all()

    results: list[dict[str, Any]] = []
    if only != "missing":
        results += [
            {
                "kind": "purchase",
                "purchase_id": p.id,
                "code": p.code,
                "name": p.name,
                "detail": p.variant,
                "series_name": p.series_name,
                "owned": True,
                "photo_id": p.photo_id,
            }
            for p in loose
        ]
    results += [
        {
            "kind": "card",
            "card_ref_id": ref.id,
            "collection_id": collection_id,
            "code": ref.code,
            "name": ref.name,
            "detail": ref.group.name,
            "series_name": ref.series.name,
            "owned": bool(card and card.owned),
            "photo_id": card.photo_id if card else None,
        }
        for ref, card, collection_id in rows
    ]
    return {
        "results": results[:SEARCH_LIMIT],
        "counts": {
            "all": total + len(loose),
            "owned": owned_count + len(loose),
            "missing": total - owned_count,
        },
        "truncated": len(results) > SEARCH_LIMIT,
    }


def search_catalog(db: Session, query: str) -> dict[str, Any]:
    """Second onglet de la recherche : tout le catalogue publié."""
    terms = search.parse_query(query)
    if not terms:
        return {"results": [], "truncated": False}
    rows = db.scalars(
        select(CardRef)
        .join(Series, Series.id == CardRef.series_id)
        .where(Series.status == "published", CardRef.status == "active", _match(terms))
        .order_by(Series.name, CardRef.position)
        .limit(SEARCH_LIMIT + 1)
    ).all()
    return {
        "results": [
            {
                "kind": "card",
                "card_ref_id": r.id,
                "code": r.code,
                "name": r.name,
                "detail": r.group.name,
                "series_id": r.series_id,
                "series_name": r.series.name,
            }
            for r in rows[:SEARCH_LIMIT]
        ],
        "truncated": len(rows) > SEARCH_LIMIT,
    }
