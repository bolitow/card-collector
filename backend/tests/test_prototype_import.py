"""Reprise du prototype (section 13, CA-18), sur des données de synthèse au format de l'annexe E.

Les données réelles du prototype n'étaient pas disponibles : ce test vérifie le format décrit,
les totaux avant/après et le fait que la reprise se rejoue sans rien dupliquer.
"""

from decimal import Decimal

from sqlalchemy import func, select

from app.models import CardRef, ChaseMark, Purchase, Series, User, UserCard, UserParallel, UserSeries
from scripts import import_prototype
from tests.conftest import photo_bytes

EXPORT = {
    "lists": [
        {
            # Document récent : groupes typés, quantités explicites, parallèle relié à un achat.
            "name": "Topps Chrome Sapphire UEFA Club Competitions 2024/25",
            "sub": "Topps",
            "cat": "football",
            "iso": True,
            "ref": "checklistinsider.com, consultée le 08/10/2026",
            "groups": [{"k": "base", "n": "Base"}, {"k": "special", "n": "Image Variations"}],
            "cards": [
                {
                    "c": "8",
                    "n": "Antoine Griezmann",
                    "q": 0,
                    "v": [{"b": "achat-1", "n": "Gold 35/50", "p": "photo-1"}],
                },
                {"c": "90", "n": "Julian Brandt", "q": 1},
                {"c": "91", "n": "Joueur Manquant", "q": 0},
                {"c": "IV-8", "n": "Antoine Griezmann", "g": 1, "q": 0},
            ],
        },
        {
            # Équipes par indice, équipe prioritaire, marques avec et sans raison, carte hors liste.
            "name": "Topps Flagship Basketball 2026/27",
            "sub": "Topps",
            "cat": "basket",
            "fav": "Brooklyn Nets",
            "T": ["Washington Wizards", "Brooklyn Nets", "Michigan / Brooklyn Nets"],
            "cards": [
                {"c": "261", "h": True, "n": "Mikel Brown Jr. RC", "q": 1, "t": 1},
                {
                    "c": "RPD-MY",
                    "h": "Double autographe de deux rookies suivis",
                    "n": "Yaxel Lendeborg / Mikel Brown Jr. RC",
                    "q": 0,
                    "t": 2,
                },
                {"c": "12", "n": "Joueur Ancien Format", "t": "Washington Wizards"},
                {"c": "PROMO", "n": "Carte promo", "q": 2, "u": True},
            ],
        },
    ],
    "purchases": [
        {
            "id": "achat-1",
            "buy": 15,
            "buyDate": "2026-11-12",
            "cat": "football",
            "code": "8",
            "createdAt": 1794505025108,
            "name": "Antoine Griezmann",
            "photo": "photo-1",
            "platform": "",
            "sell": None,
            "sellDate": "",
            "set": "Topps Chrome Sapphire UEFA Club Competitions 2024/25",
            "sold": False,
            "variant": "Gold 35/50",
        },
        {
            "id": "achat-2",
            "buy": 27.5,
            "buyDate": "2026-10-02",
            "cat": "basket",
            "code": "103",
            "name": "Dalton Knecht",
            "photo": "",
            "platform": "Vinted",
            "sell": None,
            "sellDate": "",
            "set": "Panini National Treasures Basketball 2024/25",
            "sold": False,
            "variant": "Rookie Patch Auto Bronze 08/49",
        },
    ],
}


def test_prototype_import_matches_totals_and_can_be_replayed(db, tmp_path):
    (tmp_path / "photo-1.jpg").write_bytes(photo_bytes())
    assert import_prototype.source_totals(EXPORT, 1) == {
        "séries": 2,
        "références": 7,
        "cartes possédées": 4,
        "parallèles": 1,
        "cartes personnelles": 1,
        "achats": 2,
        "montant investi": Decimal("42.5"),
    }
    assert import_prototype.run(db, EXPORT, "porteur@example.org", tmp_path)  # totaux identiques (CA-18)
    db.commit()

    owner = db.scalar(select(User).where(User.email == "porteur@example.org"))
    assert owner.role == "admin"
    sapphire = db.scalar(select(Series).where(Series.name.like("%Sapphire%")))
    basket = db.scalar(select(Series).where(Series.name.like("%Basketball%")))
    assert (sapphire.status, sapphire.universe.slug, sapphire.source) == (
        "published",
        "football",
        EXPORT["lists"][0]["ref"],
    )

    # Série « en réserve » et équipe prioritaire.
    collections = {
        c.series_id: c for c in db.scalars(select(UserSeries).where(UserSeries.user_id == owner.id))
    }
    assert collections[sapphire.id].status == "reserve" and collections[basket.id].status == "followed"
    assert collections[basket.id].priority_team.name == "Brooklyn Nets"

    # Achat relié à la référence et au parallèle par identifiants, avec la même photo (RG-10, RG-14).
    griezmann = db.scalar(select(CardRef).where(CardRef.series_id == sapphire.id, CardRef.code == "8"))
    purchase = db.scalar(select(Purchase).where(Purchase.variant == "Gold 35/50"))
    parallel = db.scalar(select(UserParallel))
    assert purchase.card_ref_id == griezmann.id and purchase.applied and purchase.price == Decimal("15.00")
    assert (parallel.purchase_id, parallel.name) == (purchase.id, "Gold 35/50")
    assert parallel.photo_id == purchase.photo_id is not None
    loose = db.scalar(select(Purchase).where(Purchase.name == "Dalton Knecht"))
    assert loose.series_id is None and loose.series_name.startswith("Panini National Treasures")

    # Marques : avec raison → éditoriale ; sans raison → personnelle (option par défaut).
    dual = db.scalar(select(CardRef).where(CardRef.code == "RPD-MY"))
    assert db.get(ChaseMark, dual.id).reason == "Double autographe de deux rookies suivis"
    assert [t.name for t in dual.teams] == ["Brooklyn Nets", "Michigan"] and dual.rookie
    brown = db.scalar(select(CardRef).where(CardRef.code == "261"))
    assert db.scalar(select(UserCard.wanted).where(UserCard.card_ref_id == brown.id)) is True
    # Ancien document : quantité absente = 1.
    old = db.scalar(select(CardRef).where(CardRef.code == "12"))
    assert db.scalar(select(UserCard.quantity).where(UserCard.card_ref_id == old.id)) == 1

    # Sans --reset, la reprise ne s'applique pas deux fois ; avec, elle se rejoue à l'identique.
    assert not import_prototype.run(db, EXPORT, "porteur@example.org", tmp_path)
    db.rollback()
    ids_before = {r.code: r.id for r in db.scalars(select(CardRef))}
    assert import_prototype.run(db, EXPORT, "porteur@example.org", tmp_path, reset=True)
    db.commit()
    assert {r.code: r.id for r in db.scalars(select(CardRef))} == ids_before  # RG-04
    assert db.scalar(select(func.count()).select_from(Series)) == 2
    assert db.scalar(select(func.count()).select_from(Purchase)) == 2
