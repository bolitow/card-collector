"""Modèle de données (section 9 du cahier des charges, écarts expliqués dans docs/architecture.md)."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Computed,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, CITEXT, JSONB, TSVECTOR
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

GROUP_KINDS = ("base", "insert", "special", "relic", "auto")  # glossaire : types de carte

TZDateTime = DateTime(timezone=True)
Money = Numeric(10, 2)


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


class Base(DeclarativeBase):
    pass


class Timestamps:
    created_at: Mapped[datetime] = mapped_column(TZDateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(TZDateTime, server_default=func.now(), onupdate=func.now())


# --------------------------------------------------------------------------- comptes


class User(Base, Timestamps):
    __tablename__ = "app_user"
    __table_args__ = (
        CheckConstraint(_in("role", ("collector", "admin")), name="user_role"),
        CheckConstraint(_in("status", ("active", "suspended", "deleting")), name="user_status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(CITEXT, unique=True)
    email_verified_at: Mapped[datetime | None] = mapped_column(TZDateTime)
    password_hash: Mapped[str | None] = mapped_column(Text)
    pseudo: Mapped[str] = mapped_column(CITEXT, unique=True)  # adresse du profil public (F-29)
    avatar_photo_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("photo.id", ondelete="SET NULL", use_alter=True, name="fk_app_user_avatar_photo")
    )
    locale: Mapped[str] = mapped_column(Text, server_default="fr")
    currency: Mapped[str] = mapped_column(Text, server_default="EUR")
    theme: Mapped[str] = mapped_column(Text, server_default="auto")
    role: Mapped[str] = mapped_column(Text, server_default="collector")
    status: Mapped[str] = mapped_column(Text, server_default="active")
    suspended_reason: Mapped[str | None] = mapped_column(Text)
    plan: Mapped[str] = mapped_column(Text, server_default="free")
    # Consentements (F-29, D-01). L'âge est déclaratif : aucune date de naissance n'est stockée.
    terms_version: Mapped[str | None] = mapped_column(Text)
    terms_accepted_at: Mapped[datetime | None] = mapped_column(TZDateTime)
    age_confirmed_at: Mapped[datetime | None] = mapped_column(TZDateTime)
    notify_series_published: Mapped[bool] = mapped_column(Boolean, server_default="true")
    # Partage (RG-02) : rien n'est public par défaut.
    public_profile: Mapped[bool] = mapped_column(Boolean, server_default="false")
    share_singles: Mapped[bool] = mapped_column(Boolean, server_default="false")
    # Quotas d'IA propres à l'utilisateur ; NULL = quota de l'offre (RG-20).
    ai_quota_day: Mapped[int | None] = mapped_column(Integer)
    ai_quota_month: Mapped[int | None] = mapped_column(Integer)
    totp_secret: Mapped[str | None] = mapped_column(Text)
    totp_enabled_at: Mapped[datetime | None] = mapped_column(TZDateTime)
    last_seen_at: Mapped[datetime | None] = mapped_column(TZDateTime)


class UserSession(Base):
    __tablename__ = "session"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("app_user.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(Text, unique=True)
    user_agent: Mapped[str] = mapped_column(Text, server_default="")
    ip: Mapped[str] = mapped_column(Text, server_default="")
    mfa_verified: Mapped[bool] = mapped_column(Boolean, server_default="false")
    created_at: Mapped[datetime] = mapped_column(TZDateTime, server_default=func.now())
    last_seen_at: Mapped[datetime] = mapped_column(TZDateTime, server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(TZDateTime)

    user: Mapped[User] = relationship()


class AuthToken(Base):
    """Jeton à usage unique : vérification d'adresse, mot de passe oublié, lien de connexion."""

    __tablename__ = "auth_token"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("app_user.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(Text)
    token_hash: Mapped[str] = mapped_column(Text, unique=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default="{}")
    expires_at: Mapped[datetime] = mapped_column(TZDateTime)
    used_at: Mapped[datetime | None] = mapped_column(TZDateTime)


class OAuthIdentity(Base):
    __tablename__ = "oauth_identity"

    provider: Mapped[str] = mapped_column(Text, primary_key=True)
    subject: Mapped[str] = mapped_column(Text, primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("app_user.id", ondelete="CASCADE"), index=True)


# ------------------------------------------------------------------------- catalogue


class Universe(Base):
    __tablename__ = "universe"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    slug: Mapped[str] = mapped_column(Text, unique=True)
    name: Mapped[str] = mapped_column(Text)
    color_light: Mapped[str] = mapped_column(Text)
    color_dark: Mapped[str] = mapped_column(Text)
    position: Mapped[int] = mapped_column(Integer, server_default="0")


class Publisher(Base):
    __tablename__ = "publisher"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(CITEXT, unique=True)


class Series(Base, Timestamps):
    __tablename__ = "series"
    __table_args__ = (CheckConstraint(_in("status", ("draft", "published", "hidden")), name="series_status"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(CITEXT, unique=True)  # convention 9.2
    publisher_id: Mapped[int] = mapped_column(ForeignKey("publisher.id"))
    universe_id: Mapped[int] = mapped_column(ForeignKey("universe.id"), index=True)
    season: Mapped[str] = mapped_column(Text, server_default="")
    release_date: Mapped[date | None] = mapped_column(Date)
    source: Mapped[str] = mapped_column(Text, server_default="")
    source_date: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(Text, server_default="draft")
    version: Mapped[int] = mapped_column(Integer, server_default="0")
    card_count: Mapped[int] = mapped_column(Integer, server_default="0")
    published_at: Mapped[datetime | None] = mapped_column(TZDateTime)

    publisher: Mapped[Publisher] = relationship(lazy="joined")
    universe: Mapped[Universe] = relationship(lazy="joined")
    groups: Mapped[list[SeriesGroup]] = relationship(order_by="SeriesGroup.position", back_populates="series")


class SeriesGroup(Base):
    """Sous-série : une section de la checklist, avec un type de carte."""

    __tablename__ = "series_group"
    __table_args__ = (
        UniqueConstraint("series_id", "name"),
        CheckConstraint(_in("kind", GROUP_KINDS), name="group_kind"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    series_id: Mapped[int] = mapped_column(ForeignKey("series.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(Text)
    prefix: Mapped[str] = mapped_column(Text, server_default="")
    position: Mapped[int] = mapped_column(Integer, server_default="0")
    card_count: Mapped[int] = mapped_column(Integer, server_default="0")

    series: Mapped[Series] = relationship(back_populates="groups")


class Team(Base):
    __tablename__ = "team"
    __table_args__ = (UniqueConstraint("universe_id", "name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    universe_id: Mapped[int] = mapped_column(ForeignKey("universe.id"))
    name: Mapped[str] = mapped_column(Text)
    franchise: Mapped[str | None] = mapped_column(Text)  # annexe A15, prévu sans refonte


class CardRef(Base):
    """Référence : une carte du catalogue. Son identifiant ne change jamais (RG-04)."""

    __tablename__ = "card_ref"
    __table_args__ = (
        UniqueConstraint("series_id", "code_key"),  # RG-13 : « 007 » = « 7 »
        CheckConstraint(_in("status", ("active", "hidden")), name="card_ref_status"),
        Index("ix_card_ref_series_position", "series_id", "position"),
        Index("ix_card_ref_search", "search_tsv", postgresql_using="gin"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    series_id: Mapped[int] = mapped_column(ForeignKey("series.id", ondelete="CASCADE"))
    group_id: Mapped[int] = mapped_column(ForeignKey("series_group.id"), index=True)
    code: Mapped[str] = mapped_column(Text)  # tel qu'imprimé, normalisé (RG-13)
    code_key: Mapped[str] = mapped_column(Text)  # clé d'égalité
    name: Mapped[str] = mapped_column(Text, server_default="")
    rookie: Mapped[bool] = mapped_column(Boolean, server_default="false")
    position: Mapped[int] = mapped_column(Integer, server_default="0")
    status: Mapped[str] = mapped_column(Text, server_default="active")
    merged_into_id: Mapped[int | None] = mapped_column(ForeignKey("card_ref.id"))
    search_tokens: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default="{}")
    search_tsv: Mapped[Any] = mapped_column(
        TSVECTOR, Computed("array_to_tsvector(search_tokens)", persisted=True)
    )

    group: Mapped[SeriesGroup] = relationship()
    series: Mapped[Series] = relationship()
    teams: Mapped[list[Team]] = relationship(secondary="card_ref_team", order_by="Team.name")


class CardRefTeam(Base):
    __tablename__ = "card_ref_team"

    card_ref_id: Mapped[int] = mapped_column(ForeignKey("card_ref.id", ondelete="CASCADE"), primary_key=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("team.id"), primary_key=True, index=True)


class OfficialParallel(Base):
    """Parallèles officiels d'une série, proposés en suggestion (F-16)."""

    __tablename__ = "official_parallel"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    series_id: Mapped[int] = mapped_column(ForeignKey("series.id", ondelete="CASCADE"), index=True)
    group_id: Mapped[int | None] = mapped_column(ForeignKey("series_group.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(Text)
    print_run: Mapped[int | None] = mapped_column(Integer)


class ChaseMark(Base):
    """Carte recherchée éditoriale (RG-17)."""

    __tablename__ = "chase_mark"

    card_ref_id: Mapped[int] = mapped_column(ForeignKey("card_ref.id", ondelete="CASCADE"), primary_key=True)
    reason: Mapped[str] = mapped_column(Text, server_default="")
    sources: Mapped[str] = mapped_column(Text, server_default="")
    marked_on: Mapped[date] = mapped_column(Date, server_default=func.current_date())
    author_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("app_user.id", ondelete="SET NULL"))


class SeriesVersion(Base):
    """Historique des publications d'une série (F-46)."""

    __tablename__ = "series_version"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    series_id: Mapped[int] = mapped_column(ForeignKey("series.id", ondelete="CASCADE"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    admin_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("app_user.id", ondelete="SET NULL"))
    summary: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default="{}")
    published_at: Mapped[datetime] = mapped_column(TZDateTime, server_default=func.now())


# ------------------------------------------------------- données de l'utilisateur


class Photo(Base):
    """Photo d'un utilisateur (RG-14). Trois tailles sous `key_prefix` : thumb, medium, large."""

    __tablename__ = "photo"
    __table_args__ = (UniqueConstraint("user_id", "sha256"),)

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("app_user.id", ondelete="CASCADE"), index=True)
    key_prefix: Mapped[str] = mapped_column(Text)
    width: Mapped[int] = mapped_column(Integer)
    height: Mapped[int] = mapped_column(Integer)
    bytes: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(TZDateTime, server_default=func.now())


class UserSeries(Base, Timestamps):
    """Collection : une série suivie (ou en réserve), ou une collection personnelle (F-35)."""

    __tablename__ = "user_series"
    __table_args__ = (
        UniqueConstraint("user_id", "series_id"),
        CheckConstraint("series_id IS NOT NULL OR personal_name IS NOT NULL", name="user_series_target"),
        CheckConstraint(_in("status", ("followed", "reserve")), name="user_series_status"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("app_user.id", ondelete="CASCADE"), index=True)
    series_id: Mapped[int | None] = mapped_column(ForeignKey("series.id"), index=True)
    personal_name: Mapped[str | None] = mapped_column(Text)
    universe_id: Mapped[int | None] = mapped_column(ForeignKey("universe.id"))
    status: Mapped[str] = mapped_column(Text, server_default="followed")
    priority_team_id: Mapped[int | None] = mapped_column(ForeignKey("team.id"))  # RG-16
    # Partage par collection (F-42, F-44).
    shared: Mapped[bool] = mapped_column(Boolean, server_default="false")
    share_photos_only: Mapped[bool] = mapped_column(Boolean, server_default="true")
    share_missing: Mapped[bool] = mapped_column(Boolean, server_default="false")

    series: Mapped[Series | None] = relationship()
    priority_team: Mapped[Team | None] = relationship()


class UserCard(Base, Timestamps):
    """État d'une référence pour un utilisateur. Créée à la première action sur la carte.

    Rattachée à la référence et non à la collection : la possession survit à « Ne plus suivre » (RG-12).
    """

    __tablename__ = "user_card"
    __table_args__ = (
        UniqueConstraint("user_id", "card_ref_id"),
        CheckConstraint("quantity BETWEEN 0 AND 999", name="user_card_quantity"),  # RG-06
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("app_user.id", ondelete="CASCADE"))
    card_ref_id: Mapped[int] = mapped_column(ForeignKey("card_ref.id"), index=True)
    quantity: Mapped[int] = mapped_column(SmallInteger, server_default="0")  # exemplaires classiques
    parallel_count: Mapped[int] = mapped_column(SmallInteger, server_default="0")  # parallèles non vendus
    # RG-05 : un parallèle suffit à rendre la carte possédée.
    owned: Mapped[bool] = mapped_column(
        Boolean, Computed("quantity > 0 OR parallel_count > 0", persisted=True)
    )
    photo_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("photo.id", ondelete="SET NULL"))
    wanted: Mapped[bool] = mapped_column(Boolean, server_default="false")  # marque personnelle (RG-17)
    note: Mapped[str] = mapped_column(Text, server_default="")

    card_ref: Mapped[CardRef] = relationship()
    parallels: Mapped[list[UserParallel]] = relationship(
        back_populates="user_card", order_by="UserParallel.id", cascade="all, delete-orphan"
    )


class UserParallel(Base):
    __tablename__ = "user_parallel"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_card_id: Mapped[int] = mapped_column(ForeignKey("user_card.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("app_user.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(Text)
    photo_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("photo.id", ondelete="SET NULL"))
    # CA-08 : supprimer l'achat laisse le parallèle, sans prix.
    purchase_id: Mapped[int | None] = mapped_column(
        ForeignKey("purchase.id", ondelete="SET NULL"), unique=True
    )
    # Vrai tant que l'achat relié est vendu : le parallèle ne compte plus (RG-02, RG-18).
    sold: Mapped[bool] = mapped_column(Boolean, server_default="false")
    created_at: Mapped[datetime] = mapped_column(TZDateTime, server_default=func.now())

    user_card: Mapped[UserCard] = relationship(back_populates="parallels")


class PersonalCard(Base, Timestamps):
    """Carte ajoutée par l'utilisateur hors catalogue, visible de lui seul (RG-03)."""

    __tablename__ = "personal_card"
    __table_args__ = (
        UniqueConstraint("user_series_id", "code_key"),
        CheckConstraint("quantity BETWEEN 0 AND 999", name="personal_card_quantity"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("app_user.id", ondelete="CASCADE"), index=True)
    user_series_id: Mapped[int] = mapped_column(ForeignKey("user_series.id", ondelete="CASCADE"), index=True)
    code: Mapped[str] = mapped_column(Text)
    code_key: Mapped[str] = mapped_column(Text)
    name: Mapped[str] = mapped_column(Text, server_default="")
    quantity: Mapped[int] = mapped_column(SmallInteger, server_default="1")
    photo_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("photo.id", ondelete="SET NULL"))
    note: Mapped[str] = mapped_column(Text, server_default="")


class Purchase(Base, Timestamps):
    __tablename__ = "purchase"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("app_user.id", ondelete="CASCADE"), index=True)
    # RG-10 : lien par identifiant ; `series_name` porte le nom libre quand la série n'est pas au catalogue.
    series_id: Mapped[int | None] = mapped_column(ForeignKey("series.id"), index=True)
    series_name: Mapped[str] = mapped_column(Text)
    universe_id: Mapped[int | None] = mapped_column(ForeignKey("universe.id"))
    card_ref_id: Mapped[int | None] = mapped_column(ForeignKey("card_ref.id"), index=True)
    code: Mapped[str] = mapped_column(Text, server_default="")
    name: Mapped[str] = mapped_column(Text, server_default="")
    variant: Mapped[str] = mapped_column(Text, server_default="")
    # Choix forcé « Parallèle » / « Carte de base » (F-20) ; NULL = déduit de la variante (RG-09).
    as_parallel: Mapped[bool | None] = mapped_column(Boolean)
    # Vrai une fois l'achat reporté dans la collection (RG-09, RG-12).
    applied: Mapped[bool] = mapped_column(Boolean, server_default="false")
    photo_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("photo.id", ondelete="SET NULL"))
    price: Mapped[Decimal | None] = mapped_column(Money)
    fees: Mapped[Decimal | None] = mapped_column(Money)
    bought_on: Mapped[date | None] = mapped_column(Date)
    platform: Mapped[str] = mapped_column(Text, server_default="")
    note: Mapped[str] = mapped_column(Text, server_default="")
    # Vente (RG-18).
    sold: Mapped[bool] = mapped_column(Boolean, server_default="false")
    sale_price: Mapped[Decimal | None] = mapped_column(Money)
    sale_fees: Mapped[Decimal | None] = mapped_column(Money)
    sold_on: Mapped[date | None] = mapped_column(Date)
    sale_removed_copy: Mapped[bool] = mapped_column(Boolean, server_default="false")

    series: Mapped[Series | None] = relationship()
    card_ref: Mapped[CardRef | None] = relationship()


class ShareLink(Base):
    """Lien secret vers une seule collection, révocable (F-42)."""

    __tablename__ = "share_link"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("app_user.id", ondelete="CASCADE"), index=True)
    user_series_id: Mapped[int] = mapped_column(ForeignKey("user_series.id", ondelete="CASCADE"))
    token: Mapped[str] = mapped_column(Text, unique=True)
    created_at: Mapped[datetime] = mapped_column(TZDateTime, server_default=func.now())
    revoked_at: Mapped[datetime | None] = mapped_column(TZDateTime)


# ------------------------------------------------------------ file de travail


class SeriesRequest(Base, Timestamps):
    """Demande d'ajout d'une série (F-34)."""

    __tablename__ = "series_request"
    __table_args__ = (
        CheckConstraint(_in("status", ("open", "accepted", "declined", "published")), name="request_status"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("app_user.id", ondelete="SET NULL"))
    name: Mapped[str] = mapped_column(Text)
    url: Mapped[str] = mapped_column(Text, server_default="")
    note: Mapped[str] = mapped_column(Text, server_default="")
    status: Mapped[str] = mapped_column(Text, server_default="open")
    series_id: Mapped[int | None] = mapped_column(ForeignKey("series.id", ondelete="SET NULL"))
    admin_reply: Mapped[str] = mapped_column(Text, server_default="")


class SeriesRequestVote(Base):
    """« Moi aussi » sur une demande de série : sert à prioriser la file de travail (ajout)."""

    __tablename__ = "series_request_vote"

    request_id: Mapped[int] = mapped_column(
        ForeignKey("series_request.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("app_user.id", ondelete="CASCADE"), primary_key=True
    )


class Report(Base, Timestamps):
    """Signalement : erreur du catalogue (RG-03) ou contenu d'un profil public (F-45)."""

    __tablename__ = "report"
    __table_args__ = (
        CheckConstraint(_in("kind", ("catalog", "content")), name="report_kind"),
        CheckConstraint(_in("status", ("open", "resolved", "dismissed")), name="report_status"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    reporter_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("app_user.id", ondelete="SET NULL"))
    kind: Mapped[str] = mapped_column(Text)
    series_id: Mapped[int | None] = mapped_column(ForeignKey("series.id", ondelete="SET NULL"))
    card_ref_id: Mapped[int | None] = mapped_column(ForeignKey("card_ref.id", ondelete="SET NULL"))
    target_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("app_user.id", ondelete="CASCADE"))
    photo_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("photo.id", ondelete="SET NULL"))
    message: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, server_default="open")
    admin_reply: Mapped[str] = mapped_column(Text, server_default="")


class ChecklistImport(Base, Timestamps):
    """Import d'une checklist (F-36). Le brouillon reste hors catalogue jusqu'à la publication (RG-19)."""

    __tablename__ = "checklist_import"
    __table_args__ = (
        CheckConstraint(
            _in("status", ("uploaded", "analyzing", "review", "published", "failed")), name="import_status"
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    admin_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("app_user.id", ondelete="SET NULL"))
    series_id: Mapped[int | None] = mapped_column(ForeignKey("series.id", ondelete="SET NULL"))
    universe_id: Mapped[int] = mapped_column(ForeignKey("universe.id"))
    publisher_id: Mapped[int] = mapped_column(ForeignKey("publisher.id"))
    series_name: Mapped[str] = mapped_column(Text, server_default="")
    season: Mapped[str] = mapped_column(Text, server_default="")
    source: Mapped[str] = mapped_column(Text, server_default="")
    source_text: Mapped[str] = mapped_column(Text, server_default="")
    use_ai: Mapped[bool] = mapped_column(Boolean, server_default="true")
    status: Mapped[str] = mapped_column(Text, server_default="uploaded")
    draft: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default="{}")
    error: Mapped[str] = mapped_column(Text, server_default="")


# ------------------------------------------------------------- technique


class Job(Base):
    """Tâche de fond (T-05). Le worker prend les lignes `queued` avec FOR UPDATE SKIP LOCKED."""

    __tablename__ = "job"
    __table_args__ = (
        CheckConstraint(_in("status", ("queued", "running", "done", "failed")), name="job_status"),
        Index("ix_job_queue", "status", "run_after"),
    )

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    kind: Mapped[str] = mapped_column(Text)
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("app_user.id", ondelete="SET NULL"), index=True
    )
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default="{}")
    status: Mapped[str] = mapped_column(Text, server_default="queued")
    progress: Mapped[int] = mapped_column(Integer, server_default="0")
    result: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default="{}")
    error: Mapped[str] = mapped_column(Text, server_default="")
    attempts: Mapped[int] = mapped_column(Integer, server_default="0")
    run_after: Mapped[datetime] = mapped_column(TZDateTime, server_default=func.now())
    created_at: Mapped[datetime] = mapped_column(TZDateTime, server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(TZDateTime)


class AiCall(Base):
    """Journal des appels à l'IA (IA-02) ; sert aussi au calcul des quotas (RG-20)."""

    __tablename__ = "ai_call"
    __table_args__ = (Index("ix_ai_call_user_time", "user_id", "created_at"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("app_user.id", ondelete="SET NULL"))
    function: Mapped[str] = mapped_column(Text)
    model: Mapped[str] = mapped_column(Text)
    duration_ms: Mapped[int] = mapped_column(Integer, server_default="0")
    input_tokens: Mapped[int] = mapped_column(Integer, server_default="0")
    output_tokens: Mapped[int] = mapped_column(Integer, server_default="0")
    cost_usd: Mapped[Decimal] = mapped_column(Numeric(10, 6), server_default="0")
    outcome: Mapped[str] = mapped_column(Text)  # ok, invalid, error
    created_at: Mapped[datetime] = mapped_column(TZDateTime, server_default=func.now())


class AuditLog(Base):
    """Journal des actions des administrateurs (RG-01, F-49)."""

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    admin_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("app_user.id", ondelete="SET NULL"))
    action: Mapped[str] = mapped_column(Text)
    target: Mapped[str] = mapped_column(Text, server_default="")
    reason: Mapped[str] = mapped_column(Text, server_default="")
    data: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default="{}")
    created_at: Mapped[datetime] = mapped_column(TZDateTime, server_default=func.now())


class RateLimit(Base):
    """Compteur par fenêtre fixe (S-04)."""

    __tablename__ = "rate_limit"

    key: Mapped[str] = mapped_column(Text, primary_key=True)
    window_start: Mapped[datetime] = mapped_column(TZDateTime, primary_key=True)
    count: Mapped[int] = mapped_column(Integer, server_default="0")
