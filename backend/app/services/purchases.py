"""Achats, ventes et bilan : RG-09 à RG-11, RG-18, F-22 à F-24."""

from collections import defaultdict
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.errors import AppError, Conflict, NotFound
from app.models import CardRef, Purchase, Series, User
from app.rules import codes
from app.services import collections, photos

ZERO = Decimal("0")


def get(db: Session, user: User, purchase_id: int) -> Purchase:
    purchase = db.get(Purchase, purchase_id)
    if purchase is None or purchase.user_id != user.id:
        raise NotFound(code="purchase_not_found")
    return purchase


def _resolve(db: Session, purchase: Purchase, series_id: int | None, series_name: str, code: str) -> None:
    """RG-10 : relie l'achat à une série et, si possible, à une référence, par leurs identifiants."""
    purchase.card_ref_id = None
    if series_id is not None:
        series = db.get(Series, series_id)
        if series is None or series.status != "published":
            raise NotFound(code="series_not_found")
        purchase.series_id, purchase.series_name = series.id, series.name
        purchase.universe_id = series.universe_id
        if purchase.code:
            ref = db.scalar(
                select(CardRef).where(
                    CardRef.series_id == series.id,
                    CardRef.code_key == codes.code_key(purchase.code),
                    CardRef.status == "active",
                )
            )
            if ref:
                purchase.card_ref_id, purchase.code = ref.id, ref.code
                purchase.name = purchase.name or ref.name
    else:
        purchase.series_id = None
        purchase.series_name = series_name.strip()
    if not purchase.series_name:
        raise AppError(code="series_required")  # F-21


def create(db: Session, user: User, data: dict[str, Any]) -> Purchase:
    purchase = Purchase(user_id=user.id, series_name="")
    photos.owned(db, user, data.get("photo_id"))
    for field in (
        "name",
        "variant",
        "as_parallel",
        "photo_id",
        "price",
        "fees",
        "bought_on",
        "platform",
        "note",
    ):
        if data.get(field) is not None:
            setattr(purchase, field, data[field])
    purchase.universe_id = data.get("universe_id")
    purchase.code = _code(data.get("code"))
    _resolve(db, purchase, data.get("series_id"), data.get("series_name") or "", purchase.code)
    db.add(purchase)
    db.flush()
    # RG-09 / RG-11 : reporté dans la collection si la série est suivie, carte isolée sinon.
    if collections.is_followed(db, user, purchase.series_id):
        collections.apply_purchase(db, user, purchase)
    return purchase


def _code(raw: str | None) -> str:
    if not raw or not raw.strip():
        return ""
    try:
        return codes.normalize_code(raw)
    except codes.InvalidCode as error:
        raise AppError(str(error), code="code_invalid") from error


def update(db: Session, user: User, purchase: Purchase, data: dict[str, Any]) -> Purchase:
    """Modifie un achat. Une fois reporté dans la collection, son lien (série, code) est figé :
    on supprime et on recrée l'achat pour le déplacer."""
    relink = any(k in data for k in ("series_id", "series_name", "code"))
    if relink and purchase.applied:
        changed = data.get("series_id", purchase.series_id) != purchase.series_id or (
            "code" in data and codes.code_key(data["code"] or "0") != codes.code_key(purchase.code or "0")
        )
        if changed:
            raise Conflict(code="purchase_already_applied")
        relink = False
    if "photo_id" in data and data["photo_id"] != purchase.photo_id:
        photos.owned(db, user, data["photo_id"])
        previous, purchase.photo_id = purchase.photo_id, data["photo_id"]
        photos.release(db, previous)
    for field in ("name", "variant", "platform", "note"):
        if field in data:
            setattr(purchase, field, data[field] or "")
    for field in ("price", "fees", "bought_on", "universe_id"):
        if field in data:
            setattr(purchase, field, data[field])
    if purchase.sold:
        for field in ("sale_price", "sale_fees", "sold_on"):
            if field in data:
                setattr(purchase, field, data[field])
    if relink:
        if "code" in data:
            purchase.code = _code(data["code"])
        _resolve(
            db,
            purchase,
            data.get("series_id", purchase.series_id),
            data.get("series_name", purchase.series_name) or "",
            purchase.code,
        )
        if collections.is_followed(db, user, purchase.series_id):
            collections.apply_purchase(db, user, purchase)
    # Le nom du parallèle relié suit la variante.
    parallel = collections.linked_parallel(db, purchase)
    if parallel and "variant" in data and purchase.variant:
        parallel.name = purchase.variant[:80]
    return purchase


def delete(db: Session, user: User, purchase: Purchase) -> None:
    """CA-08 : supprimer l'achat laisse la carte (ou le parallèle, sans prix) dans la collection."""
    photo_id = purchase.photo_id
    db.delete(purchase)
    photos.release(db, photo_id)


def sell(
    db: Session, user: User, purchase: Purchase, price: Decimal, fees: Decimal | None, sold_on: date | None
) -> Purchase:
    """RG-18 : la carte reste dans les achats avec son prix et sa date de vente."""
    if purchase.sold:
        raise Conflict(code="already_sold")
    purchase.sold, purchase.sale_price, purchase.sale_fees = True, price, fees
    purchase.sold_on = sold_on or date.today()
    collections.on_sale(db, user, purchase)
    return purchase


def cancel_sale(db: Session, user: User, purchase: Purchase) -> Purchase:
    if not purchase.sold:
        raise Conflict(code="not_sold")
    collections.on_sale_cancelled(db, user, purchase)
    purchase.sold, purchase.sale_price, purchase.sale_fees, purchase.sold_on = False, None, None, None
    return purchase


def result(purchase: Purchase) -> Decimal | None:
    """RG-18 : résultat = prix de vente − prix d'achat (− frais, si renseignés)."""
    if not purchase.sold or purchase.sale_price is None:
        return None
    return (
        purchase.sale_price
        - (purchase.price or ZERO)
        - (purchase.fees or ZERO)
        - (purchase.sale_fees or ZERO)
    )


def summary(db: Session, user: User) -> dict[str, Any]:
    """F-24 : bilan. Calculé à la volée — quelques milliers d'achats au plus par utilisateur."""
    rows = db.scalars(select(Purchase).where(Purchase.user_id == user.id)).all()

    def cost(p: Purchase) -> Decimal:
        return (p.price or ZERO) + (p.fees or ZERO)

    by_universe: dict[int | None, list] = defaultdict(lambda: [0, ZERO])
    by_platform: dict[str, list] = defaultdict(lambda: [0, ZERO])
    for p in rows:
        for bucket in (by_universe[p.universe_id], by_platform[p.platform.strip()]):
            bucket[0] += 1
            bucket[1] += cost(p)
    sold = [p for p in rows if p.sold]
    kept = [p for p in rows if not p.sold]

    def table(buckets: dict) -> list[dict]:
        ordered = sorted(buckets.items(), key=lambda item: item[1][1], reverse=True)
        return [{"key": key, "count": count, "amount": amount} for key, (count, amount) in ordered]

    return {
        "count": len(rows),
        "invested": sum(map(cost, rows), ZERO),
        "sold_count": len(sold),
        "sales_result": sum((result(p) or ZERO for p in sold), ZERO),
        "kept_count": len(kept),
        "kept_amount": sum(map(cost, kept), ZERO),
        "by_universe": table(by_universe),
        "by_platform": table(by_platform),
    }


def platforms(db: Session, user: User) -> list[str]:
    """Plateformes déjà saisies, proposées en suggestion (F-20)."""
    return list(
        db.scalars(
            select(Purchase.platform)
            .where(Purchase.user_id == user.id, Purchase.platform != "")
            .group_by(Purchase.platform)
            .order_by(Purchase.platform)
        )
    )
