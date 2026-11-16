"""Cloisonnement et partage : RG-01, RG-02, RG-14, S-02 ; CA-01 à CA-04."""

import io
import json

from PIL import Image

from app.models import Photo
from app.storage import get_storage
from tests.conftest import API, photo_bytes, refs

PRIVATE_WORDS = ("price", "prix", "fees", "bought_on", "platform", "quantity", "sold", "sale", "note")


def follow(account, series) -> dict:
    return account.post("/collections", json={"series_id": series.id}, expect=201).json()


def test_another_user_gets_nothing(alice, bob, basket):
    """CA-01, S-02 : A demande à l'API une collection, une photo ou un achat de B → refus, aucune donnée."""
    collection = follow(bob, basket)
    ref = refs(bob, basket)["83"]
    photo = bob.upload()
    bob.put(f"/cards/{ref}", {"quantity": 2, "photo_id": photo, "note": "secret"})
    parallel = bob.post(f"/cards/{ref}/parallels", json={"name": "Gold 1/50"}, expect=201).json()
    purchase = bob.post(
        "/purchases", json={"series_id": basket.id, "code": "90", "price": "12"}, expect=201
    ).json()
    personal = bob.post(
        f"/collections/{collection['id']}/personal-cards", json={"code": "X1", "name": "Perso"}, expect=201
    ).json()
    link = bob.post(f"/me/collections/{collection['id']}/links", expect=201).json()

    attempts = [
        ("GET", f"/collections/{collection['id']}", None),
        ("PATCH", f"/collections/{collection['id']}", {"shared": True}),
        ("DELETE", f"/collections/{collection['id']}", None),
        ("POST", f"/collections/{collection['id']}/import-codes", {"text": "83"}),
        ("GET", f"/collections/{collection['id']}/codes", None),
        ("POST", f"/collections/{collection['id']}/personal-cards", {"code": "X2"}),
        ("GET", f"/photos/{photo}/large", None),
        ("GET", f"/purchases/{purchase['id']}", None),
        ("PATCH", f"/purchases/{purchase['id']}", {"price": "1"}),
        ("DELETE", f"/purchases/{purchase['id']}", None),
        ("POST", f"/purchases/{purchase['id']}/sale", {"price": "1"}),
        ("PATCH", f"/parallels/{parallel['id']}", {"name": "volé"}),
        ("DELETE", f"/parallels/{parallel['id']}", None),
        ("PATCH", f"/personal-cards/{personal['id']}", {"name": "volé"}),
        ("DELETE", f"/personal-cards/{personal['id']}", None),
        ("POST", f"/me/collections/{collection['id']}/links", None),
        ("DELETE", f"/me/links/{link['id']}", None),
    ]
    for method, path, body in attempts:
        response = alice.request(method, path, json=body)
        assert response.status_code == 404, f"{method} {path} → {response.status_code}"
        assert "secret" not in response.text and "12" not in response.text

    # La fiche de la même référence, vue par A, ne dit rien de B ; sa photo ne peut pas être empruntée.
    assert alice.get(f"/cards/{ref}")["quantity"] == 0
    assert alice.request("PUT", f"/cards/{ref}", json={"photo_id": photo}).status_code == 404
    assert alice.get("/purchases") == [] and alice.get("/isolated") == []
    assert alice.get("/search", params={"q": "claxton"})["results"] == []
    # Rien n'a changé pour B.
    assert bob.get(f"/cards/{ref}")["parallels"][0]["name"] == "Gold 1/50"
    assert bob.get(f"/purchases/{purchase['id']}")["price"] == "12.00"


def test_nothing_is_reachable_without_a_session(visitor, alice, basket):
    collection = follow(alice, basket)
    for path in (
        "/me",
        "/collections",
        f"/collections/{collection['id']}",
        "/purchases",
        "/isolated",
        "/admin/users",
    ):
        assert visitor.get(f"{API}{path}").status_code == 401
    assert visitor.get(f"{API}/catalog/series").status_code == 200  # le catalogue est public (F-32)


def test_public_profile_shows_only_what_was_shared_and_never_a_price(alice, visitor, basket, db):
    """CA-02 : seules les collections partagées ; aucun prix, aucune date d'achat, aucune carte vendue."""
    from tests.conftest import card, publish_series

    other = publish_series(
        db,
        "Topps Chrome Football 2026",
        {"groups": [{"name": "Base", "kind": "base", "cards": [card("1", "A")]}]},
        universe="football",
        season="2026",
    )
    shared, private = follow(alice, basket), follow(alice, other)
    codes = refs(alice, basket)
    photo, sold_photo = alice.upload(), alice.upload(photo_bytes("teal"))
    alice.put(f"/cards/{codes['83']}", {"quantity": 3, "photo_id": photo, "note": "double à échanger"})
    alice.put(f"/cards/{codes['90']}", {"quantity": 1})  # possédée, sans photo
    alice.put(
        f"/cards/{refs(alice, other)['1']}", {"quantity": 1, "photo_id": alice.upload(photo_bytes("navy"))}
    )
    kept = alice.post(
        "/purchases",
        json={
            "series_id": basket.id,
            "code": "135",
            "variant": "Gold 35/50",
            "price": "77.77",
            "bought_on": "2026-11-12",
            "platform": "Vinted",
            "photo_id": alice.upload(photo_bytes("gold")),
        },
        expect=201,
    ).json()
    sold = alice.post(
        "/purchases",
        json={
            "series_id": basket.id,
            "code": "261",
            "variant": "Red 1/5",
            "price": "55.55",
            "photo_id": sold_photo,
        },
        expect=201,
    ).json()
    alice.post(f"/purchases/{sold['id']}/sale", json={"price": "99.99"}, expect=200)

    # Rien n'est public par défaut (RG-02).
    assert visitor.get(f"{API}/public/profiles/alice").status_code == 404
    alice.patch("/me", {"public_profile": True})
    assert visitor.get(f"{API}/public/profiles/alice").json()["collections"] == []

    alice.patch(f"/collections/{shared['id']}", {"shared": True})
    response = visitor.get(f"{API}/public/profiles/alice")
    profile = response.json()
    assert [c["id"] for c in profile["collections"]] == [shared["id"]]  # pas la collection privée
    assert private["id"] not in [c["id"] for c in profile["collections"]]
    cards = {c["code"]: c for c in profile["collections"][0]["cards"]}
    assert set(cards) == {"83", "135"}  # 90 n'a pas de photo ; 261 est vendue
    assert cards["135"]["parallels"] == ["Gold 35/50"]

    # Ni dans la page, ni dans les réponses de l'API.
    body = response.text
    for value in ("77.77", "55.55", "99.99", "2026-11-12", "Vinted", "double à échanger"):
        assert value not in body
    for item in profile["collections"][0]["cards"]:
        assert not [key for key in item if any(word in key for word in PRIVATE_WORDS)]

    # Photos : celles des cartes partagées seulement.
    assert visitor.get(f"{API}/public/photos/{photo}/medium").status_code == 200
    assert visitor.get(f"{API}/public/photos/{kept['photo_id']}/medium").status_code == 200
    assert visitor.get(f"{API}/public/photos/{sold_photo}/medium").status_code == 404
    assert visitor.get(f"{API}/photos/{photo}/medium").status_code == 401

    # F-44 : toutes les cartes possédées, et la liste des manquantes, sur option.
    alice.patch(f"/collections/{shared['id']}", {"share_photos_only": False, "share_missing": True})
    collection = visitor.get(f"{API}/public/profiles/alice").json()["collections"][0]
    assert {c["code"] for c in collection["cards"]} == {"83", "90", "135"}
    assert "261" in {m["code"] for m in collection["missing"]}

    # L'aperçu montre exactement la vue des visiteurs.
    assert alice.get("/me/sharing/preview")["collections"][0]["cards"] == collection["cards"]

    # Retirer le partage ferme tout, photos comprises.
    alice.patch("/me", {"public_profile": False})
    assert visitor.get(f"{API}/public/profiles/alice").status_code == 404
    assert visitor.get(f"{API}/public/photos/{photo}/medium").status_code == 404


def test_secret_link_shares_one_collection_and_revocation_is_immediate(alice, visitor, basket):
    """CA-03, F-42 : lien secret vers une seule collection, révocable."""
    collection = follow(alice, basket)
    photo = alice.upload()
    alice.put(f"/cards/{refs(alice, basket)['83']}", {"quantity": 1, "photo_id": photo})
    link = alice.post(f"/me/collections/{collection['id']}/links", expect=201).json()

    response = visitor.get(f"{API}/public/links/{link['token']}")
    assert response.status_code == 200 and response.headers["x-robots-tag"] == "noindex"
    assert [c["code"] for c in response.json()["cards"]] == ["83"]
    assert visitor.get(f"{API}/public/photos/{photo}/thumb").status_code == 404  # sans le lien : rien
    assert (
        visitor.get(f"{API}/public/photos/{photo}/thumb", params={"token": link["token"]}).status_code == 200
    )
    assert visitor.get(f"{API}/public/profiles/alice").status_code == 404  # le profil reste fermé

    alice.delete(f"/me/links/{link['id']}", expect=204)
    assert visitor.get(f"{API}/public/links/{link['token']}").status_code == 404
    assert (
        visitor.get(f"{API}/public/photos/{photo}/thumb", params={"token": link["token"]}).status_code == 404
    )


def test_compare_with_a_shared_collection(alice, bob, basket):
    """Ajout : comparer sa collection à une collection partagée, sans rien révéler de plus."""
    theirs = follow(alice, basket)
    codes = refs(alice, basket)
    for code in ("83", "90"):
        alice.put(f"/cards/{codes[code]}", {"quantity": 2})
    alice.patch("/me", {"public_profile": True})
    alice.patch(
        f"/collections/{theirs['id']}", {"shared": True, "share_photos_only": False, "share_missing": True}
    )

    follow(bob, basket)
    for code in ("90", "135"):
        bob.put(f"/cards/{codes[code]}", {"quantity": 1})
    result = bob.get(f"/public/compare/alice/{theirs['id']}")
    assert [c["code"] for c in result["they_have_i_miss"]] == ["83"]
    assert [c["code"] for c in result["i_have_they_miss"]] == ["135"]
    assert "quantity" not in json.dumps(result)


def test_gps_position_is_removed_from_uploaded_photos(alice, db):
    """CA-04, RG-14 : la photo stockée n'a plus de métadonnées de position."""
    exif = Image.Exif()
    exif[0x010F] = "FabricantSecret"
    exif.get_ifd(0x8825).update({1: "N", 2: (48.0, 51.0, 24.0), 3: "E", 4: (2.0, 21.0, 8.0)})
    original = photo_bytes(exif=exif)
    assert Image.open(io.BytesIO(original)).getexif().get_ifd(0x8825)  # la position est bien dans l'envoi

    photo_id = alice.upload(original)
    photo = db.get(Photo, photo_id)
    for size, edge in (("thumb", 320), ("medium", 800), ("large", 1600)):
        stored = get_storage().get(f"{photo.key_prefix}/{size}.webp")
        image = Image.open(io.BytesIO(stored))
        assert image.format == "WEBP" and max(image.size) <= edge
        assert not image.getexif() and b"FabricantSecret" not in stored and b"Exif" not in stored


def test_upload_checks_the_content_not_the_extension(alice):
    """S-04."""
    response = alice.post(
        "/photos", files={"file": ("carte.jpg", b"<script>alert(1)</script>", "image/jpeg")}
    )
    assert response.status_code == 400 and response.json()["error"]["code"] == "photo_unsupported"


def test_origin_of_modifying_requests_is_checked(alice):
    """S-03 : une requête modifiante venue d'un autre site est refusée."""
    response = alice.http.post(
        f"{API}/collections", json={"series_id": 1}, headers={"Origin": "https://pirate.example"}
    )
    assert response.status_code == 403 and response.json()["error"]["code"] == "bad_origin"
