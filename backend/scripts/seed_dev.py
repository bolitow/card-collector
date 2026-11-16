"""Données de démonstration pour le développement et la recette. Jamais en production.

    uv run python -m scripts.seed_dev

Crée un administrateur, un compte de démonstration et trois séries de synthèse : les joueurs sont
inventés, pour ne faire passer aucune liste fictive pour une checklist officielle.
Comptes : admin@example.org et demo@example.org, mot de passe « demonstration ».
"""

import io
import random

from PIL import Image, ImageDraw
from sqlalchemy import select

from app import security
from app.config import get_settings
from app.db import get_sessionmaker
from app.models import CardRef, ChaseMark, ChecklistImport, Publisher, Universe, User, UserSeries
from app.services import accounts, collections, imports, photos, purchases

FIRST = [
    "Malo",
    "Idriss",
    "Nolan",
    "Eliott",
    "Sacha",
    "Tiago",
    "Noé",
    "Yanis",
    "Ruben",
    "Lenny",
    "Milan",
    "Oscar",
    "Kylian",
    "Mathis",
    "Enzo",
    "Isaac",
    "Naël",
    "Côme",
]
LAST = [
    "Carrel",
    "Vasseur",
    "Okoro",
    "Lindqvist",
    "Maro",
    "Brandt",
    "Sorel",
    "Diallo",
    "Ferrand",
    "Abadie",
    "Keller",
    "Moreno",
    "Tanaka",
    "Novak",
    "Berger",
    "Lemaire",
    "Rossi",
]
NBA = [
    "Brooklyn Nets",
    "Charlotte Hornets",
    "Dallas Mavericks",
    "San Antonio Spurs",
    "Atlanta Hawks",
    "Boston Celtics",
]
CLUBS = [
    "Paris Saint-Germain",
    "Real Madrid CF",
    "FC Bayern München",
    "Arsenal FC",
    "Inter Milan",
    "SL Benfica",
]
NFL = [
    "Buffalo Bills",
    "Chicago Bears",
    "Las Vegas Raiders",
    "Arizona Cardinals",
    "Detroit Lions",
    "Miami Dolphins",
]


def player(rng: random.Random) -> str:
    return f"{rng.choice(FIRST)} {rng.choice(LAST)}"


def card(rng: random.Random, code: str, teams: list[str], rookie_rate: float = 0.12) -> dict:
    return {
        "code": code,
        "names": [player(rng)],
        "teams": [rng.choice(teams)],
        "rookie": rng.random() < rookie_rate,
    }


def draft(rng: random.Random, teams: list[str], base: int, groups: list[tuple[str, str, str, int]]) -> dict:
    """Base numérotée de 1 à `base`, puis des sous-séries (nom, type, préfixe de code, taille)."""
    result = [
        {"name": "Base", "kind": "base", "cards": [card(rng, str(n), teams) for n in range(1, base + 1)]}
    ]
    for name, kind, prefix, size in groups:
        result.append(
            {
                "name": name,
                "kind": kind,
                "cards": [card(rng, f"{prefix}-{n}", teams, 0.05) for n in range(1, size + 1)],
            }
        )
    return {"groups": result}


def big_draft(rng: random.Random) -> dict:
    """4 042 références en 87 sous-séries : la taille de la plus grosse série du prototype (CA-17)."""
    groups = [(f"Insert {n:02d}", "insert", f"I{n:02d}", 40) for n in range(1, 61)]
    groups += [(f"Autographes {n:02d}", "auto", f"A{n:02d}", 30) for n in range(1, 17)]
    groups += [(f"Reliques {n:02d}", "relic", f"R{n:02d}", 26) for n in range(1, 11)]
    built = draft(rng, NFL, 902, groups)
    assert sum(len(g["cards"]) for g in built["groups"]) == 4042 and len(built["groups"]) == 87
    return built


def picture(rng: random.Random, code: str, name: str) -> bytes:
    """Photo de carte factice : un aplat, un cadre, le numéro."""
    hue = rng.choice(["#2E9E5B", "#2F6FDB", "#E8742B", "#D7263D", "#7A4BD1", "#C9A227", "#1597A8"])
    image = Image.new("RGB", (600, 840), hue)
    pen = ImageDraw.Draw(image)
    pen.rounded_rectangle([28, 28, 572, 812], radius=26, outline="#F4F5F0", width=10)
    pen.rectangle([28, 620, 572, 812], fill="#14160F")
    pen.text((60, 650), name, fill="#F4F5F0", font_size=40)
    pen.text((60, 720), f"#{code}", fill="#C8F03C", font_size=54)
    buffer = io.BytesIO()
    image.save(buffer, "JPEG", quality=85)
    return buffer.getvalue()


def main() -> None:
    assert get_settings().env != "prod", "Ce script ne tourne pas en production."
    rng = random.Random(2026)
    with get_sessionmaker()() as db:
        if db.scalar(select(User).where(User.email == "demo@example.org")):
            print("Données de démonstration déjà présentes.")
            return
        admin = accounts.register(db, "admin@example.org", "demonstration", "admin-demo")
        admin.role, admin.email_verified_at = "admin", security.now()
        demo = accounts.register(db, "demo@example.org", "demonstration", "demo")
        demo.email_verified_at = security.now()
        publisher = db.scalar(select(Publisher).where(Publisher.name == "Démo")) or Publisher(name="Démo")
        db.add(publisher)
        db.flush()

        def publish(name: str, universe: str, season: str, content: dict):
            record = ChecklistImport(
                admin_id=admin.id,
                universe_id=db.scalar(select(Universe.id).where(Universe.slug == universe)),
                publisher_id=publisher.id,
                series_name=name,
                season=season,
                source="Données de démonstration",
                status="review",
                draft=imports.normalize_draft(content),
            )
            db.add(record)
            db.flush()
            return imports.publish(db, admin, record)

        basket = publish(
            "Démo Flagship Basketball 2026/27",
            "basket",
            "2026/27",
            draft(
                rng,
                NBA,
                300,
                [
                    ("Winning Kicks", "insert", "WK", 30),
                    ("Blackout", "special", "BLK", 25),
                    ("Rookie Signatures", "auto", "RS", 20),
                    ("Jersey Remnants", "relic", "JR", 15),
                ],
            ),
        )
        chrome = publish(
            "Démo Chrome Club Competitions 2025/26",
            "football",
            "2025/26",
            draft(
                rng,
                CLUBS,
                200,
                [("Budapest At Night", "insert", "BAN", 20), ("Chrome Autographs", "auto", "CA", 25)],
            ),
        )
        flagship = publish("Démo Flagship Football 2026", "football-americain", "2026", big_draft(rng))
        print("Séries publiées :", basket.name, "·", chrome.name, "·", flagship.name)

        def refs_of(series):
            return list(
                db.scalars(select(CardRef).where(CardRef.series_id == series.id).order_by(CardRef.position))
            )

        for series, share in ((basket, 0.42), (chrome, 0.18)):
            collections.follow(db, demo, series.id)
            refs = refs_of(series)
            for ref in rng.sample(refs, int(len(refs) * share)):
                collections.set_card(db, demo, ref.id, quantity=rng.choice([1, 1, 1, 1, 2, 3]))
            for ref in rng.sample(refs, 6):
                db.merge(ChaseMark(card_ref_id=ref.id, reason="Rookie très demandé", author_id=admin.id))
            series.version += 1
        collections.follow(db, demo, flagship.id)
        basket_collection = db.scalar(select(UserSeries).where(UserSeries.series_id == basket.id))
        nets = next(t for t in collections.teams_of_series(db, basket.id) if t.name == "Brooklyn Nets")
        collections.set_priority_team(db, basket_collection, nets.id)

        for series, variants in (
            (basket, ["Gold 35/50", "Orange 02/25", "Base", "Red Refractor 09/10"]),
            (chrome, ["Refractor", "Base", "Magenta Mini-Diamonds 285/399"]),
        ):
            for ref in rng.sample(refs_of(series), 7):
                photo = photos.store(db, demo, picture(rng, ref.code, ref.name))
                purchases.create(
                    db,
                    demo,
                    {
                        "series_id": series.id,
                        "code": ref.code,
                        "variant": rng.choice(variants),
                        "photo_id": photo.id,
                        "price": rng.choice([4, 9, 15, 19, 25, 27]),
                        "bought_on": security.now().date(),
                        "platform": rng.choice(["Vinted", "eBay", "Salon"]),
                    },
                )
        photo = photos.store(db, demo, picture(rng, "10", "Carte hors catalogue"))
        purchases.create(
            db,
            demo,
            {
                "series_name": "Prizm World Cup 2026",
                "code": "10",
                "name": "Carte hors catalogue",
                "variant": "Silver",
                "price": 12,
                "photo_id": photo.id,
                "platform": "Vinted",
            },
        )
        db.commit()
        print("Comptes : admin@example.org et demo@example.org — mot de passe « demonstration ».")


if __name__ == "__main__":
    main()
