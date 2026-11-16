"""Collections, cartes, parallèles, cartes isolées, recherche (section 5)."""

from typing import Literal

from fastapi import APIRouter, Query, Response
from sqlalchemy import func, select

from app.deps import CurrentUser, Db
from app.errors import AppError, Conflict, NotFound
from app.models import (
    CardRef,
    ChaseMark,
    OfficialParallel,
    PersonalCard,
    Purchase,
    Team,
    UserCard,
    UserParallel,
    UserSeries,
)
from app.rules import codes
from app.schemas import (
    CardOut,
    CardStateIn,
    CollectionDetailOut,
    CollectionIn,
    CollectionOut,
    FollowIn,
    HomeOut,
    ImportCodesIn,
    ImportCodesOut,
    IsolatedOut,
    ParallelIn,
    ParallelOut,
    ParallelPurchaseOut,
    PersonalCardIn,
    PersonalCardOut,
    PersonalCollectionIn,
    SearchOut,
)
from app.services import catalog, collections, photos

router = APIRouter(tags=["collections"])


def _summary(db, user, collection_id: int) -> dict:
    return next(s for s in collections.summaries(db, user) if s["id"] == collection_id)


@router.get("/collections")
def home(user: CurrentUser, db: Db) -> HomeOut:
    """F-04 à F-06 : « Mes collections ». Les séries en réserve sont dans les cartes isolées."""
    isolated = collections.isolated(db, user)
    return HomeOut(
        collections=[s for s in collections.summaries(db, user) if s["status"] == "followed"],
        isolated_cards=len(isolated),
        isolated_series=len({i["series_name"] for i in isolated}),
    )


@router.post("/collections", status_code=201)
def follow(body: FollowIn, user: CurrentUser, db: Db) -> CollectionOut:
    collection = collections.follow(db, user, body.series_id)
    return CollectionOut(**_summary(db, user, collection.id))


@router.post("/collections/personal", status_code=201)
def create_personal(body: PersonalCollectionIn, user: CurrentUser, db: Db) -> CollectionOut:
    collection = collections.create_personal(db, user, body.name, body.universe_id, body.codes)
    db.flush()
    return CollectionOut(**_summary(db, user, collection.id))


@router.get("/collections/{collection_id}")
def detail(collection_id: int, user: CurrentUser, db: Db) -> CollectionDetailOut:
    collection = collections.get_collection(db, user, collection_id)
    state = collections.state(db, user, collection)
    return CollectionDetailOut(
        **_summary(db, user, collection.id),
        series_version=collection.series.version if collection.series else None,
        share_photos_only=collection.share_photos_only,
        share_missing=collection.share_missing,
        cards=state["cards"],
        personal=[PersonalCardOut.model_validate(p) for p in state["personal"]],
    )


@router.patch("/collections/{collection_id}")
def update(collection_id: int, body: CollectionIn, user: CurrentUser, db: Db) -> CollectionOut:
    collection = collections.get_collection(db, user, collection_id)
    if body.status:
        collection.status = body.status  # RG-12 : « Ne plus suivre » met en réserve, sans rien perdre
        if body.status == "followed" and collection.series_id:
            collections.follow(db, user, collection.series_id)
    if body.clear_priority_team:
        collections.set_priority_team(db, collection, None)
    elif body.priority_team:
        team = db.scalar(
            select(Team).where(Team.universe_id == collection.universe_id, Team.name == body.priority_team)
        )
        if team is None:
            raise AppError(code="team_not_in_series")
        collections.set_priority_team(db, collection, team.id)
    if body.shared is not None or body.share_photos_only is not None or body.share_missing is not None:
        if collection.series_id is None:
            raise AppError(code="personal_collection_not_shareable")
        for field in ("shared", "share_photos_only", "share_missing"):
            if getattr(body, field) is not None:
                setattr(collection, field, getattr(body, field))
    db.flush()
    return CollectionOut(**_summary(db, user, collection.id))


@router.delete("/collections/{collection_id}", status_code=204)
def delete(collection_id: int, user: CurrentUser, db: Db) -> None:
    collections.delete_collection(db, user, collections.get_collection(db, user, collection_id))


@router.post("/collections/{collection_id}/import-codes")
def import_codes(collection_id: int, body: ImportCodesIn, user: CurrentUser, db: Db) -> ImportCodesOut:
    collection = collections.get_collection(db, user, collection_id)
    return ImportCodesOut(**collections.import_codes(db, user, collection, body.text))


@router.post("/collections/{collection_id}/attach")
def attach_to_catalog(collection_id: int, body: FollowIn, user: CurrentUser, db: Db) -> ImportCodesOut:
    """F-35 : rattache une collection personnelle à la série du catalogue, une fois celle-ci publiée.

    Les cartes possédées sont cochées par leur code ; celles que la série ne connaît pas restent
    des cartes personnelles de la nouvelle collection.
    """
    personal = collections.get_collection(db, user, collection_id)
    if personal.series_id is not None:
        raise Conflict(code="already_attached")
    target = collections.follow(db, user, body.series_id)
    cards = db.scalars(select(PersonalCard).where(PersonalCard.user_series_id == personal.id)).all()
    refs = dict(
        db.execute(
            select(CardRef.code_key, CardRef.id).where(
                CardRef.series_id == body.series_id, CardRef.status == "active"
            )
        ).all()
    )
    checked, unknown = 0, []
    for card in cards:
        ref_id = refs.get(card.code_key)
        if ref_id is None:
            card.user_series_id = target.id
            unknown.append(card.code)
            continue
        if card.quantity > 0 or card.photo_id or card.note:
            state = collections.get_or_create_card(db, user, ref_id)
            state.quantity = max(state.quantity, card.quantity)
            state.photo_id = state.photo_id or card.photo_id
            state.note = state.note or card.note
            checked += card.quantity > 0
        db.delete(card)
    db.flush()
    db.delete(personal)
    return ImportCodesOut(checked=checked, already=0, unknown=unknown)


@router.get("/collections/{collection_id}/codes")
def copy_codes(
    collection_id: int,
    user: CurrentUser,
    db: Db,
    what: Literal["missing", "doubles"] = "missing",
    compact: bool = False,
    team: str | None = None,
) -> dict:
    """F-12 : « Copier les manquantes » et « Copier les doubles ». L'interface fait le même calcul sur
    les cartes affichées ; ce point d'accès sert à l'export et aux séries non chargées."""
    collection = collections.get_collection(db, user, collection_id)
    if collection.series_id is None:
        raise AppError(code="catalog_collection_required")
    statement = (
        select(CardRef.code, func.coalesce(UserCard.quantity, 0), func.coalesce(UserCard.owned, False))
        .outerjoin(UserCard, (UserCard.card_ref_id == CardRef.id) & (UserCard.user_id == user.id))
        .where(CardRef.series_id == collection.series_id, CardRef.status == "active")
    )
    rows = db.execute(statement).all()
    if what == "missing":
        selected = [code for code, _, owned in rows if not owned]
    else:
        selected = [code for code, quantity, _ in rows if quantity > 1]
    return {"count": len(selected), "text": codes.format_code_list(selected, compact)}


# ----------------------------------------------------- cartes personnelles


@router.post("/collections/{collection_id}/personal-cards", status_code=201)
def add_personal_card(collection_id: int, body: PersonalCardIn, user: CurrentUser, db: Db) -> PersonalCardOut:
    """RG-03 : carte hors catalogue, visible de l'utilisateur seul."""
    collection = collections.get_collection(db, user, collection_id)
    try:
        code = codes.normalize_code(body.code or "")
    except codes.InvalidCode as error:
        raise AppError(str(error), code="code_invalid") from error
    key = codes.code_key(code)
    if db.scalar(
        select(PersonalCard).where(PersonalCard.user_series_id == collection.id, PersonalCard.code_key == key)
    ):
        raise Conflict(code="code_taken")
    if collection.series_id and db.scalar(
        select(CardRef.id).where(CardRef.series_id == collection.series_id, CardRef.code_key == key)
    ):
        raise Conflict(code="code_in_catalog")
    photos.owned(db, user, body.photo_id)
    card = PersonalCard(
        user_id=user.id,
        user_series_id=collection.id,
        code=code,
        code_key=key,
        name=(body.name or "").strip(),
        quantity=body.quantity if body.quantity is not None else 1,
        photo_id=body.photo_id,
        note=body.note or "",
    )
    db.add(card)
    db.flush()
    return PersonalCardOut.model_validate(card)


def _personal_card(db, user, card_id: int) -> PersonalCard:
    card = db.get(PersonalCard, card_id)
    if card is None or card.user_id != user.id:
        raise NotFound(code="card_not_found")
    return card


@router.patch("/personal-cards/{card_id}")
def update_personal_card(card_id: int, body: PersonalCardIn, user: CurrentUser, db: Db) -> PersonalCardOut:
    card = _personal_card(db, user, card_id)
    data = body.model_dump(exclude_unset=True)
    if "photo_id" in data and data["photo_id"] != card.photo_id:
        photos.owned(db, user, data["photo_id"])
        previous, card.photo_id = card.photo_id, data["photo_id"]
        photos.release(db, previous)
    for field in ("name", "note"):
        if field in data:
            setattr(card, field, data[field] or "")
    if data.get("quantity") is not None:
        card.quantity = data["quantity"]
    db.flush()
    return PersonalCardOut.model_validate(card)


@router.delete("/personal-cards/{card_id}", status_code=204)
def delete_personal_card(card_id: int, user: CurrentUser, db: Db) -> None:
    card = _personal_card(db, user, card_id)
    photo_id = card.photo_id
    db.delete(card)
    photos.release(db, photo_id)


# ------------------------------------------------------- fiche d'une carte


def _parallel_out(db, parallel: UserParallel) -> ParallelOut:
    purchase = db.get(Purchase, parallel.purchase_id) if parallel.purchase_id else None
    return ParallelOut(
        id=parallel.id,
        name=parallel.name,
        photo_id=parallel.photo_id,
        sold=parallel.sold,
        purchase=ParallelPurchaseOut(id=purchase.id, price=purchase.price) if purchase else None,
    )


def _card_out(db, user, ref: CardRef) -> CardOut:
    card = collections.get_card(db, user, ref.id)
    collection_id = db.scalar(
        select(UserSeries.id).where(UserSeries.user_id == user.id, UserSeries.series_id == ref.series_id)
    )
    purchase_photo = db.scalar(
        select(Purchase.photo_id)
        .where(
            Purchase.user_id == user.id,
            Purchase.card_ref_id == ref.id,
            Purchase.sold.is_(False),
            Purchase.photo_id.is_not(None),
        )
        .order_by(Purchase.created_at.desc())
        .limit(1)
    )
    official = db.scalars(
        select(OfficialParallel.name)
        .where(
            OfficialParallel.series_id == ref.series_id,
            (OfficialParallel.group_id == ref.group_id) | OfficialParallel.group_id.is_(None),
        )
        .order_by(OfficialParallel.id)
    ).all()
    return CardOut(
        card_ref_id=ref.id,
        code=ref.code,
        name=ref.name,
        rookie=ref.rookie,
        series_id=ref.series_id,
        series_name=ref.series.name,
        group=ref.group.name,
        kind=ref.group.kind,
        teams=[t.name for t in ref.teams],
        chase_reason=db.scalar(select(ChaseMark.reason).where(ChaseMark.card_ref_id == ref.id)),
        collection_id=collection_id,
        quantity=card.quantity if card else 0,
        wanted=card.wanted if card else False,
        note=card.note if card else "",
        photo_id=card.photo_id if card else None,
        purchase_photo_id=purchase_photo,
        parallels=[_parallel_out(db, p) for p in card.parallels] if card else [],
        official_parallels=list(official),
    )


@router.get("/cards/{card_ref_id}")
def card(card_ref_id: int, user: CurrentUser, db: Db) -> CardOut:
    return _card_out(db, user, collections.get_ref(db, card_ref_id))


@router.put("/cards/{card_ref_id}")
def set_card(card_ref_id: int, body: CardStateIn, user: CurrentUser, db: Db) -> CardOut:
    """RG-07 : la quantité est toujours fixée explicitement — aucun appel ne « bascule » une case."""
    data = body.model_dump(exclude_unset=True)
    photo = data.pop("photo_id", collections.UNSET)
    collections.set_card(db, user, card_ref_id, photo_id=photo, **data)
    return _card_out(db, user, collections.get_ref(db, card_ref_id))


@router.post("/cards/{card_ref_id}/parallels", status_code=201)
def add_parallel(card_ref_id: int, body: ParallelIn, user: CurrentUser, db: Db) -> ParallelOut:
    parallel = collections.add_parallel(db, user, card_ref_id, body.name or "", body.photo_id)
    db.flush()
    return _parallel_out(db, parallel)


@router.patch("/parallels/{parallel_id}")
def update_parallel(parallel_id: int, body: ParallelIn, user: CurrentUser, db: Db) -> ParallelOut:
    parallel = collections.get_parallel(db, user, parallel_id)
    data = body.model_dump(exclude_unset=True)
    collections.update_parallel(db, user, parallel, data.get("name"), data.get("photo_id", collections.UNSET))
    return _parallel_out(db, parallel)


@router.delete("/parallels/{parallel_id}", status_code=204)
def delete_parallel(parallel_id: int, user: CurrentUser, db: Db) -> None:
    collections.delete_parallel(db, user, collections.get_parallel(db, user, parallel_id))


# ------------------------------------------- cartes isolées et recherche


@router.get("/isolated")
def isolated(user: CurrentUser, db: Db) -> list[IsolatedOut]:
    return [IsolatedOut(**item) for item in collections.isolated(db, user)]


@router.get("/search")
def search(
    user: CurrentUser,
    db: Db,
    response: Response,
    q: str = Query("", max_length=100),
    scope: Literal["mine", "catalog"] = "mine",
    only: Literal["all", "owned", "missing"] = "all",
) -> SearchOut:
    response.headers["Cache-Control"] = "no-store"
    if scope == "catalog":
        return SearchOut(**catalog.search_catalog(db, q))
    return SearchOut(**catalog.search_mine(db, user, q, only))
