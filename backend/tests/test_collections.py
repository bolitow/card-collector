"""Collections et possession : RG-05, RG-06, RG-07, RG-12, RG-15, RG-16 ; CA-05, CA-07, CA-13."""

from tests.conftest import refs


def follow(account, series) -> dict:
    return account.post("/collections", json={"series_id": series.id}, expect=201).json()


def test_following_a_series_creates_the_collection(alice, basket):
    collection = follow(alice, basket)
    assert collection["name"] == "Topps Flagship Basketball 2026/27"
    assert collection["short_name"] == "Flagship Basketball"  # F-05 : marque et saison en 2e ligne
    assert (collection["owned"], collection["total"], collection["label"]) == (0, 8, "0 %")
    assert [c["id"] for c in alice.get("/collections")["collections"]] == [collection["id"]]


def test_opening_a_card_does_not_check_it(alice, basket):
    """CA-05 : toucher une case ouvre la fiche ; la carte n'est pas cochée."""
    collection = follow(alice, basket)
    ref = refs(alice, basket)["83"]
    sheet = alice.get(f"/cards/{ref}")
    assert sheet["quantity"] == 0 and sheet["name"] == "Nic Claxton"
    assert alice.get(f"/collections/{collection['id']}")["cards"] == {}


def test_quantity_is_set_explicitly_and_bounded(alice, basket):
    """RG-06 : quantité de 0 à 999 ; q ≥ 2 donne q − 1 doubles."""
    collection = follow(alice, basket)
    ref = refs(alice, basket)["83"]
    assert alice.put(f"/cards/{ref}", {"quantity": 3})["quantity"] == 3
    assert alice.get(f"/collections/{collection['id']}")["cards"][str(ref)][0] == 3
    alice.request("PUT", f"/cards/{ref}", 422, json={"quantity": 1000})
    alice.request("PUT", f"/cards/{ref}", 422, json={"quantity": -1})
    doubles = alice.get(f"/collections/{collection['id']}/codes", params={"what": "doubles"})
    assert doubles == {"count": 1, "text": "83"}


def test_a_parallel_makes_the_card_owned_but_is_never_a_double(alice, basket):
    """CA-07, RG-05 : ajouter un parallèle à une carte manquante → carte possédée, doubles inchangés."""
    collection = follow(alice, basket)
    ref = refs(alice, basket)["135"]
    alice.post(f"/cards/{ref}/parallels", json={"name": "Orange 07/25"}, expect=201)
    state = alice.get(f"/collections/{collection['id']}")
    assert state["cards"][str(ref)][:2] == [0, 1]  # aucun exemplaire classique, un parallèle
    assert state["owned"] == 1
    assert alice.get(f"/collections/{collection['id']}/codes", params={"what": "doubles"})["count"] == 0
    missing = alice.get(f"/collections/{collection['id']}/codes")["text"]
    assert "135" not in missing.split(", ")


def test_thirty_parallels_at_most(alice, basket):
    """F-16."""
    follow(alice, basket)
    ref = refs(alice, basket)["135"]
    for number in range(30):
        alice.post(f"/cards/{ref}/parallels", json={"name": f"Gold {number + 1}/50"}, expect=201)
    response = alice.post(f"/cards/{ref}/parallels", json={"name": "Red 1/5"}, expect=409)
    assert response.json()["error"]["code"] == "too_many_parallels"


def test_progress_is_on_base_once_a_base_card_is_owned(alice, basket):
    """RG-15."""
    collection = follow(alice, basket)
    codes = refs(alice, basket)
    alice.put(f"/cards/{codes['WK-3']}", {"quantity": 1})
    summary = alice.get("/collections")["collections"][0]
    assert (summary["owned"], summary["total"]) == (1, 8)  # aucune carte de base : toute la série
    alice.put(f"/cards/{codes['83']}", {"quantity": 1})
    summary = alice.get("/collections")["collections"][0]
    assert (summary["owned"], summary["total"], summary["label"]) == (1, 5, "20 %")  # sur la base
    assert collection["id"] == summary["id"]


def test_priority_team_scopes_progress_and_is_shown_on_home(alice, basket):
    """CA-13, RG-16 : l'accueil affiche l'équipe ; l'avancement porte sur elle."""
    collection = follow(alice, basket)
    codes = refs(alice, basket)
    updated = alice.patch(f"/collections/{collection['id']}", {"priority_team": "Brooklyn Nets"}).json()
    assert updated["priority_team"] == "Brooklyn Nets"
    assert updated["total"] == 5  # 83, 135, 261, WK-30 et la carte à deux joueurs
    for code in ("83", "135", "261"):
        alice.put(f"/cards/{codes[code]}", {"quantity": 1})
    summary = alice.get("/collections")["collections"][0]
    assert (summary["owned"], summary["total"], summary["label"]) == (3, 3, "100 %")  # base des Nets


def test_a_card_with_two_players_counts_for_each_team(alice, basket):
    """RG-16 : « Équipe A / Équipe B » compte pour chaque équipe."""
    payload = alice.get(f"/catalog/series/{basket.id}/cards")
    dual = next(row for row in payload["cards"] if row[1] == "RPD-MY")
    assert {payload["teams"][i] for i in dual[4]} == {"Michigan", "Brooklyn Nets"}
    assert dual[2] == "Yaxel Lendeborg / Mikel Brown Jr. RC"  # convention 9.2


def test_a_team_outside_the_series_is_refused(alice, basket):
    collection = follow(alice, basket)
    response = alice.patch(
        f"/collections/{collection['id']}", {"priority_team": "Real Madrid CF"}, expect=400
    )
    assert response.json()["error"]["code"] == "team_not_in_series"


def test_unfollowing_keeps_everything_and_cards_become_isolated(alice, basket):
    """RG-12 : « Ne plus suivre » met en réserve sans rien perdre."""
    collection = follow(alice, basket)
    ref = refs(alice, basket)["261"]
    alice.put(f"/cards/{ref}", {"quantity": 2, "wanted": True, "note": "signée"})
    alice.patch(f"/collections/{collection['id']}", {"status": "reserve"})

    assert alice.get("/collections")["collections"] == []
    isolated = alice.get("/isolated")
    assert [(i["code"], i["name"]) for i in isolated] == [("261", "Mikel Brown Jr. RC")]

    alice.patch(f"/collections/{collection['id']}", {"status": "followed"})
    assert alice.get("/isolated") == []
    assert alice.get(f"/cards/{ref}")["quantity"] == 2
    assert alice.get(f"/cards/{ref}")["note"] == "signée"


def test_import_a_list_of_owned_codes(alice, basket):
    """F-12, F-37 : plages, virgules, noms ; ne décoche jamais rien ; signale les codes inconnus."""
    collection = follow(alice, basket)
    codes = refs(alice, basket)
    alice.put(f"/cards/{codes['83']}", {"quantity": 4})
    report = alice.post(
        f"/collections/{collection['id']}/import-codes",
        json={"text": "83, 90\n#135 Michael Porter Jr.\nwk-3; 999"},
    ).json()
    assert report == {"checked": 3, "already": 1, "unknown": ["999"]}
    state = alice.get(f"/collections/{collection['id']}")["cards"]
    assert state[str(codes["83"])][0] == 4  # quantité conservée
    assert state[str(codes["WK-3"])][0] == 1


def test_copy_missing_in_compact_ranges(alice, db):
    """Ajout : « Copier les manquantes » au format compact, relisible par l'import."""
    from tests.conftest import card, publish_series

    draft = {
        "groups": [
            {"name": "Base", "kind": "base", "cards": [card(str(n), f"Joueur {n}") for n in range(1, 21)]}
        ]
    }
    series = publish_series(db, "Topps Chrome Football 2026", draft, universe="football", season="2026")
    collection = follow(alice, series)
    codes = refs(alice, series)
    for code in ("4", "5", "13"):
        alice.put(f"/cards/{codes[code]}", {"quantity": 1})
    compact = alice.get(f"/collections/{collection['id']}/codes", params={"compact": True})
    assert compact == {"count": 17, "text": "1-3, 6-12, 14-20"}


def test_personal_card_is_private_and_cannot_shadow_the_catalog(alice, basket):
    """RG-03 : carte personnelle hors catalogue, visible de l'utilisateur seul."""
    collection = follow(alice, basket)
    created = alice.post(
        f"/collections/{collection['id']}/personal-cards",
        json={"code": "promo-1", "name": "Carte promo"},
        expect=201,
    ).json()
    assert created["code"] == "PROMO-1"
    assert [c["code"] for c in alice.get(f"/collections/{collection['id']}")["personal"]] == ["PROMO-1"]
    clash = alice.post(f"/collections/{collection['id']}/personal-cards", json={"code": "083"}, expect=409)
    assert clash.json()["error"]["code"] == "code_in_catalog"  # « 083 » = « 83 » (RG-13)


def test_personal_collection_then_attach_to_catalog(alice, db):
    """F-35 : collection personnelle à partir d'une liste, rattachée quand la série est publiée."""
    from tests.conftest import publish_series

    created = alice.post(
        "/collections/personal",
        json={"name": "Flagship Basketball (en attente)", "codes": "83, 90, 999 Carte bonus"},
        expect=201,
    ).json()
    assert created["total"] == 3 and created["series_id"] is None
    alice.post(f"/collections/{created['id']}/import-codes", json={"text": "83 999"}, expect=200)

    series = publish_series(db)
    report = alice.post(
        f"/collections/{created['id']}/attach", json={"series_id": series.id}, expect=200
    ).json()
    assert report["checked"] == 1 and report["unknown"] == ["999"]
    home = alice.get("/collections")["collections"]
    assert len(home) == 1 and home[0]["series_id"] == series.id
    detail = alice.get(f"/collections/{home[0]['id']}")
    assert detail["cards"][str(refs(alice, series)["83"])][0] == 1
    assert [c["code"] for c in detail["personal"]] == ["999"]  # inconnue du catalogue : reste personnelle


def test_deleting_a_collection_removes_possession_but_not_purchases(alice, basket):
    collection = follow(alice, basket)
    ref = refs(alice, basket)["83"]
    alice.put(f"/cards/{ref}", {"quantity": 1})
    alice.post("/purchases", json={"series_id": basket.id, "code": "90", "price": "4"}, expect=201)
    alice.delete(f"/collections/{collection['id']}", expect=204)
    assert alice.get("/collections")["collections"] == []
    assert alice.get(f"/cards/{ref}")["quantity"] == 0
    assert len(alice.get("/purchases")) == 1
    assert [i["code"] for i in alice.get("/isolated")] == ["90"]  # l'achat redevient une carte isolée
