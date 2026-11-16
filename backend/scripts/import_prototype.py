"""Reprise des données du prototype (section 13, annexe E). Rejouable, avec contrôle des totaux.

    uv run python -m scripts.import_prototype export.json --email proprietaire@example.org \
        [--photos DOSSIER] [--chase split|editorial|personal] [--reset]

`export.json` : {"lists": [...], "purchases": [...]} — un objet par document du prototype, tel que
décrit en annexe E ; chaque achat porte en plus son identifiant de document dans "id".
`--photos` : dossier des fichiers photo, nommés par leur identifiant (avec ou sans extension).

Ce que fait le script :
- chaque liste devient une série publiée du catalogue (les cartes `u` restent des cartes
  personnelles) ; rejouer le script met la série à jour sans changer ses identifiants (RG-04) ;
- la possession, les parallèles, les marques et les photos vont au compte du porteur ; les listes
  « en réserve » (`iso`) deviennent des collections en réserve ;
- les achats sont reliés aux références par série et code (RG-10) ;
- les totaux de la source et ceux de la base sont comparés à la fin. Le script échoue s'ils diffèrent.

`--reset` efface d'abord les données du porteur (pas le catalogue), pour rejouer la reprise.
"""

import argparse
import json
import sys
from collections import Counter
from datetime import date
from decimal import Decimal
from pathlib import Path

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app import security
from app.db import get_sessionmaker
from app.models import (
    CardRef,
    ChaseMark,
    ChecklistImport,
    PersonalCard,
    Photo,
    Publisher,
    Purchase,
    Series,
    Universe,
    User,
    UserCard,
    UserParallel,
    UserSeries,
)
from app.rules import codes
from app.rules.search import fold
from app.services import accounts, collections, imports, photos
from app.storage import get_storage

# Clés d'univers du prototype (champ `cat`) → univers de l'application.
UNIVERSES = {
    "football": "football",
    "foot": "football",
    "nfl": "football-americain",
    "football americain": "football-americain",
    "baseball": "baseball",
    "basket": "basket",
    "basketball": "basket",
    "hockey": "hockey",
    "f1": "formule-1",
    "formule 1": "formule-1",
    "manga": "manga",
    "star wars": "star-wars",
    "starwars": "star-wars",
    "marvel": "marvel",
}


def universe_id(db: Session, key: str | None) -> int | None:
    slug = UNIVERSES.get(fold(key or "").replace("-", " ").strip())
    return db.scalar(select(Universe.id).where(Universe.slug == slug)) if slug else None


def card_teams(card: dict, teams: list[str]) -> list[str]:
    """`t` : indice dans la liste `T`, ou texte dans les anciens documents ; « A / B » pour deux équipes."""
    value = card.get("t")
    if value is None:
        return []
    name = teams[value] if isinstance(value, int) and value < len(teams) else str(value)
    return [part.strip() for part in name.split("/") if part.strip()]


def quantity_of(card: dict, missing: int) -> int:
    """`q` absente = 1 dans les anciens documents (annexe E) ; réglable par --missing-quantity."""
    return int(card["q"]) if card.get("q") is not None else missing


def source_totals(export: dict, missing: int) -> Counter:
    totals: Counter = Counter()
    for item in export["lists"]:
        totals["séries"] += 1
        for card in item.get("cards", []):
            if card.get("u"):
                totals["cartes personnelles"] += 1
                continue
            totals["références"] += 1
            parallels = len(card.get("v", []))
            totals["parallèles"] += parallels
            totals["cartes possédées"] += quantity_of(card, missing) > 0 or parallels > 0  # RG-05
    totals["achats"] = len(export["purchases"])
    totals["montant investi"] = sum(Decimal(str(p.get("buy") or 0)) for p in export["purchases"])
    return totals


def database_totals(db: Session, user: User, series_ids: list[int]) -> Counter:
    totals: Counter = Counter()
    totals["séries"] = len(series_ids)
    totals["références"] = db.scalar(
        select(func.count()).where(CardRef.series_id.in_(series_ids), CardRef.status == "active")
    )
    totals["cartes personnelles"] = db.scalar(select(func.count()).where(PersonalCard.user_id == user.id))
    totals["cartes possédées"] = db.scalar(
        select(func.count()).where(UserCard.user_id == user.id, UserCard.owned)
    )
    totals["parallèles"] = db.scalar(select(func.count()).where(UserParallel.user_id == user.id))
    totals["achats"] = db.scalar(select(func.count()).where(Purchase.user_id == user.id))
    invested = db.scalar(
        select(func.coalesce(func.sum(Purchase.price), 0)).where(Purchase.user_id == user.id)
    )
    totals["montant investi"] = Decimal(invested)
    return totals


def reset_owner(db: Session, user: User) -> list[str]:
    """Efface les données du porteur. Renvoie les fichiers à supprimer du stockage une fois la
    reprise validée : si elle échoue, la base est restaurée et ses photos doivent encore exister."""
    stale = [
        f"{photo.key_prefix}/{size}.webp"
        for photo in db.scalars(select(Photo).where(Photo.user_id == user.id))
        for size in photos.SIZES
    ]
    for model in (Purchase, UserCard, PersonalCard, UserSeries, Photo):
        db.execute(delete(model).where(model.user_id == user.id))
    db.flush()
    return stale


class PhotoStore:
    """Envoie chaque photo du prototype une seule fois ; la même sert à l'achat et à la carte (RG-14)."""

    def __init__(self, db: Session, user: User, folder: Path | None) -> None:
        self.db, self.user, self.folder = db, user, folder
        self.known: dict[str, object] = {}
        self.missing: set[str] = set()

    def get(self, file_id: str | None):
        if not file_id or self.folder is None:
            return None
        if file_id not in self.known:
            match = next(iter(sorted(self.folder.glob(f"{file_id}*"))), None)
            if match is None:
                self.missing.add(file_id)
                self.known[file_id] = None
            else:
                self.known[file_id] = photos.store(self.db, self.user, match.read_bytes()).id
        return self.known[file_id]


def publish_list(db: Session, admin: User, item: dict) -> Series:
    """Une liste du prototype → une série du catalogue, par le chemin de l'outil d'administration."""
    groups = [{"name": g["n"], "kind": g["k"], "cards": []} for g in item.get("groups", [])]
    if not groups:
        groups = [{"name": "Base", "kind": "base", "cards": []}]
    for card in item.get("cards", []):
        if card.get("u"):
            continue
        name = card.get("n", "")
        rookie = name.endswith(" RC")
        groups[card.get("g", 0)]["cards"].append(
            {
                "code": card["c"],
                "names": [n for n in (name[:-3] if rookie else name).split(" / ") if n],
                "teams": card_teams(card, item.get("T", [])),
                "rookie": rookie,
            }
        )
    publisher_name = item.get("sub") or "Divers"
    publisher = db.scalar(select(Publisher).where(Publisher.name == publisher_name))
    if publisher is None:
        publisher = Publisher(name=publisher_name)
        db.add(publisher)
        db.flush()
    existing = db.scalar(select(Series).where(Series.name == item["name"]))
    record = ChecklistImport(
        admin_id=admin.id,
        series_id=existing.id if existing else None,
        universe_id=universe_id(db, item.get("cat"))
        or db.scalar(select(Universe.id).order_by(Universe.position)),
        publisher_id=publisher.id,
        series_name=item["name"],
        season=existing.season if existing else "",
        source=item.get("ref", ""),
        status="review",
        draft=imports.normalize_draft({"groups": [g for g in groups if g["cards"]]}),
    )
    db.add(record)
    db.flush()
    return imports.publish(db, admin, record)


def run(
    db: Session,
    export: dict,
    email: str,
    photo_dir: Path | None = None,
    chase: str = "split",
    missing: int = 1,
    reset: bool = False,
    stale_files: list[str] | None = None,
) -> bool:
    owner = db.scalar(select(User).where(User.email == email))
    if owner is None:
        owner = accounts.register(
            db, email, None, fold(email.split("@")[0])[:20].replace(".", "-") or "porteur"
        )
        owner.email_verified_at = security.now()
    owner.role = "admin"  # le porteur du projet est le futur administrateur (section 2)
    has_data = db.scalar(select(func.count()).where(UserSeries.user_id == owner.id))
    if has_data and not reset:
        print("Ce compte a déjà des collections. Relancez avec --reset pour rejouer la reprise.")
        return False
    if reset:
        (stale_files if stale_files is not None else []).extend(reset_owner(db, owner))

    store = PhotoStore(db, owner, photo_dir)
    series_by_name: dict[str, Series] = {}
    parallel_of_purchase: dict[str, tuple[int, str, object]] = {}  # achat → (référence, nom, photo)

    for item in export["lists"]:
        series = publish_list(db, owner, item)
        series_by_name[item["name"]] = series
        refs = dict(
            db.execute(select(CardRef.code_key, CardRef.id).where(CardRef.series_id == series.id)).all()
        )
        collection = collections.follow(db, owner, series.id)
        collection.status = "reserve" if item.get("iso") else "followed"
        if item.get("fav"):
            team = next(
                (t for t in collections.teams_of_series(db, series.id) if t.name == item["fav"]), None
            )
            collection.priority_team_id = team.id if team else None

        for card in item.get("cards", []):
            key = codes.code_key(card["c"])
            if card.get("u"):
                db.add(
                    PersonalCard(
                        user_id=owner.id,
                        user_series_id=collection.id,
                        code=codes.normalize_code(card["c"]),
                        code_key=key,
                        name=card.get("n", ""),
                        quantity=quantity_of(card, missing),
                    )
                )
                continue
            ref_id = refs[key]
            mark, reason = card.get("h"), ""
            if isinstance(mark, str):
                reason = mark
            editorial = bool(mark) and (chase == "editorial" or (chase == "split" and reason))
            if editorial:  # RG-17 : marque éditoriale, avec sa raison
                db.merge(ChaseMark(card_ref_id=ref_id, reason=reason, author_id=owner.id))
            quantity, parallels = quantity_of(card, missing), card.get("v", [])
            personal_mark = bool(mark) and not editorial
            if not (quantity or parallels or personal_mark or card.get("p")):
                continue
            state = collections.set_card(
                db, owner, ref_id, quantity=quantity, wanted=personal_mark, photo_id=store.get(card.get("p"))
            )
            for parallel in parallels:
                photo_id = store.get(parallel.get("p"))
                if parallel.get("b"):
                    parallel_of_purchase[parallel["b"]] = (ref_id, parallel["n"], photo_id)
                else:
                    collections.add_parallel(db, owner, state.card_ref_id, parallel["n"], photo_id)
        series.version += 1  # les marques éditoriales font partie de la checklist servie

    for item in export["purchases"]:
        series = series_by_name.get(item.get("set", ""))
        linked = parallel_of_purchase.get(item.get("id"))
        purchase = Purchase(
            user_id=owner.id,
            series_id=series.id if series else None,
            series_name=series.name if series else item.get("set", ""),
            universe_id=series.universe_id if series else universe_id(db, item.get("cat")),
            code=codes.normalize_code(item["code"]) if item.get("code") else "",
            name=item.get("name", ""),
            variant=item.get("variant", ""),
            photo_id=store.get(item.get("photo")),
            price=Decimal(str(item["buy"])) if item.get("buy") is not None else None,
            bought_on=date.fromisoformat(item["buyDate"]) if item.get("buyDate") else None,
            platform=item.get("platform", ""),
            sold=bool(item.get("sold")),
            sale_price=Decimal(str(item["sell"])) if item.get("sell") is not None else None,
            sold_on=date.fromisoformat(item["sellDate"]) if item.get("sellDate") else None,
        )
        if series and purchase.code:
            purchase.card_ref_id = db.scalar(
                select(CardRef.id).where(
                    CardRef.series_id == series.id, CardRef.code_key == codes.code_key(purchase.code)
                )
            )
        db.add(purchase)
        db.flush()
        if linked:  # parallèle relié à cet achat dans la liste du prototype
            ref_id, name, photo_id = linked
            purchase.card_ref_id, purchase.applied = ref_id, True
            parallel = collections.add_parallel(
                db, owner, ref_id, name, photo_id or purchase.photo_id, purchase.id
            )
            parallel.sold = purchase.sold
            collections._recount_parallels(db, parallel.user_card)
        elif purchase.card_ref_id and collections.is_followed(db, owner, purchase.series_id):
            # La liste du prototype porte déjà la quantité : l'achat est relié sans rien recocher.
            purchase.applied = True
    db.flush()

    expected = source_totals(export, missing)
    actual = database_totals(db, owner, [s.id for s in series_by_name.values()])
    print(f"{'':24}{'prototype':>12}{'application':>14}")
    same = True
    for key in (
        "séries",
        "références",
        "cartes possédées",
        "parallèles",
        "cartes personnelles",
        "achats",
        "montant investi",
    ):
        match = expected[key] == actual[key]
        same &= match
        print(f"{key:24}{str(expected[key]):>12}{str(actual[key]):>14}  {'ok' if match else 'ÉCART'}")
    if store.missing:
        sample = ", ".join(sorted(store.missing)[:5])
        print(f"Photos introuvables dans le dossier : {len(store.missing)} ({sample}…)")
    return same


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("export", type=Path)
    parser.add_argument("--email", required=True, help="adresse du compte du porteur du projet")
    parser.add_argument("--photos", type=Path)
    parser.add_argument("--chase", choices=("split", "editorial", "personal"), default="split")
    parser.add_argument("--missing-quantity", type=int, default=1, choices=(0, 1))
    parser.add_argument("--reset", action="store_true")
    args = parser.parse_args()
    export = json.loads(args.export.read_text(encoding="utf-8"))
    stale: list[str] = []
    with get_sessionmaker()() as db:
        ok = run(db, export, args.email, args.photos, args.chase, args.missing_quantity, args.reset, stale)
        if ok:
            db.commit()
            get_storage().delete(stale)
            print("Reprise enregistrée.")
        else:
            db.rollback()
            print("Reprise annulée : rien n'a été écrit.")
            sys.exit(1)


if __name__ == "__main__":
    main()
