"""Partage et vues publiques (RG-02, F-42 à F-45).

Tout ce que ce module renvoie est destiné à des visiteurs. Il ne lit jamais un prix, une date
d'achat, une plateforme ou une quantité : ces colonnes n'apparaissent dans aucune requête ci-dessous.
"""

import uuid
from collections import defaultdict
from typing import Any

from sqlalchemy import exists, or_, select
from sqlalchemy.orm import Session, selectinload

from app.errors import NotFound
from app.models import (
    CardRef,
    ChaseMark,
    Photo,
    Purchase,
    SeriesGroup,
    ShareLink,
    User,
    UserCard,
    UserParallel,
    UserSeries,
)
from app.security import new_token, now
from app.services import collections


def public_owner(db: Session, pseudo: str) -> User:
    """F-42 : le profil n'existe pour les visiteurs que si l'utilisateur l'a activé."""
    user = db.scalar(select(User).where(User.pseudo == pseudo))
    if user is None or not user.public_profile or user.status != "active":
        raise NotFound(code="profile_not_found")
    return user


def shared_collections(db: Session, owner: User) -> list[UserSeries]:
    return list(
        db.scalars(
            select(UserSeries)
            .where(
                UserSeries.user_id == owner.id,
                UserSeries.shared,
                UserSeries.status == "followed",
                UserSeries.series_id.is_not(None),  # une collection personnelle n'est jamais partagée (F-35)
            )
            .order_by(UserSeries.created_at)
        )
    )


def link_collection(db: Session, token: str) -> UserSeries:
    """Collection désignée par un lien secret. CA-03 : un lien révoqué ne fonctionne plus, tout de suite."""
    link = db.scalar(select(ShareLink).where(ShareLink.token == token, ShareLink.revoked_at.is_(None)))
    collection = db.get(UserSeries, link.user_series_id) if link else None
    if collection is None or collection.series_id is None:
        raise NotFound(code="link_not_found")
    owner = db.get(User, collection.user_id)
    if owner is None or owner.status != "active":
        raise NotFound(code="link_not_found")
    return collection


def create_link(db: Session, user: User, collection: UserSeries) -> ShareLink:
    link = ShareLink(user_id=user.id, user_series_id=collection.id, token=new_token())
    db.add(link)
    db.flush()
    return link


def revoke_link(db: Session, user: User, link_id: int) -> None:
    link = db.get(ShareLink, link_id)
    if link is None or link.user_id != user.id:
        raise NotFound(code="link_not_found")
    link.revoked_at = now()


def collection_view(db: Session, owner: User, collection: UserSeries) -> dict[str, Any]:
    """Vue publique d'une collection (F-43, F-44) : les cartes possédées, en photo."""
    series = collection.series
    cards = db.scalars(
        select(UserCard)
        .join(CardRef, CardRef.id == UserCard.card_ref_id)
        .join(SeriesGroup, SeriesGroup.id == CardRef.group_id)
        .options(
            selectinload(UserCard.parallels), selectinload(UserCard.card_ref).selectinload(CardRef.teams)
        )
        .where(
            UserCard.user_id == owner.id,
            UserCard.owned,
            CardRef.series_id == series.id,
            CardRef.status == "active",
        )
        .order_by(SeriesGroup.position, CardRef.position)
    ).all()

    # Photo de l'achat quand la carte n'en a pas d'autre ; jamais celle d'une carte vendue.
    purchase_photos: dict[int, list[uuid.UUID]] = defaultdict(list)
    for ref_id, photo_id in db.execute(
        select(Purchase.card_ref_id, Purchase.photo_id).where(
            Purchase.user_id == owner.id,
            Purchase.series_id == series.id,
            Purchase.sold.is_(False),
            Purchase.applied,
            Purchase.photo_id.is_not(None),
        )
    ):
        purchase_photos[ref_id].append(photo_id)

    chase = set(
        db.scalars(
            select(ChaseMark.card_ref_id)
            .join(CardRef, CardRef.id == ChaseMark.card_ref_id)
            .where(CardRef.series_id == series.id)
        )
    )
    priority = collection.priority_team.name if collection.priority_team else None

    items = []
    owned_ids = set()
    for card in cards:
        ref = card.card_ref
        owned_ids.add(ref.id)
        live = [p for p in card.parallels if not p.sold]
        photo_ids = [card.photo_id, *(p.photo_id for p in live), *purchase_photos.get(ref.id, [])]
        photo_ids = list(dict.fromkeys(p for p in photo_ids if p))
        if collection.share_photos_only and not photo_ids:
            continue  # F-44 : par défaut, seulement les cartes avec photo
        teams = [t.name for t in ref.teams]
        items.append(
            {
                "card_ref_id": ref.id,
                "code": ref.code,
                "name": ref.name,
                "group": ref.group.name,
                "teams": teams,
                "chase": ref.id in chase,
                "parallels": [p.name for p in live],
                "photo_ids": photo_ids,
                "_priority": priority in teams,
            }
        )
    # RG-16 : l'équipe prioritaire en premier (tri stable, l'ordre de la checklist est conservé).
    items.sort(key=lambda item: not item.pop("_priority"))

    missing: list[dict[str, str]] = []
    if collection.share_missing:  # F-44 : utile pour les échanges
        refs = db.execute(
            select(CardRef.id, CardRef.code, CardRef.name)
            .join(SeriesGroup, SeriesGroup.id == CardRef.group_id)
            .where(CardRef.series_id == series.id, CardRef.status == "active")
            .order_by(SeriesGroup.position, CardRef.position)
        ).all()
        missing = [{"code": r.code, "name": r.name} for r in refs if r.id not in owned_ids]

    return {
        "id": collection.id,
        "series_id": series.id,
        "name": series.name,
        "short_name": collections.short_series_name(series),
        "universe_id": series.universe_id,
        "priority_team": priority,
        "cards": items,
        "missing": missing,
    }


def singles_view(db: Session, owner: User) -> list[dict[str, Any]]:
    """« Cartes à l'unité » : les cartes isolées qui ont une photo."""
    return [
        {
            "name": item["name"],
            "code": item["code"],
            "variant": item["variant"],
            "series_name": item["series_name"],
            "universe_id": item["universe_id"],
            "photo_ids": [item["photo_id"]],
        }
        for item in collections.isolated(db, owner)
        if item["photo_id"]
    ]


def profile_view(db: Session, owner: User) -> dict[str, Any]:
    return {
        "pseudo": owner.pseudo,
        "avatar_photo_id": owner.avatar_photo_id,
        "collections": [collection_view(db, owner, c) for c in shared_collections(db, owner)],
        "singles": singles_view(db, owner) if owner.share_singles else [],
    }


def photo_is_public(db: Session, photo: Photo, token: str | None) -> bool:
    """Une photo n'est servie à un visiteur que si elle illustre une carte actuellement partagée."""
    owner = db.get(User, photo.user_id)
    if owner is None or owner.status != "active":
        return False
    series_ids: set[int] = set()
    if owner.public_profile:
        if photo.id == owner.avatar_photo_id:
            return True
        series_ids.update(c.series_id for c in shared_collections(db, owner))
    if token:
        try:
            collection = link_collection(db, token)
        except NotFound:
            collection = None
        if collection and collection.user_id == owner.id:
            series_ids.add(collection.series_id)

    if series_ids:
        in_series = CardRef.series_id.in_(series_ids)
        visible = db.scalar(
            select(
                or_(
                    exists().where(
                        UserCard.photo_id == photo.id,
                        UserCard.owned,
                        UserCard.card_ref_id == CardRef.id,
                        in_series,
                    ),
                    exists().where(
                        UserParallel.photo_id == photo.id,
                        UserParallel.sold.is_(False),
                        UserParallel.user_card_id == UserCard.id,
                        UserCard.card_ref_id == CardRef.id,
                        in_series,
                    ),
                    exists().where(
                        Purchase.photo_id == photo.id,
                        Purchase.sold.is_(False),
                        Purchase.applied,
                        Purchase.series_id.in_(series_ids),
                    ),
                )
            )
        )
        if visible:
            return True
    if owner.public_profile and owner.share_singles:
        return any(item["photo_id"] == photo.id for item in collections.isolated(db, owner))
    return False
