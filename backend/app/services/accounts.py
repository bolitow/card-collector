"""Compte : inscription, export des données et suppression (F-28 à F-31, D-03)."""

import csv
import io
import json
import re
import uuid
import zipfile
from datetime import timedelta
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session, selectinload

from app import security
from app.config import get_settings
from app.errors import AppError, Conflict
from app.models import (
    CardRef,
    Job,
    PersonalCard,
    Photo,
    Purchase,
    User,
    UserCard,
    UserSeries,
    UserSession,
)
from app.services import jobs, mail, photos
from app.storage import get_storage

PSEUDO = re.compile(r"^[a-z0-9][a-z0-9_-]{2,23}$")
RESERVED = {
    "admin",
    "api",
    "catalogue",
    "collections",
    "achats",
    "recherche",
    "profil",
    "connexion",
    "inscription",
}
DELETE_WORD = "SUPPRIMER"  # RG-08 : mot à retaper pour supprimer le compte


def check_pseudo(db: Session, pseudo: str, current: User | None = None) -> str:
    """F-29 : pseudonyme unique ; il forme l'adresse du profil public."""
    pseudo = pseudo.strip().lower()
    if not PSEUDO.match(pseudo) or pseudo in RESERVED:
        raise AppError(code="pseudo_invalid")
    taken = db.scalar(select(User).where(User.pseudo == pseudo))
    if taken and (current is None or taken.id != current.id):
        raise Conflict(code="pseudo_taken")
    return pseudo


def register(db: Session, email: str, password: str | None, pseudo: str, locale: str = "fr") -> User:
    if db.scalar(select(User).where(User.email == email)):
        raise Conflict(code="email_taken")
    settings = get_settings()
    user = User(
        id=uuid.uuid4(),
        email=email,
        pseudo=check_pseudo(db, pseudo),
        password_hash=security.hash_password(password) if password else None,
        locale=locale,
        terms_version=settings.terms_version,  # F-29 : CGU et politique de confidentialité acceptées
        terms_accepted_at=security.now(),
        age_confirmed_at=security.now(),  # 15 ans ou plus, ou accord d'un parent (section 2)
    )
    db.add(user)
    db.flush()
    return user


def send_link(
    db: Session, user: User, kind: str, path: str, to: str | None = None, payload: dict | None = None
) -> None:
    token = security.issue_token(db, user, kind, payload)
    link = f"{get_settings().app_url}{path}?token={token}"
    jobs.enqueue(db, "send_email", {"to": to or user.email, "template": kind, "link": link}, user.id)


# --------------------------------------------------------------- export


def export_data(db: Session, user: User) -> dict[str, Any]:
    """D-03 : accès et portabilité — tout ce que l'application sait de l'utilisateur."""
    collections = db.scalars(select(UserSeries).where(UserSeries.user_id == user.id)).all()
    cards = db.scalars(
        select(UserCard)
        .options(
            selectinload(UserCard.parallels), selectinload(UserCard.card_ref).selectinload(CardRef.group)
        )
        .where(UserCard.user_id == user.id)
    ).all()
    personal = db.scalars(select(PersonalCard).where(PersonalCard.user_id == user.id)).all()
    purchases = db.scalars(select(Purchase).where(Purchase.user_id == user.id).order_by(Purchase.id)).all()

    def photo(photo_id: uuid.UUID | None) -> str | None:
        return f"photos/{photo_id}.webp" if photo_id else None

    return {
        "compte": {
            "email": user.email,
            "pseudo": user.pseudo,
            "langue": user.locale,
            "devise": user.currency,
            "inscrit_le": user.created_at.isoformat(),
            "cgu_acceptees": user.terms_version,
            "profil_public": user.public_profile,
        },
        "collections": [
            {
                "serie": c.series.name if c.series else c.personal_name,
                "personnelle": c.series_id is None,
                "statut": c.status,
                "equipe_prioritaire": c.priority_team.name if c.priority_team else None,
                "partagee": c.shared,
            }
            for c in collections
        ],
        "cartes": [
            {
                "serie": c.card_ref.series.name,
                "sous_serie": c.card_ref.group.name,
                "code": c.card_ref.code,
                "nom": c.card_ref.name,
                "quantite": c.quantity,
                "recherchee": c.wanted,
                "note": c.note,
                "photo": photo(c.photo_id),
                "paralleles": [
                    {"nom": p.name, "photo": photo(p.photo_id), "vendu": p.sold} for p in c.parallels
                ],
            }
            for c in cards
        ],
        "cartes_personnelles": [
            {
                "code": c.code,
                "nom": c.name,
                "quantite": c.quantity,
                "note": c.note,
                "photo": photo(c.photo_id),
            }
            for c in personal
        ],
        "achats": [
            {
                "serie": p.series_name,
                "code": p.code,
                "nom": p.name,
                "variante": p.variant,
                "prix": str(p.price) if p.price is not None else None,
                "frais": str(p.fees) if p.fees is not None else None,
                "achete_le": p.bought_on.isoformat() if p.bought_on else None,
                "plateforme": p.platform,
                "note": p.note,
                "vendu": p.sold,
                "prix_de_vente": str(p.sale_price) if p.sale_price is not None else None,
                "frais_de_vente": str(p.sale_fees) if p.sale_fees is not None else None,
                "vendu_le": p.sold_on.isoformat() if p.sold_on else None,
                "photo": photo(p.photo_id),
            }
            for p in purchases
        ],
    }


def _csv(rows: list[dict[str, Any]], columns: list[str]) -> str:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, columns, extrasaction="ignore", delimiter=";")
    writer.writeheader()
    writer.writerows(rows)
    return "﻿" + buffer.getvalue()  # BOM : Excel ouvre le fichier en UTF-8


@jobs.handler("export_data")
def export_job(db: Session, job: Job) -> dict:
    """F-31 : archive JSON + CSV + photos, puis e-mail « export prêt »."""
    user = db.get(User, job.user_id)
    data = export_data(db, user)
    storage = get_storage()
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("donnees.json", json.dumps(data, ensure_ascii=False, indent=2))
        cards = [{**c, "paralleles": ", ".join(p["nom"] for p in c["paralleles"])} for c in data["cartes"]]
        archive.writestr(
            "collections.csv",
            _csv(
                cards, ["serie", "sous_serie", "code", "nom", "quantite", "paralleles", "recherchee", "note"]
            ),
        )
        archive.writestr(
            "achats.csv",
            _csv(
                data["achats"],
                [
                    "serie",
                    "code",
                    "nom",
                    "variante",
                    "prix",
                    "frais",
                    "achete_le",
                    "plateforme",
                    "vendu",
                    "prix_de_vente",
                    "frais_de_vente",
                    "vendu_le",
                    "note",
                ],
            ),
        )
        for item in db.scalars(select(Photo).where(Photo.user_id == user.id)):
            content = storage.get(f"{item.key_prefix}/large.webp")
            archive.writestr(f"photos/{item.id}.webp", content, zipfile.ZIP_STORED)
    key = f"exports/{user.id}/{job.id}.zip"
    storage.put(key, buffer.getvalue(), "application/zip")
    settings = get_settings()
    mail.send(
        user.email,
        "export_ready",
        link=f"{settings.app_url}/profil/donnees",
        days=settings.export_retention_days,
    )
    return {"key": key, "bytes": buffer.tell()}


def purge_exports(db: Session) -> None:
    """Les archives d'export ne sont gardées que quelques jours."""
    limit = security.now() - timedelta(days=get_settings().export_retention_days)
    old = db.scalars(
        select(Job).where(Job.kind == "export_data", Job.status == "done", Job.finished_at < limit)
    ).all()
    get_storage().delete([job.result["key"] for job in old if job.result.get("key")])
    for job in old:
        db.delete(job)
    db.execute(delete(Job).where(Job.status == "done", Job.finished_at < limit))


# ------------------------------------------------------------ suppression


def request_deletion(db: Session, user: User, word: str) -> None:
    """F-31, RG-08 : la suppression demande de retaper un mot de confirmation."""
    if word.strip().upper() != DELETE_WORD:
        raise AppError(code="confirmation_mismatch", expected=DELETE_WORD)
    user.status = "deleting"  # le compte est inaccessible dès maintenant
    db.execute(delete(UserSession).where(UserSession.user_id == user.id))
    jobs.enqueue(db, "delete_account", {"email": user.email}, user.id)


@jobs.handler("delete_account")
def delete_account_job(db: Session, job: Job) -> None:
    """CA-16 : plus aucune donnée ni photo du compte, en base comme dans le stockage."""
    user = db.get(User, job.user_id) if job.user_id else None
    email = job.payload.get("email")
    if user is not None:
        photos.delete_all_for_user(db, user.id)
        exports = db.scalars(select(Job).where(Job.user_id == user.id, Job.kind == "export_data")).all()
        get_storage().delete([e.result["key"] for e in exports if e.result.get("key")])
        db.execute(delete(Job).where(Job.user_id == user.id, Job.id != job.id))
        db.execute(delete(User).where(User.id == user.id))  # les suppressions en cascade font le reste
    job.payload = {}
    if email:
        mail.send(email, "account_deleted", days=get_settings().account_deletion_days)
