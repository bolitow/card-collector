"""Comptes : F-28 à F-31, S-01 ; CA-16."""

import io
import json
import zipfile

import pyotp
from sqlalchemy import func, select, text

from app.models import Photo, User
from app.services import mail
from app.storage import get_storage
from tests.conftest import API, refs, run_jobs


def link_token(template: str) -> str:
    message = next(m for m in reversed(mail.outbox) if m["template"] == template)
    return message["body"].split("token=")[1].split()[0]


def register(visitor, **overrides):
    body = {
        "email": "nouveau@example.org",
        "password": "mot-de-passe-solide",
        "pseudo": "nouveau",
        "accept_terms": True,
        "age_confirmed": True,
        **overrides,
    }
    return visitor.post(f"{API}/auth/register", json=body)


def test_register_verify_login_logout(visitor):
    assert register(visitor).status_code == 201
    me = visitor.get(f"{API}/me").json()
    assert me["pseudo"] == "nouveau" and me["email_verified"] is False and me["public_profile"] is False

    run_jobs()
    visitor.post(f"{API}/auth/verify-email", json={"token": link_token("verify_email")})
    assert visitor.get(f"{API}/me").json()["email_verified"] is True

    assert visitor.post(f"{API}/auth/logout").status_code == 204
    assert visitor.get(f"{API}/me").status_code == 401
    wrong = visitor.post(f"{API}/auth/login", json={"email": "nouveau@example.org", "password": "mauvais"})
    assert wrong.status_code == 401 and wrong.json()["error"]["code"] == "invalid_credentials"
    assert (
        visitor.post(
            f"{API}/auth/login", json={"email": "NOUVEAU@example.org", "password": "mot-de-passe-solide"}
        ).status_code
        == 200
    )


def test_registration_requires_consent_age_and_a_valid_unique_pseudo(visitor, alice):
    """F-29."""
    assert register(visitor, accept_terms=False).json()["error"]["code"] == "terms_required"
    assert register(visitor, age_confirmed=False).json()["error"]["code"] == "age_required"
    assert register(visitor, pseudo="a").json()["error"]["code"] == "pseudo_invalid"
    assert register(visitor, pseudo="admin").json()["error"]["code"] == "pseudo_invalid"
    assert register(visitor, pseudo="ALICE").json()["error"]["code"] == "pseudo_taken"
    assert register(visitor, email="alice@example.org").json()["error"]["code"] == "email_taken"
    assert register(visitor, password="court").json()["error"]["code"] == "password_too_short"


def test_password_is_hashed_with_argon2(alice, db):
    """S-01."""
    password_hash = db.scalar(select(User.password_hash).where(User.email == alice.email))
    assert password_hash.startswith("$argon2id$") and "mot-de-passe-solide" not in password_hash


def test_forgotten_password_closes_other_sessions(alice, visitor):
    visitor.post(f"{API}/auth/forgot-password", json={"email": alice.email})
    assert (
        visitor.post(f"{API}/auth/forgot-password", json={"email": "inconnu@example.org"}).status_code == 204
    )
    run_jobs()
    token = link_token("reset_password")
    assert (
        visitor.post(
            f"{API}/auth/reset-password", json={"token": token, "password": "un-nouveau-secret"}
        ).status_code
        == 204
    )
    alice.get("/me", expect=401)
    reused = visitor.post(f"{API}/auth/reset-password", json={"token": token, "password": "encore-un-autre"})
    assert reused.json()["error"]["code"] == "token_invalid"  # usage unique
    assert (
        visitor.post(
            f"{API}/auth/login", json={"email": alice.email, "password": "un-nouveau-secret"}
        ).status_code
        == 200
    )


def test_sign_in_with_an_emailed_link(alice, visitor):
    """F-28 : lien de connexion par e-mail."""
    visitor.post(f"{API}/auth/magic-link", json={"email": alice.email})
    run_jobs()
    assert (
        visitor.post(f"{API}/auth/magic-link/consume", json={"token": link_token("magic_link")}).status_code
        == 200
    )
    assert visitor.get(f"{API}/me").json()["pseudo"] == "alice"


def test_sessions_can_be_listed_and_closed(alice, visitor):
    """F-30."""
    visitor.post(f"{API}/auth/login", json={"email": alice.email, "password": "mot-de-passe-solide"})
    sessions = alice.get("/me/sessions")
    assert len(sessions) == 2 and sum(s["current"] for s in sessions) == 1
    other = next(s for s in sessions if not s["current"])
    alice.delete(f"/me/sessions/{other['id']}", expect=204)
    assert visitor.get(f"{API}/me").status_code == 401


def test_changing_email_needs_confirmation(alice):
    alice.post("/me/email", json={"email": "alice.nouvelle@example.org"}, expect=204)
    assert alice.get("/me")["email"] == "alice@example.org"
    run_jobs()
    assert mail.outbox[-1]["to"] == "alice.nouvelle@example.org"
    alice.post("/auth/verify-email", json={"token": link_token("verify_email")}, expect=204)
    assert alice.get("/me")["email"] == "alice.nouvelle@example.org"


def test_admin_area_requires_two_factor_authentication(alice, db):
    """S-01 : double authentification obligatoire pour les administrateurs."""
    alice.get("/admin/users", expect=403)
    user = db.get(User, alice.id)
    user.role = "admin"
    db.commit()
    assert alice.request("GET", "/admin/users").json()["error"]["code"] == "totp_setup_required"
    assert alice.get("/me")["admin_access"] == "totp_setup_required"

    setup = alice.post("/me/totp/setup", expect=200).json()
    alice.post("/me/totp/enable", json={"code": "000000"}, expect=400)
    alice.post("/me/totp/enable", json={"code": pyotp.TOTP(setup["secret"]).now()}, expect=204)
    alice.get("/admin/users", expect=200)
    assert alice.post("/me/totp/disable", json={"code": pyotp.TOTP(setup["secret"]).now()}).status_code == 403


def test_suspended_account_is_locked_out(alice, admin):
    target = next(u for u in admin.get("/admin/users", params={"q": "alice"}) if u["pseudo"] == "alice")
    admin.patch(f"/admin/users/{target['id']}", {"status": "suspended", "reason": "Photos signalées"})
    alice.get("/me", expect=401)
    login = alice.http.post(
        f"{API}/auth/login", json={"email": alice.email, "password": "mot-de-passe-solide"}
    )
    assert login.json()["error"]["code"] == "account_suspended"
    assert admin.get("/admin/audit")[0]["reason"] == "Photos signalées"  # RG-01 : action tracée


def test_export_then_delete_account(alice, basket, db):
    """CA-16 : archive complète (avec photos) ; puis plus aucune donnée ni photo du compte."""
    alice.post("/collections", json={"series_id": basket.id}, expect=201)
    photo_id = alice.upload()
    alice.put(f"/cards/{refs(alice, basket)['83']}", {"quantity": 2, "photo_id": photo_id, "note": "ma note"})
    alice.post(
        "/purchases",
        json={"series_id": basket.id, "code": "90", "price": "12.50", "platform": "Vinted"},
        expect=201,
    )
    prefix = db.get(Photo, photo_id).key_prefix

    job = alice.post("/me/exports", expect=202).json()
    run_jobs()
    assert alice.get("/me/exports")[0]["status"] == "done"
    assert mail.outbox[-1]["template"] == "export_ready"
    archive = zipfile.ZipFile(
        io.BytesIO(alice.request("GET", f"/me/exports/{job['id']}/download", 200).content)
    )
    assert {"donnees.json", "collections.csv", "achats.csv", f"photos/{photo_id}.webp"} <= set(
        archive.namelist()
    )
    data = json.loads(archive.read("donnees.json"))
    assert data["compte"]["email"] == "alice@example.org"
    assert data["cartes"][0]["quantite"] == 2 and data["cartes"][0]["note"] == "ma note"
    assert data["achats"][0]["prix"] == "12.50"
    assert "12.50" in archive.read("achats.csv").decode("utf-8-sig")

    # RG-08 : la suppression demande de retaper le mot de confirmation.
    assert alice.post("/me/delete", json={"word": "oui"}).json()["error"]["code"] == "confirmation_mismatch"
    alice.post("/me/delete", json={"word": "supprimer"}, expect=202)
    alice.get("/me", expect=401)
    run_jobs()

    db.expire_all()
    assert db.get(User, alice.id) is None
    for table in ("user_series", "user_card", "user_parallel", "purchase", "photo", "session", "share_link"):
        assert db.scalar(text(f"SELECT count(*) FROM {table}")) == 0, table
    assert db.scalar(select(func.count()).select_from(Photo)) == 0
    storage_root = get_storage().root
    assert not list((storage_root / prefix).glob("*")) and not list((storage_root / "exports").rglob("*.zip"))
    assert mail.outbox[-1]["template"] == "account_deleted" and mail.outbox[-1]["to"] == "alice@example.org"
    assert "alice@example.org" not in json.dumps(
        [dict(row._mapping) for row in db.execute(text("SELECT payload FROM job"))], default=str
    )
