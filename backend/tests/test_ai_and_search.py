"""IA (RG-19, RG-20, IA-01, IA-02, IA-04 ; CA-14, CA-20) et recherche (F-25, CA-12)."""

from sqlalchemy import func, select

from app.models import AiCall, User, UserCard
from app.services import ai
from tests.conftest import refs


def follow(account, series) -> dict:
    return account.post("/collections", json={"series_id": series.id}, expect=201).json()


# ----------------------------------------------------------------------- IA


def test_reading_a_photo_proposes_catalog_references_and_applies_nothing(alice, basket, db):
    """F-19, RG-19 : l'IA propose la référence du catalogue ; rien n'est enregistré sans validation."""
    follow(alice, basket)
    ai.FakeProvider.reading = ai.CardReading(
        serie="Topps Flagship Basketball 2026/27", numero="#261", nom="Mikel Brown Jr.", variante="Orange /25"
    )
    reading = alice.post("/ai/read-card", json={"photo_id": alice.upload()}, expect=200).json()
    assert (reading["code"], reading["variant"]) == ("261", "Orange /25")
    assert reading["candidates"] == [
        {
            "series_id": basket.id,
            "series_name": "Topps Flagship Basketball 2026/27",
            "card_ref_id": refs(alice, basket)["261"],
            "code": "261",
            "name": "Mikel Brown Jr. RC",
            "group": "Base",
        }
    ]
    assert db.scalar(select(func.count()).select_from(UserCard)) == 0
    assert alice.get("/purchases") == []
    # IA-02 : l'appel est journalisé.
    call = db.scalar(select(AiCall))
    assert (call.function, call.outcome, call.input_tokens) == ("read_card", "ok", 1500)


def test_series_is_recognised_even_when_the_model_does_not_copy_the_exact_name(alice, basket):
    ai.FakeProvider.reading = ai.CardReading(
        serie="Topps Flagship Basketball", numero="83", nom="", variante="Base"
    )
    reading = alice.post("/ai/read-card", json={"photo_id": alice.upload()}, expect=200).json()
    assert [c["name"] for c in reading["candidates"]] == ["Nic Claxton"]


def test_quota_reached_gives_a_clear_error_and_manual_entry_still_works(alice, basket, db):
    """CA-14, RG-20 : message clair ; saisie manuelle possible."""
    follow(alice, basket)
    user = db.get(User, alice.id)
    user.ai_quota_day = 2
    db.commit()
    photo = alice.upload()
    for _ in range(2):
        alice.post("/ai/read-card", json={"photo_id": photo}, expect=200)
    assert alice.get("/ai/quota") == {"day_limit": 2, "month_limit": 100, "day_used": 2, "month_used": 2}

    refused = alice.post("/ai/read-card", json={"photo_id": photo}, expect=429).json()["error"]
    assert refused["code"] == "ai_quota_exceeded" and refused["day_limit"] == 2
    assert ai.FakeProvider.calls == 2  # le fournisseur n'est pas appelé au-delà du quota

    manual = alice.post(
        "/purchases", json={"series_id": basket.id, "code": "83", "photo_id": photo}, expect=201
    )
    assert manual.json()["name"] == "Nic Claxton"


def test_malformed_answer_is_retried_once_then_reported_and_nothing_is_applied(alice, basket, db):
    """CA-20, IA-01 : rien n'est appliqué ; l'interface reçoit de quoi afficher message et saisie manuelle."""
    follow(alice, basket)
    ai.FakeProvider.fail = ai.InvalidOutput("JSON incomplet")
    error = alice.post("/ai/read-card", json={"photo_id": alice.upload()}, expect=503).json()["error"]
    assert error["code"] == "ai_invalid"
    assert ai.FakeProvider.calls == 2  # une seule nouvelle tentative
    assert db.scalar(select(AiCall.outcome)) == "invalid"
    assert db.scalar(select(func.count()).select_from(UserCard)) == 0


def test_provider_outage_does_not_consume_the_quota(alice, db):
    """IA-04 : si l'IA est indisponible, l'application reste utilisable."""
    ai.FakeProvider.fail = ConnectionError("réseau coupé")
    photo = alice.upload()
    assert (
        alice.post("/ai/read-card", json={"photo_id": photo}, expect=503).json()["error"]["code"]
        == "ai_unavailable"
    )
    assert alice.get("/ai/quota")["day_used"] == 0
    assert alice.get("/me")["ai_available"] is True


def test_reading_requires_a_verified_address(alice, db):
    user = db.get(User, alice.id)
    user.email_verified_at = None
    db.commit()
    response = alice.post("/ai/read-card", json={"photo_id": alice.upload()}, expect=403)
    assert response.json()["error"]["code"] == "email_not_verified"


# ---------------------------------------------------------------- recherche


def search(account, q: str, **params) -> dict:
    return account.get("/search", params={"q": q, **params})


def test_search_in_my_collections(alice, basket):
    """CA-12 : « 3 » trouve WK-3, pas WK-30 ; « nets » ne trouve pas Hornets."""
    follow(alice, basket)
    assert [r["code"] for r in search(alice, "3")["results"]] == ["WK-3"]
    nets = [r["code"] for r in search(alice, "nets")["results"]]
    assert set(nets) == {"83", "135", "261", "WK-30", "RPD-MY"}
    assert "90" not in nets and "WK-3" not in nets  # Charlotte Hornets
    assert [r["code"] for r in search(alice, "wk3")["results"]] == ["WK-3"]
    assert [r["code"] for r in search(alice, "demin")["results"]] == ["WK-30"]  # accents ignorés
    assert [r["name"] for r in search(alice, "#261")["results"]] == ["Mikel Brown Jr. RC"]


def test_owned_cards_come_first_and_filters_count(alice, basket):
    """F-25 : filtres Toutes, Détenues, Manquantes ; détenues en premier."""
    follow(alice, basket)
    alice.put(f"/cards/{refs(alice, basket)['261']}", {"quantity": 1})
    result = search(alice, "brooklyn")
    assert result["results"][0]["code"] == "261" and result["results"][0]["owned"] is True
    assert result["counts"] == {"all": 5, "owned": 1, "missing": 4}
    assert [r["code"] for r in search(alice, "brooklyn", only="owned")["results"]] == ["261"]
    assert "261" not in [r["code"] for r in search(alice, "brooklyn", only="missing")["results"]]


def test_search_covers_reserve_collections_and_loose_purchases_but_not_other_series(alice, basket):
    collection = follow(alice, basket)
    alice.patch(f"/collections/{collection['id']}", {"status": "reserve"})
    alice.post(
        "/purchases",
        json={"series_name": "Prizm World Cup", "code": "10", "name": "Lionel Messi"},
        expect=201,
    )
    assert [r["code"] for r in search(alice, "claxton")["results"]] == ["83"]
    messi = search(alice, "messi")["results"]
    assert [(r["kind"], r["series_name"]) for r in messi] == [("purchase", "Prizm World Cup")]


def test_catalog_tab_searches_published_series_without_following(alice, basket):
    assert search(alice, "flagg")["results"] == []  # la série n'est pas suivie
    found = search(alice, "flagg", scope="catalog")["results"]
    assert [(r["code"], r["series_name"]) for r in found] == [("151", "Topps Flagship Basketball 2026/27")]
