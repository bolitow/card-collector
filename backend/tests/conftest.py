"""Tests sur une vraie base PostgreSQL : les migrations sont jouées, les contraintes s'appliquent."""

import io
import os
import tempfile
from collections.abc import Iterator

import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session

ADMIN_URL = os.environ.get("CC_TEST_ADMIN_URL", "postgresql+psycopg://postgres@127.0.0.1:5433/postgres")
TEST_URL = ADMIN_URL.rsplit("/", 1)[0] + "/cc_test"

os.environ.update(
    CC_ENV="test",
    CC_DATABASE_URL=TEST_URL,
    CC_STORAGE_LOCAL_DIR=tempfile.mkdtemp(prefix="cc-test-storage-"),
    CC_AI_BACKEND="fake",
    CC_MAIL_BACKEND="console",
    CC_APP_URL="http://testserver",
)

from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from PIL import Image  # noqa: E402

from app import security  # noqa: E402
from app.db import get_sessionmaker  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Base, ChecklistImport, Publisher, Series, Universe, User  # noqa: E402
from app.services import ai, catalog, imports, jobs, mail  # noqa: E402

KEEP = {"alembic_version", "universe", "publisher"}  # données de référence posées par la migration


@pytest.fixture(scope="session", autouse=True)
def database() -> None:
    engine = create_engine(ADMIN_URL, isolation_level="AUTOCOMMIT")
    with engine.connect() as connection:
        connection.execute(text("DROP DATABASE IF EXISTS cc_test WITH (FORCE)"))
        connection.execute(text("CREATE DATABASE cc_test"))
    command.upgrade(Config(os.path.join(os.path.dirname(__file__), "..", "alembic.ini")), "head")


@pytest.fixture(autouse=True)
def clean() -> None:
    tables = ", ".join(t.name for t in Base.metadata.sorted_tables if t.name not in KEEP)
    with get_sessionmaker()() as session:
        session.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
        session.commit()
    mail.outbox.clear()
    catalog._payload_cache.clear()  # les identifiants repartent de 1 à chaque test
    ai.FakeProvider.reading = None
    ai.FakeProvider.fail = None
    ai.FakeProvider.calls = 0


@pytest.fixture
def db() -> Iterator[Session]:
    with get_sessionmaker()() as session:
        yield session


API = "/api/v1"


class Account:
    """Un utilisateur connecté, avec son propre navigateur (ses propres cookies)."""

    def __init__(self, email: str, pseudo: str) -> None:
        self.http = TestClient(app)
        self.email, self.pseudo = email, pseudo
        response = self.http.post(
            f"{API}/auth/register",
            json={
                "email": email,
                "password": "mot-de-passe-solide",
                "pseudo": pseudo,
                "accept_terms": True,
                "age_confirmed": True,
            },
        )
        assert response.status_code == 201, response.text
        with get_sessionmaker()() as session:
            user = session.scalar(select(User).where(User.email == email))
            user.email_verified_at = security.now()
            session.commit()
            self.id = user.id

    def request(self, method: str, path: str, expect: int | None = None, **kwargs):
        response = self.http.request(method, f"{API}{path}", **kwargs)
        if expect is not None:
            assert response.status_code == expect, f"{method} {path} → {response.status_code} {response.text}"
        return response

    def get(self, path: str, expect: int | None = 200, **kwargs):
        return self.request("GET", path, expect, **kwargs).json()

    def post(self, path: str, json=None, expect: int | None = None, **kwargs):
        return self.request("POST", path, expect, json=json, **kwargs)

    def put(self, path: str, json=None, expect: int | None = 200):
        return self.request("PUT", path, expect, json=json).json()

    def patch(self, path: str, json=None, expect: int | None = 200):
        return self.request("PATCH", path, expect, json=json)

    def delete(self, path: str, expect: int | None = None, **kwargs):
        return self.request("DELETE", path, expect, **kwargs)

    def upload(self, image: bytes | None = None) -> str:
        files = {"file": ("carte.jpg", image or photo_bytes(), "image/jpeg")}
        return self.post("/photos", files=files, expect=201).json()["id"]


@pytest.fixture
def alice() -> Account:
    return Account("alice@example.org", "alice")


@pytest.fixture
def bob() -> Account:
    return Account("bob@example.org", "bob")


@pytest.fixture
def visitor() -> TestClient:
    return TestClient(app)


@pytest.fixture
def admin(db: Session) -> Account:
    account = Account("admin@example.org", "admin-test")
    user = db.get(User, account.id)
    user.role = "admin"
    # S-01 : un administrateur passe par la double authentification.
    user.totp_secret = security.new_totp_secret()
    user.totp_enabled_at = security.now()
    db.commit()
    import pyotp

    account.post("/auth/totp", json={"code": pyotp.TOTP(user.totp_secret).now()}, expect=204)
    return account


def photo_bytes(color: str = "orange", exif: Image.Exif | None = None, size=(600, 840)) -> bytes:
    buffer = io.BytesIO()
    image = Image.new("RGB", size, color)
    image.save(buffer, "JPEG", **({"exif": exif} if exif else {}))
    return buffer.getvalue()


def card(code: str, name: str, team: str = "", rookie: bool = False) -> dict:
    return {
        "code": code,
        "names": name.split(" / "),
        "teams": team.split(" / ") if team else [],
        "rookie": rookie,
    }


BASKET_DRAFT = {
    "groups": [
        {
            "name": "Base",
            "kind": "base",
            "cards": [
                card("83", "Nic Claxton", "Brooklyn Nets"),
                card("90", "Tre Mann", "Charlotte Hornets"),
                card("135", "Michael Porter Jr.", "Brooklyn Nets"),
                card("151", "Cooper Flagg", "Dallas Mavericks", rookie=True),
                card("261", "Mikel Brown Jr.", "Brooklyn Nets", rookie=True),
            ],
        },
        {
            "name": "Winning Kicks",
            "kind": "insert",
            "cards": [
                card("WK-3", "Kon Knueppel", "Charlotte Hornets"),
                card("WK-30", "Egor Dëmin", "Brooklyn Nets"),
            ],
        },
        {
            "name": "Rookie Dual Autographs",
            "kind": "auto",
            "cards": [
                card("RPD-MY", "Yaxel Lendeborg / Mikel Brown Jr.", "Michigan / Brooklyn Nets", rookie=True)
            ],
        },
    ]
}


def publish_series(
    db: Session,
    name: str = "Topps Flagship Basketball 2026/27",
    draft: dict | None = None,
    universe: str = "basket",
    season: str = "2026/27",
    series_id: int | None = None,
) -> Series:
    """Publie une série par le même chemin que l'outil d'administration."""
    admin = db.scalar(select(User).where(User.role == "admin"))
    if admin is None:
        admin = User(email="catalogue@example.org", pseudo="catalogue", role="admin")
        db.add(admin)
        db.flush()
    record = ChecklistImport(
        admin_id=admin.id,
        series_id=series_id,
        universe_id=db.scalar(select(Universe.id).where(Universe.slug == universe)),
        publisher_id=db.scalar(select(Publisher.id).where(Publisher.name == "Topps")),
        series_name=name,
        season=season,
        status="review",
        draft=imports.normalize_draft(draft or BASKET_DRAFT),
    )
    db.add(record)
    db.flush()
    series = imports.publish(db, admin, record)
    db.commit()
    return series


@pytest.fixture
def basket(db: Session) -> Series:
    return publish_series(db)


def refs(account: Account, series: Series) -> dict[str, int]:
    """Code → identifiant de référence, lu comme le fait l'interface."""
    payload = account.get(f"/catalog/series/{series.id}/cards")
    return {row[1]: row[0] for row in payload["cards"]}


def run_jobs() -> int:
    with get_sessionmaker()() as session:
        return jobs.run_all(session)
