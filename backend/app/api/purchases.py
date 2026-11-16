"""Achats, ventes et bilan (F-22 à F-24)."""

from typing import Literal

from fastapi import APIRouter
from sqlalchemy import select

from app.deps import CurrentUser, Db
from app.models import Purchase, UserSeries
from app.schemas import PurchaseIn, PurchaseOut, SaleIn, SummaryOut
from app.services import collections, purchases

router = APIRouter(prefix="/purchases", tags=["purchases"])


def _out(db, user, purchase: Purchase, detailed: bool = False) -> PurchaseOut:
    out = PurchaseOut.model_validate(purchase)
    out.result = purchases.result(purchase)
    out.is_isolated = not purchase.applied and not purchase.sold  # RG-11
    if detailed:
        series = purchase.series
        out.can_follow = out.is_isolated and series is not None and series.status == "published"
        parallel = collections.linked_parallel(db, purchase)
        out.parallel_id = parallel.id if parallel else None
        if purchase.series_id:
            out.collection_id = db.scalar(
                select(UserSeries.id).where(
                    UserSeries.user_id == user.id, UserSeries.series_id == purchase.series_id
                )
            )
    return out


@router.get("")
def list_purchases(
    user: CurrentUser, db: Db, only: Literal["all", "kept", "sold"] = "all", limit: int = 100, offset: int = 0
) -> list[PurchaseOut]:
    """F-22 : du plus récent au plus ancien ; filtres « Toutes », « En collection », « Vendues »."""
    statement = select(Purchase).where(Purchase.user_id == user.id)
    if only != "all":
        statement = statement.where(Purchase.sold.is_(only == "sold"))
    rows = db.scalars(
        statement.order_by(Purchase.bought_on.desc().nulls_last(), Purchase.id.desc())
        .limit(min(limit, 200))
        .offset(offset)
    )
    return [_out(db, user, p) for p in rows]


@router.get("/summary")
def summary(user: CurrentUser, db: Db) -> SummaryOut:
    return SummaryOut(**purchases.summary(db, user))


@router.get("/platforms")
def platforms(user: CurrentUser, db: Db) -> list[str]:
    return purchases.platforms(db, user)


@router.post("", status_code=201)
def create(body: PurchaseIn, user: CurrentUser, db: Db) -> PurchaseOut:
    purchase = purchases.create(db, user, body.model_dump(exclude_unset=True))
    db.flush()
    return _out(db, user, purchase, detailed=True)


@router.get("/{purchase_id}")
def get(purchase_id: int, user: CurrentUser, db: Db) -> PurchaseOut:
    return _out(db, user, purchases.get(db, user, purchase_id), detailed=True)


@router.patch("/{purchase_id}")
def update(purchase_id: int, body: PurchaseIn, user: CurrentUser, db: Db) -> PurchaseOut:
    purchase = purchases.update(
        db, user, purchases.get(db, user, purchase_id), body.model_dump(exclude_unset=True)
    )
    db.flush()
    return _out(db, user, purchase, detailed=True)


@router.delete("/{purchase_id}", status_code=204)
def delete(purchase_id: int, user: CurrentUser, db: Db) -> None:
    purchases.delete(db, user, purchases.get(db, user, purchase_id))


@router.post("/{purchase_id}/sale")
def sell(purchase_id: int, body: SaleIn, user: CurrentUser, db: Db) -> PurchaseOut:
    purchase = purchases.sell(
        db, user, purchases.get(db, user, purchase_id), body.price, body.fees, body.sold_on
    )
    db.flush()
    return _out(db, user, purchase, detailed=True)


@router.delete("/{purchase_id}/sale")
def cancel_sale(purchase_id: int, user: CurrentUser, db: Db) -> PurchaseOut:
    purchase = purchases.cancel_sale(db, user, purchases.get(db, user, purchase_id))
    db.flush()
    return _out(db, user, purchase, detailed=True)
