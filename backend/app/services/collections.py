"""Collections et possession : RG-03 à RG-07, RG-09, RG-12, RG-15, RG-16."""

import uuid
from collections import defaultdict
from typing import Any

from sqlalchemy import and_, delete, func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.errors import AppError, Conflict, NotFound
from app.models import (
    CardRef,
    CardRefTeam,
    PersonalCard,
    Purchase,
    Series,
    SeriesGroup,
    ShareLink,
    Team,
    User,
    UserCard,
    UserParallel,
    UserSeries,
)
from app.rules import codes
from app.rules.progress import progress
from app.rules.variants import is_parallel_variant
from app.services import photos

MAX_PARALLELS = 30  # F-16
MAX_QUANTITY = 999  # RG-06
UNSET: Any = object()


# ------------------------------------------------------------------ accès


def get_collection(db: Session, user: User, collection_id: int) -> UserSeries:
    """RG-01 : la collection d'un autre utilisateur n'existe pas pour celui qui la demande."""
    collection = db.get(UserSeries, collection_id)
    if collection is None or collection.user_id != user.id:
        raise NotFound(code="collection_not_found")
    return collection


def get_ref(db: Session, card_ref_id: int) -> CardRef:
    ref = db.get(CardRef, card_ref_id)
    if ref is None or ref.status != "active" or ref.series.status != "published":
        raise NotFound(code="card_not_found")
    return ref


def is_followed(db: Session, user: User, series_id: int | None) -> bool:
    if series_id is None:
        return False
    return bool(
        db.scalar(
            select(UserSeries.id).where(
                UserSeries.user_id == user.id,
                UserSeries.series_id == series_id,
                UserSeries.status == "followed",
            )
        )
    )


def short_series_name(series: Series) -> str:
    """« Topps Chrome Star Wars 2026 » → « Chrome Star Wars » (F-05 : marque et saison en 2e ligne)."""
    name = series.name
    publisher = series.publisher.name
    if name.lower().startswith(publisher.lower() + " "):
        name = name[len(publisher) + 1 :]
    if series.season and name.endswith(" " + series.season):
        name = name[: -len(series.season) - 1]
    return name or series.name


# ------------------------------------------------------- suivre, ne plus suivre


def follow(db: Session, user: User, series_id: int) -> UserSeries:
    """RG-12 : suivre une série crée la collection et y coche les achats existants."""
    series = db.get(Series, series_id)
    if series is None or series.status != "published":
        raise NotFound(code="series_not_found")
    collection = db.scalar(
        select(UserSeries).where(UserSeries.user_id == user.id, UserSeries.series_id == series_id)
    )
    if collection is None:
        collection = UserSeries(user_id=user.id, series_id=series_id, universe_id=series.universe_id)
        db.add(collection)
    collection.status = "followed"
    db.flush()
    pending = db.scalars(
        select(Purchase).where(
            Purchase.user_id == user.id,
            Purchase.series_id == series_id,
            Purchase.card_ref_id.is_not(None),
            Purchase.applied.is_(False),
            Purchase.sold.is_(False),
        )
    ).all()
    for purchase in pending:
        apply_purchase(db, user, purchase)
    return collection


def create_personal(db: Session, user: User, name: str, universe_id: int | None, text: str) -> UserSeries:
    """F-35 : collection personnelle à partir d'une liste de codes, visible de l'utilisateur seul."""
    name = name.strip()
    if not name:
        raise AppError(code="name_required")
    try:
        entries = codes.parse_code_list(text)
    except codes.InvalidCode as error:
        raise AppError(str(error), code="code_invalid") from error
    collection = UserSeries(user_id=user.id, personal_name=name, universe_id=universe_id)
    db.add(collection)
    db.flush()
    db.add_all(
        PersonalCard(
            user_id=user.id,
            user_series_id=collection.id,
            code=code,
            code_key=codes.code_key(code),
            name=card_name,
            quantity=0,
        )
        for code, card_name in entries
    )
    return collection


def set_priority_team(db: Session, collection: UserSeries, team_id: int | None) -> None:
    """RG-16 : l'équipe doit apparaître dans la série."""
    if team_id is not None:
        in_series = db.scalar(
            select(CardRefTeam.team_id)
            .join(CardRef, CardRef.id == CardRefTeam.card_ref_id)
            .where(CardRef.series_id == collection.series_id, CardRefTeam.team_id == team_id)
            .limit(1)
        )
        if in_series is None:
            raise AppError(code="team_not_in_series")
    collection.priority_team_id = team_id


def delete_collection(db: Session, user: User, collection: UserSeries) -> None:
    """Supprime la collection et la possession de cette série ; les achats restent (RG-08 côté interface)."""
    photo_ids: set[uuid.UUID] = set()
    if collection.series_id is not None:
        cards = db.scalars(
            select(UserCard)
            .join(CardRef, CardRef.id == UserCard.card_ref_id)
            .where(UserCard.user_id == user.id, CardRef.series_id == collection.series_id)
        ).all()
        for card in cards:
            photo_ids.update(p for p in [card.photo_id, *(x.photo_id for x in card.parallels)] if p)
            db.delete(card)
        # Les achats redeviennent des cartes isolées.
        db.execute(
            update(Purchase)
            .where(Purchase.user_id == user.id, Purchase.series_id == collection.series_id)
            .values(applied=False, sale_removed_copy=False)
        )
    personal = db.scalars(select(PersonalCard).where(PersonalCard.user_series_id == collection.id)).all()
    photo_ids.update(p.photo_id for p in personal if p.photo_id)
    db.execute(delete(ShareLink).where(ShareLink.user_series_id == collection.id))
    db.delete(collection)
    db.flush()
    for photo_id in photo_ids:
        photos.release(db, photo_id)


# --------------------------------------------------------------- cartes


def get_card(db: Session, user: User, card_ref_id: int) -> UserCard | None:
    return db.scalar(select(UserCard).where(UserCard.user_id == user.id, UserCard.card_ref_id == card_ref_id))


def get_or_create_card(db: Session, user: User, card_ref_id: int) -> UserCard:
    get_ref(db, card_ref_id)
    db.execute(
        insert(UserCard).values(user_id=user.id, card_ref_id=card_ref_id).on_conflict_do_nothing()
    )  # sûr face à deux appels simultanés
    return db.scalars(
        select(UserCard).where(UserCard.user_id == user.id, UserCard.card_ref_id == card_ref_id)
    ).one()


def set_card(
    db: Session,
    user: User,
    card_ref_id: int,
    quantity: int | None = None,
    wanted: bool | None = None,
    note: str | None = None,
    photo_id: Any = UNSET,
) -> UserCard:
    """Règle la quantité (RG-06, RG-07), la marque personnelle (RG-17), la note et la photo."""
    card = get_or_create_card(db, user, card_ref_id)
    if quantity is not None:
        if not 0 <= quantity <= MAX_QUANTITY:
            raise AppError(code="quantity_out_of_range", max=MAX_QUANTITY)
        card.quantity = quantity
    if wanted is not None:
        card.wanted = wanted
    if note is not None:
        card.note = note[:2000]
    if photo_id is not UNSET and photo_id != card.photo_id:
        photos.owned(db, user, photo_id)
        previous, card.photo_id = card.photo_id, photo_id
        photos.release(db, previous)
    db.flush()
    db.refresh(card)
    return card


def _recount_parallels(db: Session, card: UserCard) -> None:
    db.flush()
    card.parallel_count = db.scalar(
        select(func.count()).where(UserParallel.user_card_id == card.id, UserParallel.sold.is_(False))
    )


def get_parallel(db: Session, user: User, parallel_id: int) -> UserParallel:
    parallel = db.get(UserParallel, parallel_id)
    if parallel is None or parallel.user_id != user.id:
        raise NotFound(code="parallel_not_found")
    return parallel


def add_parallel(
    db: Session,
    user: User,
    card_ref_id: int,
    name: str,
    photo_id: uuid.UUID | None = None,
    purchase_id: int | None = None,
) -> UserParallel:
    """RG-05 : posséder un parallèle rend la carte possédée ; un parallèle n'est jamais un double."""
    name = name.strip()[:80]
    if not name:
        raise AppError(code="name_required")
    card = get_or_create_card(db, user, card_ref_id)
    if len(card.parallels) >= MAX_PARALLELS:
        raise Conflict(code="too_many_parallels", max=MAX_PARALLELS)
    photos.owned(db, user, photo_id)
    parallel = UserParallel(
        user_card_id=card.id, user_id=user.id, name=name, photo_id=photo_id, purchase_id=purchase_id
    )
    card.parallels.append(parallel)
    _recount_parallels(db, card)
    return parallel


def update_parallel(
    db: Session, user: User, parallel: UserParallel, name: str | None = None, photo_id: Any = UNSET
) -> None:
    if name is not None:
        if not name.strip():
            raise AppError(code="name_required")
        parallel.name = name.strip()[:80]
    if photo_id is not UNSET and photo_id != parallel.photo_id:
        photos.owned(db, user, photo_id)
        previous, parallel.photo_id = parallel.photo_id, photo_id
        photos.release(db, previous)


def delete_parallel(db: Session, user: User, parallel: UserParallel) -> None:
    card, photo_id = parallel.user_card, parallel.photo_id
    card.parallels.remove(parallel)
    _recount_parallels(db, card)
    photos.release(db, photo_id)


# ----------------------------------------------------- achats ↔ collection


def linked_parallel(db: Session, purchase: Purchase) -> UserParallel | None:
    return db.scalar(select(UserParallel).where(UserParallel.purchase_id == purchase.id))


def apply_purchase(db: Session, user: User, purchase: Purchase) -> None:
    """RG-09 : un achat dans une série suivie est la carte de la collection.

    Variante parallèle → parallèle de cette carte, relié à l'achat ; sinon la carte est cochée
    (quantité 1 si elle manquait). Sans effet si l'achat est déjà reporté, vendu, ou sans référence.
    """
    if purchase.applied or purchase.sold or purchase.card_ref_id is None:
        return
    ref = get_ref(db, purchase.card_ref_id)
    as_parallel = purchase.as_parallel
    if as_parallel is None:
        as_parallel = is_parallel_variant(purchase.variant, ref.group.name)
    if as_parallel:
        add_parallel(db, user, ref.id, purchase.variant or "Parallèle", purchase.photo_id, purchase.id)
    else:
        card = get_or_create_card(db, user, ref.id)
        if card.quantity == 0:
            card.quantity = 1
    purchase.applied = True


def on_sale(db: Session, user: User, purchase: Purchase) -> None:
    """Une carte vendue n'est plus possédée (RG-02, RG-18) ; l'effet est réversible."""
    parallel = linked_parallel(db, purchase)
    if parallel is not None:
        parallel.sold = True
        _recount_parallels(db, parallel.user_card)
    elif purchase.applied and purchase.card_ref_id:
        card = get_card(db, user, purchase.card_ref_id)
        if card and card.quantity > 0:
            card.quantity -= 1
            purchase.sale_removed_copy = True


def on_sale_cancelled(db: Session, user: User, purchase: Purchase) -> None:
    parallel = linked_parallel(db, purchase)
    if parallel is not None:
        parallel.sold = False
        _recount_parallels(db, parallel.user_card)
    elif purchase.sale_removed_copy and purchase.card_ref_id:
        card = get_or_create_card(db, user, purchase.card_ref_id)
        card.quantity = min(card.quantity + 1, MAX_QUANTITY)
        purchase.sale_removed_copy = False


# -------------------------------------------------------- import d'une liste


def import_codes(db: Session, user: User, collection: UserSeries, text: str) -> dict[str, Any]:
    """F-12 : coche les codes déjà possédés (format F-37). Ne décoche jamais rien."""
    try:
        entries = codes.parse_code_list(text)
    except codes.InvalidCode as error:
        raise AppError(str(error), code="code_invalid") from error
    keys = {codes.code_key(code): code for code, _ in entries}

    if collection.series_id is None:
        existing = {
            c.code_key: c
            for c in db.scalars(select(PersonalCard).where(PersonalCard.user_series_id == collection.id))
        }
        added = 0
        for code, name in entries:
            key = codes.code_key(code)
            if key in existing:
                card = existing[key]
                added += card.quantity == 0
                card.quantity = max(card.quantity, 1)
            else:
                db.add(
                    PersonalCard(
                        user_id=user.id, user_series_id=collection.id, code=code, code_key=key, name=name
                    )
                )
                added += 1
        return {"checked": added, "already": len(entries) - added, "unknown": []}

    refs = db.execute(
        select(CardRef.id, CardRef.code_key).where(
            CardRef.series_id == collection.series_id, CardRef.code_key.in_(keys), CardRef.status == "active"
        )
    ).all()
    ref_ids = [r.id for r in refs]
    owned = set(
        db.scalars(
            select(UserCard.card_ref_id).where(
                UserCard.user_id == user.id, UserCard.card_ref_id.in_(ref_ids), UserCard.quantity > 0
            )
        )
    )
    to_check = [r.id for r in refs if r.id not in owned]
    if to_check:
        statement = insert(UserCard).values(
            [{"user_id": user.id, "card_ref_id": i, "quantity": 1} for i in to_check]
        )
        db.execute(
            statement.on_conflict_do_update(
                index_elements=["user_id", "card_ref_id"], set_={"quantity": 1, "updated_at": func.now()}
            )
        )
    known = {r.code_key for r in refs}
    return {
        "checked": len(to_check),
        "already": len(owned),
        "unknown": [code for key, code in keys.items() if key not in known],
    }


# ------------------------------------------------------------ avancement


def _team_counts(db: Session, user: User, series_id: int, team_id: int) -> tuple[dict, dict]:
    rows = db.execute(
        select(
            SeriesGroup.kind,
            func.count().label("total"),
            func.count().filter(UserCard.owned).label("owned"),
        )
        .select_from(CardRef)
        .join(CardRefTeam, CardRefTeam.card_ref_id == CardRef.id)
        .join(SeriesGroup, SeriesGroup.id == CardRef.group_id)
        .outerjoin(UserCard, and_(UserCard.card_ref_id == CardRef.id, UserCard.user_id == user.id))
        .where(CardRef.series_id == series_id, CardRefTeam.team_id == team_id, CardRef.status == "active")
        .group_by(SeriesGroup.kind)
    ).all()
    return {r.kind: r.total for r in rows}, {r.kind: r.owned for r in rows}


def summaries(db: Session, user: User) -> list[dict[str, Any]]:
    """Lignes de l'écran « Mes collections » (F-05), avancement selon RG-15 et RG-16."""
    collections = db.scalars(
        select(UserSeries).where(UserSeries.user_id == user.id).order_by(UserSeries.created_at)
    ).all()
    series_ids = [c.series_id for c in collections if c.series_id]

    totals: dict[int, dict[str, int]] = defaultdict(dict)
    for series_id, kind, count in db.execute(
        select(SeriesGroup.series_id, SeriesGroup.kind, func.sum(SeriesGroup.card_count))
        .where(SeriesGroup.series_id.in_(series_ids))
        .group_by(SeriesGroup.series_id, SeriesGroup.kind)
    ):
        totals[series_id][kind] = int(count)

    owned: dict[int, dict[str, int]] = defaultdict(dict)
    for series_id, kind, count in db.execute(
        select(CardRef.series_id, SeriesGroup.kind, func.count())
        .select_from(UserCard)
        .join(CardRef, CardRef.id == UserCard.card_ref_id)
        .join(SeriesGroup, SeriesGroup.id == CardRef.group_id)
        .where(UserCard.user_id == user.id, UserCard.owned, CardRef.status == "active")
        .group_by(CardRef.series_id, SeriesGroup.kind)
    ):
        owned[series_id][kind] = count

    personal = {
        row.user_series_id: row
        for row in db.execute(
            select(
                PersonalCard.user_series_id,
                func.count().label("total"),
                func.count().filter(PersonalCard.quantity > 0).label("owned"),
            )
            .where(PersonalCard.user_id == user.id)
            .group_by(PersonalCard.user_series_id)
        )
    }

    result = []
    for collection in collections:
        series = collection.series
        if series is None:
            row = personal.get(collection.id)
            state = progress({"base": row.total if row else 0}, {"base": row.owned if row else 0})
        elif collection.priority_team_id:
            state = progress(*_team_counts(db, user, series.id, collection.priority_team_id))
        else:
            state = progress(totals[series.id], owned[series.id])
        result.append(
            {
                "id": collection.id,
                "series_id": collection.series_id,
                "name": series.name if series else collection.personal_name,
                "short_name": short_series_name(series) if series else collection.personal_name,
                "universe_id": collection.universe_id,
                "publisher": series.publisher.name if series else "",
                "season": series.season if series else "",
                "status": collection.status,
                "priority_team": collection.priority_team.name if collection.priority_team else None,
                "shared": collection.shared,
                "owned": state.owned,
                "total": state.total,
                "percent": state.percent,
                "label": state.label,
            }
        )
    return result


def state(db: Session, user: User, collection: UserSeries) -> dict[str, Any]:
    """État de possession d'une collection : seulement les cartes que l'utilisateur a touchées."""
    cards: dict[int, list[int]] = {}
    if collection.series_id is not None:
        parallel_photo = (
            select(func.count())
            .where(UserParallel.user_card_id == UserCard.id, UserParallel.photo_id.is_not(None))
            .correlate(UserCard)
            .scalar_subquery()
        )
        rows = db.execute(
            select(
                UserCard.card_ref_id,
                UserCard.quantity,
                UserCard.parallel_count,
                UserCard.photo_id,
                UserCard.wanted,
                parallel_photo,
            )
            .join(CardRef, CardRef.id == UserCard.card_ref_id)
            .where(UserCard.user_id == user.id, CardRef.series_id == collection.series_id)
        )
        # [quantité, parallèles, photo, recherchée] — format compact, jusqu'à 10 000 cartes.
        cards = {
            ref_id: [quantity, parallels, int(bool(photo_id) or n_photos > 0), int(wanted)]
            for ref_id, quantity, parallels, photo_id, wanted, n_photos in rows
        }
    personal = db.scalars(
        select(PersonalCard).where(PersonalCard.user_series_id == collection.id).order_by(PersonalCard.id)
    ).all()
    personal.sort(key=lambda c: codes.natural_sort_key(c.code))
    return {"cards": cards, "personal": personal}


def teams_of_series(db: Session, series_id: int) -> list[Team]:
    return list(
        db.scalars(
            select(Team)
            .where(
                Team.id.in_(
                    select(CardRefTeam.team_id)
                    .join(CardRef, CardRef.id == CardRefTeam.card_ref_id)
                    .where(CardRef.series_id == series_id)
                )
            )
            .order_by(Team.name)
        )
    )


# ---------------------------------------------------------- cartes isolées


def isolated(db: Session, user: User) -> list[dict[str, Any]]:
    """RG-11, RG-12 : cartes possédées d'une série que l'utilisateur ne complète pas.

    Deux sources : les achats non reportés dans une collection, et les cartes possédées d'une
    série en réserve ou jamais suivie.
    """
    items: list[dict[str, Any]] = []
    purchases = db.scalars(
        select(Purchase)
        .where(Purchase.user_id == user.id, Purchase.applied.is_(False), Purchase.sold.is_(False))
        .order_by(Purchase.created_at.desc())
    ).all()
    for p in purchases:
        items.append(
            {
                "purchase_id": p.id,
                "card_ref_id": p.card_ref_id,
                "name": p.name,
                "code": p.code,
                "variant": p.variant,
                "series_id": p.series_id,
                "series_name": p.series_name,
                "universe_id": p.universe_id,
                "photo_id": p.photo_id,
                "can_follow": p.series is not None and p.series.status == "published",
            }
        )

    followed = select(UserSeries.series_id).where(
        UserSeries.user_id == user.id, UserSeries.status == "followed", UserSeries.series_id.is_not(None)
    )
    cards = db.scalars(
        select(UserCard)
        .join(CardRef, CardRef.id == UserCard.card_ref_id)
        .where(UserCard.user_id == user.id, UserCard.owned, CardRef.series_id.not_in(followed))
        .order_by(UserCard.updated_at.desc())
    ).all()
    for card in cards:
        ref = card.card_ref
        live = [x for x in card.parallels if not x.sold]
        photo_id = card.photo_id or next((x.photo_id for x in live if x.photo_id), None)
        items.append(
            {
                "purchase_id": None,
                "card_ref_id": ref.id,
                "name": ref.name,
                "code": ref.code,
                "variant": ", ".join(x.name for x in live),
                "series_id": ref.series_id,
                "series_name": ref.series.name,
                "universe_id": ref.series.universe_id,
                "photo_id": photo_id,
                "can_follow": ref.series.status == "published",
            }
        )
    return items
