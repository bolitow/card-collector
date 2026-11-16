"""Administration : import et mise à jour d'une checklist (F-36 à F-39, RG-04 ; CA-10, CA-11),
file de travail (F-48), cartes recherchées (RG-17)."""

from sqlalchemy import select

from app.models import CardRef, Publisher, Universe
from app.services import checklist_text, imports, mail
from tests.conftest import BASKET_DRAFT, card, publish_series, refs, run_jobs

CHECKLIST = """
BASE
1    Josh Allen             Buffalo Bills
2    Caleb Williams         Chicago Bears
301  Fernando Mendoza       Las Vegas Raiders       Rookie
302  JEREMIYAH LOVE         Arizona Cardinals       RC

INSERT
BIG TICKET PLAYERS
BTP-1   Josh Allen          Buffalo Bills
BTP-2   Caleb Williams      Chicago Bears
BIG TIME PLAYERS
BTP-1   Fernando Mendoza    Las Vegas Raiders
BTP-2   Jeremiyah Love      Arizona Cardinals

GOLDEN MIRROR ROOKIE IMAGE VARIATIONS
301  Fernando Mendoza       Las Vegas Raiders
302  Jeremiya Love          Arizona Cardinals
999  Carson Beck            Arizona Cardinals

AUTOGRAPH
FLAGSHIP FIRST DUAL SIGNATURES
FDS-BL  Jeremiyah Love / Carson Beck    Arizona Cardinals
"""


def ids(db):
    return {
        "universe_id": db.scalar(select(Universe.id).where(Universe.slug == "football-americain")),
        "publisher_id": db.scalar(select(Publisher.id).where(Publisher.name == "Topps")),
    }


def start_import(admin, db, **fields) -> dict:
    body = {
        **ids(db),
        "series_name": "Topps Flagship Football 2026",
        "season": "2026",
        "text": CHECKLIST,
        **fields,
    }
    created = admin.post("/admin/imports", json=body, expect=201).json()
    assert created["status"] == "analyzing"
    run_jobs()
    return admin.get(f"/admin/imports/{created['id']}")


def test_plain_text_reading_finds_groups_types_teams_and_rookies():
    groups = {g["name"]: g for g in checklist_text.parse_plain(CHECKLIST)}
    assert list(groups) == [
        "Base",
        "Big Ticket Players",
        "Big Time Players",
        "Golden Mirror Rookie Image Variations",
        "Flagship First Dual Signatures",
    ]
    assert [g["kind"] for g in groups.values()] == ["base", "insert", "insert", "special", "auto"]
    mendoza = groups["Base"]["cards"][2]
    assert mendoza == {
        "code": "301",
        "names": ["Fernando Mendoza"],
        "teams": ["Las Vegas Raiders"],
        "rookie": True,
    }
    dual = groups["Flagship First Dual Signatures"]["cards"][0]
    assert dual["names"] == ["Jeremiyah Love", "Carson Beck"]


def test_import_detects_anomalies_then_publishes(admin, alice, db):
    """CA-11 (sur une checklist de synthèse) : sous-séries, codes uniques, doublons BTP signalés,
    équipes et rookies renseignés. Les étapes 2 à 4 de F-36."""
    record = start_import(admin, db)
    assert record["status"] == "review" and record["counters"]["cards"] == 12
    found = {(a["type"], a["group"]) for a in record["anomalies"]}
    assert ("code_en_double", 2) in found  # BTP-1 et BTP-2 existent déjà dans Big Ticket Players
    assert ("coquille", 0) in found  # « JEREMIYAH LOVE » en majuscules
    assert ("nom_different", 3) in found  # « Jeremiya Love » ≠ la carte de base 302
    assert ("hors_base", 3) in found  # 999 ne correspond à aucune carte de base
    duplicate = next(a for a in record["anomalies"] if a["type"] == "code_en_double" and a["group"] == 2)
    assert duplicate["blocking"] and duplicate["proposal"] == "Préfixer : BTP-"

    # Tant qu'une anomalie bloquante reste, rien n'est publié (RG-19).
    refused = admin.post(f"/admin/imports/{record['id']}/publish", expect=409).json()["error"]
    assert refused["code"] == "import_has_blocking_anomalies"
    assert alice.get("/catalog/series") == []

    # Étape 3 : relecture — préfixes (convention 9.2), coquilles corrigées, carte hors base retirée.
    draft = record["draft"]
    draft["groups"][2]["prefix"] = "TIME"
    draft["groups"][3]["prefix"] = "GM"
    draft["groups"][0]["cards"][3]["names"] = ["Jeremiyah Love"]
    draft["groups"][3]["cards"][1]["names"] = ["Jeremiyah Love"]
    draft["groups"][3]["cards"].pop()
    reviewed = admin.patch(f"/admin/imports/{record['id']}", {"draft": draft}).json()
    assert [a for a in reviewed["anomalies"] if a["blocking"]] == []
    assert reviewed["name_problems"] == []

    # Étape 4 : publication.
    published = admin.post(f"/admin/imports/{record['id']}/publish", expect=200).json()
    series = alice.get(f"/catalog/series/{published['series_id']}")
    assert series["card_count"] == 11 and series["counts"] == {
        "base": 4,
        "insert": 4,
        "special": 2,
        "auto": 1,
    }
    assert series["has_teams"] and series["version"] == 1
    payload = alice.get(f"/catalog/series/{published['series_id']}/cards")
    codes = [row[1] for row in payload["cards"]]
    assert len(codes) == len(set(codes))  # codes uniques dans la série
    assert {"BTP-1", "TIME-BTP-1", "GM-301", "FDS-BL"} <= set(codes)
    love = next(row for row in payload["cards"] if row[1] == "302")
    assert love[2] == "Jeremiyah Love RC" and love[5] & 1  # rookie
    assert admin.get("/admin/audit")[0]["action"] == "series.publish"


def test_series_name_convention_and_duplicates_are_checked(admin, db):
    """F-39."""
    publish_series(db)
    record = start_import(admin, db, series_name="Flagship Football", season="26")
    assert len(record["name_problems"]) == 3  # marque absente, saison absente du nom, saison mal écrite
    near = start_import(
        admin,
        db,
        **{
            "universe_id": db.scalar(select(Universe.id).where(Universe.slug == "basket")),
            "series_name": "topps flagship basketball 2026-27",
            "season": "",
        },
    )
    assert any("presque identique" in problem for problem in near["name_problems"])


def test_correcting_a_followed_checklist_loses_nothing(admin, alice, bob, db):
    """CA-10, RG-04 : aucune perte de possession, de photo ni de marque ; changements montrés avant."""
    series = publish_series(db)
    before = refs(alice, series)
    for account in (alice, bob):
        account.post("/collections", json={"series_id": series.id}, expect=201)
    photo = alice.upload()
    alice.put(f"/cards/{before['261']}", {"quantity": 2, "photo_id": photo, "wanted": True})
    alice.post(f"/cards/{before['WK-3']}/parallels", json={"name": "Gold 3/50"}, expect=201)
    bob.put(f"/cards/{before['90']}", {"quantity": 1})
    bob.post("/purchases", json={"series_id": series.id, "code": "135", "price": "3"}, expect=201)

    # L'administrateur corrige un nom, renumérote une carte, en retire deux et en ajoute une.
    record = admin.post(f"/admin/series/{series.id}/edit", expect=201).json()
    draft = admin.get(f"/admin/imports/{record['id']}")["draft"]
    base, inserts = draft["groups"][0]["cards"], draft["groups"][1]["cards"]
    next(c for c in base if c["code"] == "261")["names"] = ["Mikel Brown Junior"]
    next(c for c in inserts if c["code"] == "WK-3")["code"] = "WK-03"
    base[:] = [c for c in base if c["code"] not in ("90", "83")]  # 90 est possédée par Bob, 83 par personne
    base.append(card("300", "Nouveau Joueur", "Brooklyn Nets"))
    admin.patch(f"/admin/imports/{record['id']}", {"draft": draft})

    diff = admin.get(f"/admin/imports/{record['id']}/diff")
    assert diff["counts"] == {
        "added": 1,
        "renamed": 1,
        "recoded": 1,
        "moved": 0,
        "removed": 2,
        "unchanged": 6,
    }
    assert {(r["code"], r["owners"]) for r in diff["removed"]} == {("90", 1), ("83", 0)}
    assert diff["renamed"] == [
        {"code": "261", "before": "Mikel Brown Jr. RC", "after": "Mikel Brown Junior RC"}
    ]

    version = admin.post(f"/admin/imports/{record['id']}/publish", expect=200).json()["version"]
    assert version == 2
    after = refs(alice, series)
    assert after["261"] == before["261"] and after["WK-03"] == before["WK-3"]  # identifiants conservés
    assert "90" not in after and "83" not in after and "300" in after

    sheet = alice.get(f"/cards/{before['261']}")
    assert (sheet["name"], sheet["quantity"], sheet["photo_id"], sheet["wanted"]) == (
        "Mikel Brown Junior RC",
        2,
        photo,
        True,
    )
    assert [p["name"] for p in alice.get(f"/cards/{before['WK-3']}")["parallels"]] == ["Gold 3/50"]
    # La référence possédée qui disparaît est masquée, pas supprimée ; l'autre est supprimée.
    assert db.get(CardRef, before["90"]).status == "hidden"
    assert db.get(CardRef, before["83"]) is None
    assert db.get(CardRef, before["135"]) is not None  # achetée par Bob
    assert admin.get(f"/admin/series/{series.id}/versions")[0]["summary"] == {
        "added": 1,
        "hidden": 1,
        "deleted": 1,
    }
    # La recherche suit le nouveau nom.
    assert [r["code"] for r in alice.get("/search", params={"q": "junior"})["results"]] == ["261"]


def test_two_references_can_swap_their_codes(db):
    series = publish_series(db)
    ids_before = {r.code: r.id for r in db.scalars(select(CardRef).where(CardRef.series_id == series.id))}
    draft = {"groups": [dict(g, cards=[dict(c) for c in g["cards"]]) for g in BASKET_DRAFT["groups"]]}
    cards = draft["groups"][0]["cards"]
    cards[0]["ref_id"], cards[0]["code"] = ids_before["83"], "90"
    cards[1]["ref_id"], cards[1]["code"] = ids_before["90"], "83"
    publish_series(db, draft=draft, series_id=series.id)
    db.expire_all()
    assert db.get(CardRef, ids_before["83"]).code == "90" and db.get(CardRef, ids_before["90"]).code == "83"


def test_merging_duplicates_moves_possession_to_the_target(admin, alice, db):
    """F-46 : fusion de doublons."""
    series = publish_series(db)
    codes = refs(alice, series)
    alice.post("/collections", json={"series_id": series.id}, expect=201)
    alice.put(f"/cards/{codes['WK-3']}", {"quantity": 2})
    alice.put(f"/cards/{codes['WK-30']}", {"quantity": 1, "wanted": True})
    alice.post(f"/cards/{codes['WK-30']}/parallels", json={"name": "Blue"}, expect=201)
    admin.post(
        "/admin/refs/merge", json={"source_id": codes["WK-30"], "target_id": codes["WK-3"]}, expect=204
    )

    assert "WK-30" not in refs(alice, series)
    sheet = alice.get(f"/cards/{codes['WK-3']}")
    assert (sheet["quantity"], sheet["wanted"], [p["name"] for p in sheet["parallels"]]) == (
        3,
        True,
        ["Blue"],
    )


def test_editorial_chase_marks_are_visible_to_everyone(admin, alice, basket):
    """RG-17 : marques éditoriales avec une raison ; distinctes des marques personnelles."""
    ref = refs(alice, basket)["151"]
    admin.request("PUT", f"/admin/refs/{ref}/chase", 204, json={"reason": "Rookie n° 1 de la draft"})
    series = alice.get(f"/catalog/series/{basket.id}")
    assert [(c["code"], c["reason"]) for c in series["chase"]] == [("151", "Rookie n° 1 de la draft")]
    row = next(r for r in alice.get(f"/catalog/series/{basket.id}/cards")["cards"] if r[0] == ref)
    assert row[5] & 2
    sheet = alice.get(f"/cards/{ref}")
    assert sheet["chase_reason"] == "Rookie n° 1 de la draft" and sheet["wanted"] is False


def test_series_request_is_answered_and_requester_is_told_when_published(admin, alice, bob, db):
    """F-34, F-48 : demande, vote « moi aussi », réponse, puis e-mail à la publication."""
    request = alice.post(
        "/catalog/requests",
        json={"name": "Topps Flagship Basketball 2026/27", "url": "https://example.org/x.pdf"},
        expect=201,
    ).json()
    bob.post(f"/catalog/requests/{request['id']}/vote", expect=204)
    queue = admin.get("/admin/queue")
    assert [(q["kind"], q["title"], q["votes"], q["author"]) for q in queue] == [
        ("request", "Topps Flagship Basketball 2026/27", 2, "alice")
    ]
    series = publish_series(db)
    admin.patch(
        f"/admin/queue/request/{request['id']}",
        {"status": "accepted", "admin_reply": "Ajoutée ce soir.", "series_id": series.id},
        expect=204,
    )
    imports._notify_requesters(db, series)
    db.commit()
    run_jobs()
    sent = [(m["to"], m["template"]) for m in mail.outbox]
    assert ("alice@example.org", "request_answered") in sent
    assert ("alice@example.org", "series_published") in sent and (
        "bob@example.org",
        "series_published",
    ) in sent
    assert alice.get("/catalog/requests")[0]["status"] == "published"


def test_catalog_error_report_reaches_the_queue(admin, alice, basket):
    """RG-03 : l'utilisateur ne modifie pas le catalogue ; il signale."""
    ref = refs(alice, basket)["83"]
    alice.post(
        "/reports",
        json={"kind": "catalog", "card_ref_id": ref, "message": "Le nom est mal écrit"},
        expect=201,
    )
    item = admin.get("/admin/queue")[0]
    assert item["kind"] == "report" and item["title"].endswith("n° 83") and item["author"] == "alice"
    assert alice.request("PATCH", f"/admin/series/{basket.id}", json={"status": "hidden"}).status_code == 403


def test_reported_photo_can_be_removed_and_the_action_is_logged(admin, alice, visitor, basket):
    """F-45, 10.3 : signalement par un visiteur, retrait rapide, traçabilité."""
    collection = alice.post("/collections", json={"series_id": basket.id}, expect=201).json()
    photo = alice.upload()
    ref = refs(alice, basket)["83"]
    alice.put(f"/cards/{ref}", {"quantity": 1, "photo_id": photo})
    alice.patch("/me", {"public_profile": True})
    alice.patch(f"/collections/{collection['id']}", {"shared": True})
    reported = visitor.post(
        "/api/v1/reports",
        json={"kind": "content", "pseudo": "alice", "photo_id": photo, "message": "Photo déplacée"},
    )
    assert reported.status_code == 201
    item = admin.get("/admin/queue")[0]
    assert (item["target_pseudo"], item["photo_id"], item["author"]) == ("alice", photo, None)

    admin.delete(f"/admin/photos/{photo}", expect=204, params={"reason": "Contenu inapproprié"})
    assert alice.get(f"/cards/{ref}")["photo_id"] is None and alice.get(f"/cards/{ref}")["quantity"] == 1
    assert admin.get("/admin/audit")[0]["action"] == "photo.remove"
