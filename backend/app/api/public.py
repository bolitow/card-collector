"""Vues publiques (RG-02, F-42, F-43). Aucune session n'est requise ; rien de privé ne sort d'ici."""

from fastapi import APIRouter, Response
from sqlalchemy import select

from app.deps import CurrentUser, Db
from app.errors import NotFound
from app.models import CardRef, User, UserCard, UserSeries
from app.schemas import CompareOut, PublicCollectionOut, PublicProfileOut
from app.services import sharing

router = APIRouter(prefix="/public", tags=["public"])

# Les vues publiques ne restent pas en cache : un partage retiré disparaît tout de suite (CA-03).
NO_STORE = "no-store"


@router.get("/profiles/{pseudo}")
def profile(pseudo: str, db: Db, response: Response) -> PublicProfileOut:
    response.headers["Cache-Control"] = NO_STORE
    return PublicProfileOut.model_validate(sharing.profile_view(db, sharing.public_owner(db, pseudo)))


@router.get("/links/{token}")
def shared_collection(token: str, db: Db, response: Response) -> PublicCollectionOut:
    """Une seule collection, par lien secret (F-42). Fonctionne sans profil public."""
    response.headers["Cache-Control"] = NO_STORE
    response.headers["X-Robots-Tag"] = "noindex"  # ENF-08 : les liens secrets ne sont pas référencés
    collection = sharing.link_collection(db, token)
    owner = db.get(User, collection.user_id)
    return PublicCollectionOut.model_validate(sharing.collection_view(db, owner, collection))


@router.get("/compare/{pseudo}/{collection_id}")
def compare(pseudo: str, collection_id: int, user: CurrentUser, db: Db) -> CompareOut:
    """Ajout au cahier des charges : compare une collection partagée à la sienne.

    Ne s'appuie que sur ce que le propriétaire montre déjà : ses cartes visibles, et ses manquantes
    s'il a choisi de les afficher. Aucun double, aucune quantité (RG-02) ; aucune messagerie.
    """
    owner = sharing.public_owner(db, pseudo)
    collection = next((c for c in sharing.shared_collections(db, owner) if c.id == collection_id), None)
    if collection is None:
        raise NotFound(code="collection_not_found")
    view = sharing.collection_view(db, owner, collection)

    mine = set(
        db.scalars(
            select(UserCard.card_ref_id)
            .join(CardRef, CardRef.id == UserCard.card_ref_id)
            .where(UserCard.user_id == user.id, UserCard.owned, CardRef.series_id == collection.series_id)
        )
    )
    my_codes = dict(db.execute(select(CardRef.code, CardRef.name).where(CardRef.id.in_(mine))).all())
    they_have = [
        {"code": c["code"], "name": c["name"]} for c in view["cards"] if c["card_ref_id"] not in mine
    ]
    i_have = [m for m in view["missing"] if m["code"] in my_codes]
    following = bool(
        db.scalar(
            select(UserSeries.id).where(
                UserSeries.user_id == user.id, UserSeries.series_id == collection.series_id
            )
        )
    )
    return CompareOut(they_have_i_miss=they_have, i_have_they_miss=i_have, following=following)
