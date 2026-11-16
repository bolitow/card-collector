"""Achats et ventes : RG-09 à RG-12, RG-18 ; CA-08, CA-09 ; bilan F-24."""

from tests.conftest import refs


def follow(account, series) -> dict:
    return account.post("/collections", json={"series_id": series.id}, expect=201).json()


def buy(account, **fields) -> dict:
    return account.post("/purchases", json=fields, expect=201).json()


def test_parallel_purchase_in_a_followed_series_becomes_a_parallel_of_the_card(alice, basket):
    """CA-08 : achat « Gold 35/50 » → parallèle de la carte avec son prix ; supprimer l'achat laisse
    le parallèle, sans prix."""
    follow(alice, basket)
    ref = refs(alice, basket)["83"]
    purchase = buy(
        alice, series_id=basket.id, code="#83", variant="Gold 35/50", price="15.00", bought_on="2026-11-12"
    )
    assert purchase["card_ref_id"] == ref and purchase["name"] == "Nic Claxton"
    assert purchase["applied"] and not purchase["is_isolated"]

    sheet = alice.get(f"/cards/{ref}")
    assert sheet["quantity"] == 0  # RG-05 : possédée par son parallèle, sans exemplaire classique
    assert [(p["name"], p["purchase"]["price"]) for p in sheet["parallels"]] == [("Gold 35/50", "15.00")]
    assert alice.get(f"/purchases/{purchase['id']}")["parallel_id"] == sheet["parallels"][0]["id"]

    alice.delete(f"/purchases/{purchase['id']}", expect=204)
    sheet = alice.get(f"/cards/{ref}")
    assert [(p["name"], p["purchase"]) for p in sheet["parallels"]] == [("Gold 35/50", None)]


def test_base_purchase_checks_the_card_only_if_it_was_missing(alice, basket):
    """RG-09 : variante non parallèle → carte cochée, quantité 1 si elle manquait."""
    follow(alice, basket)
    ref = refs(alice, basket)["90"]
    buy(alice, series_id=basket.id, code="90", variant="Base", price="2")
    assert alice.get(f"/cards/{ref}")["quantity"] == 1
    buy(alice, series_id=basket.id, code="90", variant="", price="2")
    assert alice.get(f"/cards/{ref}")["quantity"] == 1
    assert alice.get(f"/cards/{ref}")["parallels"] == []


def test_user_can_force_parallel_or_base(alice, basket):
    """F-20 : choix « Parallèle / Carte de base » quand l'achat correspond à une carte suivie."""
    follow(alice, basket)
    codes = refs(alice, basket)
    buy(alice, series_id=basket.id, code="83", variant="Refractor", as_parallel=False)
    assert alice.get(f"/cards/{codes['83']}")["quantity"] == 1
    buy(alice, series_id=basket.id, code="90", variant="Rookie", as_parallel=True)
    assert [p["name"] for p in alice.get(f"/cards/{codes['90']}")["parallels"]] == ["Rookie"]


def test_purchase_in_an_unfollowed_series_is_isolated_then_checked_on_follow(alice, basket):
    """CA-09, RG-11, RG-12 : carte isolée, puis cochée dans la nouvelle collection."""
    purchase = buy(alice, series_id=basket.id, code="151", variant="Base", price="9")
    assert purchase["is_isolated"] and purchase["can_follow"]
    assert alice.get("/collections")["collections"] == []  # aucune collection créée pour une carte
    assert [i["code"] for i in alice.get("/isolated")] == ["151"]

    collection = follow(alice, basket)
    ref = refs(alice, basket)["151"]
    assert alice.get(f"/collections/{collection['id']}")["cards"][str(ref)][0] == 1
    assert alice.get("/isolated") == []
    assert not alice.get(f"/purchases/{purchase['id']}")["is_isolated"]


def test_purchase_outside_the_catalog_keeps_a_free_series_name(alice, db):
    """RG-10 : nom de série libre ; l'achat rejoint le catalogue quand la série y entre."""
    from tests.conftest import publish_series

    purchase = buy(
        alice, series_name="Topps Flagship Basketball 2026/27", code="83", name="Nic Claxton", price="3"
    )
    assert purchase["series_id"] is None and purchase["is_isolated"] and not purchase["can_follow"]
    series = publish_series(db)
    linked = alice.get(f"/purchases/{purchase['id']}")
    assert linked["series_id"] == series.id and linked["card_ref_id"] is not None and linked["can_follow"]


def test_series_is_required(alice):
    """F-21."""
    response = alice.post("/purchases", json={"code": "12", "price": "3"}, expect=400)
    assert response.json()["error"]["code"] == "series_required"


def test_sale_keeps_the_purchase_and_computes_the_result(alice, basket):
    """RG-18 : résultat = prix de vente − prix d'achat − frais ; la vente s'annule."""
    follow(alice, basket)
    ref = refs(alice, basket)["83"]
    purchase = buy(alice, series_id=basket.id, code="83", variant="Gold 35/50", price="15", fees="1.50")
    sold = alice.post(
        f"/purchases/{purchase['id']}/sale",
        json={"price": "40", "fees": "4", "sold_on": "2026-11-15"},
        expect=200,
    ).json()
    assert sold["sold"] and sold["result"] == "19.50"
    assert [p["id"] for p in alice.get("/purchases", params={"only": "sold"})] == [purchase["id"]]
    # Une carte vendue n'est plus possédée (RG-02).
    assert alice.get("/collections")["collections"][0]["owned"] == 0
    assert alice.get(f"/cards/{ref}")["parallels"][0]["sold"] is True

    cancelled = alice.delete(f"/purchases/{purchase['id']}/sale", expect=200).json()
    assert not cancelled["sold"] and cancelled["sale_price"] is None and cancelled["result"] is None
    assert alice.get("/collections")["collections"][0]["owned"] == 1


def test_selling_a_base_card_removes_one_copy_and_cancelling_gives_it_back(alice, basket):
    follow(alice, basket)
    ref = refs(alice, basket)["90"]
    purchase = buy(alice, series_id=basket.id, code="90", price="2")
    alice.put(f"/cards/{ref}", {"quantity": 2})
    alice.post(f"/purchases/{purchase['id']}/sale", json={"price": "5"}, expect=200)
    assert alice.get(f"/cards/{ref}")["quantity"] == 1
    alice.delete(f"/purchases/{purchase['id']}/sale", expect=200)
    assert alice.get(f"/cards/{ref}")["quantity"] == 2


def test_summary(alice, basket):
    """F-24 : résultat des ventes, investi au total, montant en collection, par univers et plateforme."""
    first = buy(alice, series_id=basket.id, code="83", price="25", platform="Vinted", variant="Orange 02/25")
    buy(alice, series_id=basket.id, code="90", price="19", fees="1", platform="eBay")
    buy(alice, series_name="Série inconnue", price="6", platform="Vinted")
    alice.post(f"/purchases/{first['id']}/sale", json={"price": "30"}, expect=200)

    summary = alice.get("/purchases/summary")
    assert summary["count"] == 3 and summary["invested"] == "51.00"
    assert (summary["sold_count"], summary["sales_result"]) == (1, "5.00")
    assert (summary["kept_count"], summary["kept_amount"]) == (2, "26.00")
    assert [(r["key"], r["count"], r["amount"]) for r in summary["by_platform"]] == [
        ("Vinted", 2, "31.00"),
        ("eBay", 1, "20.00"),
    ]
    assert summary["by_universe"][0]["count"] == 2 and summary["by_universe"][0]["amount"] == "45.00"
    assert alice.get("/purchases/platforms") == ["Vinted", "eBay"]


def test_purchases_are_listed_most_recent_first(alice, basket):
    """F-22."""
    buy(alice, series_id=basket.id, code="83", bought_on="2026-10-01")
    buy(alice, series_id=basket.id, code="90", bought_on="2026-11-13")
    buy(alice, series_id=basket.id, code="135", bought_on="2026-11-02")
    assert [p["code"] for p in alice.get("/purchases")] == ["90", "135", "83"]


def test_a_shared_photo_is_deleted_only_when_nothing_uses_it(alice, basket):
    """RG-14 : la même photo sert à l'achat et à la carte ; supprimée quand plus rien ne l'utilise."""
    follow(alice, basket)
    ref = refs(alice, basket)["83"]
    photo = alice.upload()
    purchase = buy(alice, series_id=basket.id, code="83", variant="Gold 35/50", photo_id=photo)
    parallel = alice.get(f"/cards/{ref}")["parallels"][0]
    assert parallel["photo_id"] == photo

    alice.delete(f"/purchases/{purchase['id']}", expect=204)
    alice.request("GET", f"/photos/{photo}/thumb", 200)  # encore utilisée par le parallèle
    alice.delete(f"/parallels/{parallel['id']}", expect=204)
    alice.request("GET", f"/photos/{photo}/thumb", 404)


def test_adding_a_price_to_a_parallel_creates_a_linked_purchase_once(alice, basket):
    """F-17 : « Ajouter le prix d'achat » sur un parallèle, sans double saisie."""
    follow(alice, basket)
    ref = refs(alice, basket)["83"]
    parallel = alice.post(f"/cards/{ref}/parallels", json={"name": "Orange 07/25"}, expect=201).json()
    priced = alice.post(
        f"/parallels/{parallel['id']}/purchase", json={"price": "25", "platform": "Vinted"}, expect=201
    )
    assert priced.json()["purchase"]["price"] == "25.00"
    purchases = alice.get("/purchases")
    assert [(p["variant"], p["code"], p["applied"]) for p in purchases] == [("Orange 07/25", "83", True)]
    assert len(alice.get(f"/cards/{ref}")["parallels"]) == 1  # pas de second parallèle
    alice.post(f"/parallels/{parallel['id']}/purchase", json={"price": "1"}, expect=409)
