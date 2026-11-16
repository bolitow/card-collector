"""Schémas d'entrée et de sortie de l'API. Les types TypeScript de l'interface en sont générés.

Les schémas `Public*` décrivent tout ce qu'un visiteur peut recevoir (RG-02) : ils n'ont aucun champ
de prix, de date d'achat, de plateforme ni de quantité.
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import AfterValidator, BaseModel, ConfigDict, EmailStr, Field


class Out(BaseModel):
    model_config = ConfigDict(from_attributes=True)


def _cents(value: Decimal | None) -> Decimal | None:
    """Les montants sortent toujours avec deux décimales, qu'ils viennent de la base ou d'une saisie."""
    return None if value is None else value.quantize(Decimal("0.01"))


Amount = Annotated[Decimal | None, AfterValidator(_cents)]
Cents = Annotated[Decimal, AfterValidator(_cents)]

# ------------------------------------------------------------------ comptes


class RegisterIn(BaseModel):
    email: EmailStr
    password: str | None = None  # absent : connexion par lien envoyé par e-mail
    pseudo: str
    accept_terms: bool
    age_confirmed: bool
    locale: str = "fr"


class LoginIn(BaseModel):
    email: EmailStr
    password: str
    totp: str | None = None


class EmailIn(BaseModel):
    email: EmailStr


class TokenIn(BaseModel):
    token: str


class ResetPasswordIn(BaseModel):
    token: str
    password: str


class QuotaOut(BaseModel):
    day_limit: int
    month_limit: int
    day_used: int
    month_used: int


class MeOut(BaseModel):
    id: UUID
    email: str
    email_verified: bool
    pseudo: str
    locale: str
    currency: str
    theme: str
    role: str
    avatar_photo_id: UUID | None
    public_profile: bool
    share_singles: bool
    notify_series_published: bool
    has_password: bool
    totp_enabled: bool
    admin_access: Literal["ok", "totp_setup_required", "totp_required"] | None
    ai: QuotaOut
    ai_available: bool


class MeIn(BaseModel):
    pseudo: str | None = None
    locale: str | None = None
    currency: str | None = Field(None, pattern="^[A-Z]{3}$")
    theme: Literal["auto", "light", "dark"] | None = None
    avatar_photo_id: UUID | None = None
    public_profile: bool | None = None
    share_singles: bool | None = None
    notify_series_published: bool | None = None


class PasswordIn(BaseModel):
    current: str | None = None
    new: str


class ChangeEmailIn(BaseModel):
    email: EmailStr


class DeleteAccountIn(BaseModel):
    word: str


class TotpIn(BaseModel):
    code: str


class TotpSetupOut(BaseModel):
    secret: str
    uri: str


class SessionOut(Out):
    id: int
    user_agent: str
    ip: str
    created_at: datetime
    last_seen_at: datetime
    current: bool = False


class JobOut(Out):
    id: UUID
    kind: str
    status: str
    progress: int
    error: str
    result: dict[str, Any]
    created_at: datetime
    finished_at: datetime | None


# ---------------------------------------------------------------- catalogue


class UniverseOut(Out):
    id: int
    slug: str
    name: str
    color_light: str
    color_dark: str


class PublisherOut(Out):
    id: int
    name: str


class CatalogOut(BaseModel):
    universes: list[UniverseOut]
    publishers: list[PublisherOut]
    seasons: list[str]


class SeriesOut(BaseModel):
    id: int
    name: str
    short_name: str
    publisher: str
    universe_id: int
    season: str
    card_count: int
    version: int
    followed: bool = False


class GroupOut(BaseModel):
    name: str
    kind: str
    card_count: int


class ChaseOut(BaseModel):
    card_ref_id: int
    code: str
    name: str
    reason: str


class SeriesDetailOut(SeriesOut):
    release_date: date | None
    source: str
    source_date: date | None
    groups: list[GroupOut]
    counts: dict[str, int]
    chase: list[ChaseOut]
    has_teams: bool
    collection_id: int | None = None


class SeriesRequestIn(BaseModel):
    name: str = Field(min_length=3, max_length=200)
    url: str = Field("", max_length=500)
    note: str = Field("", max_length=1000)


class SeriesRequestOut(BaseModel):
    id: int
    name: str
    url: str
    status: str
    admin_reply: str
    votes: int
    mine: bool
    voted: bool
    series_id: int | None
    created_at: datetime


class ReportIn(BaseModel):
    kind: Literal["catalog", "content"]
    message: str = Field(min_length=3, max_length=2000)
    series_id: int | None = None
    card_ref_id: int | None = None
    pseudo: str | None = None
    photo_id: UUID | None = None


# -------------------------------------------------------------- collections


class CollectionOut(BaseModel):
    id: int
    series_id: int | None
    name: str
    short_name: str
    universe_id: int | None
    publisher: str
    season: str
    status: str
    priority_team: str | None
    shared: bool
    owned: int
    total: int
    percent: int
    label: str


class HomeOut(BaseModel):
    collections: list[CollectionOut]
    isolated_cards: int
    isolated_series: int


class FollowIn(BaseModel):
    series_id: int


class PersonalCollectionIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    universe_id: int | None = None
    codes: str = ""


class CollectionIn(BaseModel):
    status: Literal["followed", "reserve"] | None = None
    priority_team: str | None = None
    clear_priority_team: bool = False
    shared: bool | None = None
    share_photos_only: bool | None = None
    share_missing: bool | None = None


class PersonalCardOut(Out):
    id: int
    code: str
    name: str
    quantity: int
    photo_id: UUID | None
    note: str


class PersonalCardIn(BaseModel):
    code: str | None = None
    name: str | None = None
    quantity: int | None = Field(None, ge=0, le=999)
    photo_id: UUID | None = None
    note: str | None = None


class CollectionDetailOut(CollectionOut):
    series_version: int | None
    share_photos_only: bool
    share_missing: bool
    # {identifiant de référence: [quantité, parallèles, photo, recherchée]}
    cards: dict[int, list[int]]
    personal: list[PersonalCardOut]


class ImportCodesIn(BaseModel):
    text: str = Field(max_length=200_000)


class ImportCodesOut(BaseModel):
    checked: int
    already: int
    unknown: list[str]


class CardStateIn(BaseModel):
    quantity: int | None = Field(None, ge=0, le=999)
    wanted: bool | None = None
    note: str | None = None
    photo_id: UUID | None = None


class ParallelPurchaseOut(BaseModel):
    id: int
    price: Amount


class ParallelOut(BaseModel):
    id: int
    name: str
    photo_id: UUID | None
    sold: bool
    purchase: ParallelPurchaseOut | None


class ParallelIn(BaseModel):
    name: str | None = None
    photo_id: UUID | None = None


class ParallelPriceIn(BaseModel):
    price: Decimal = Field(ge=0)
    fees: Amount = Field(None, ge=0)
    bought_on: date | None = None
    platform: str = Field("", max_length=80)


class CardOut(BaseModel):
    """Fiche d'une carte (F-13 à F-15)."""

    card_ref_id: int
    code: str
    name: str
    rookie: bool
    series_id: int
    series_name: str
    group: str
    kind: str
    teams: list[str]
    chase_reason: str | None
    collection_id: int | None
    quantity: int
    wanted: bool
    note: str
    photo_id: UUID | None
    purchase_photo_id: UUID | None  # « Photo de votre achat », à défaut de photo personnelle
    parallels: list[ParallelOut]
    official_parallels: list[str]


class IsolatedOut(BaseModel):
    purchase_id: int | None
    card_ref_id: int | None
    name: str
    code: str
    variant: str
    series_id: int | None
    series_name: str
    universe_id: int | None
    photo_id: UUID | None
    can_follow: bool


class SearchResultOut(BaseModel):
    kind: Literal["card", "purchase"]
    card_ref_id: int | None = None
    purchase_id: int | None = None
    collection_id: int | None = None
    series_id: int | None = None
    code: str
    name: str
    detail: str
    series_name: str
    owned: bool = False
    photo_id: UUID | None = None


class SearchOut(BaseModel):
    results: list[SearchResultOut]
    counts: dict[str, int] = {}
    truncated: bool


# ------------------------------------------------------------------- achats


class PurchaseIn(BaseModel):
    series_id: int | None = None
    series_name: str | None = Field(None, max_length=200)
    universe_id: int | None = None
    code: str | None = Field(None, max_length=40)
    name: str | None = Field(None, max_length=200)
    variant: str | None = Field(None, max_length=120)
    as_parallel: bool | None = None
    photo_id: UUID | None = None
    price: Amount = Field(None, ge=0)
    fees: Amount = Field(None, ge=0)
    bought_on: date | None = None
    platform: str | None = Field(None, max_length=80)
    note: str | None = Field(None, max_length=2000)
    sale_price: Amount = Field(None, ge=0)
    sale_fees: Amount = Field(None, ge=0)
    sold_on: date | None = None


class SaleIn(BaseModel):
    price: Decimal = Field(ge=0)
    fees: Amount = Field(None, ge=0)
    sold_on: date | None = None


class PurchaseOut(Out):
    id: int
    series_id: int | None
    series_name: str
    universe_id: int | None
    card_ref_id: int | None
    code: str
    name: str
    variant: str
    photo_id: UUID | None
    price: Amount
    fees: Amount
    bought_on: date | None
    platform: str
    note: str
    applied: bool
    sold: bool
    sale_price: Amount
    sale_fees: Amount
    sold_on: date | None
    result: Amount = None
    # Liens utiles à la fiche (F-23).
    is_isolated: bool = False
    can_follow: bool = False
    parallel_id: int | None = None
    collection_id: int | None = None


class AmountRow(BaseModel):
    key: int | str | None
    count: int
    amount: Cents


class SummaryOut(BaseModel):
    count: int
    invested: Cents
    sold_count: int
    sales_result: Cents
    kept_count: int
    kept_amount: Cents
    by_universe: list[AmountRow]
    by_platform: list[AmountRow]


# -------------------------------------------------------------- photos et IA


class PhotoOut(Out):
    id: UUID
    width: int
    height: int


class CandidateOut(BaseModel):
    series_id: int
    series_name: str
    card_ref_id: int | None
    code: str
    name: str
    group: str


class ReadingOut(BaseModel):
    """RG-19 : proposition de l'IA, à valider par l'utilisateur."""

    series: str
    code: str
    name: str
    variant: str
    candidates: list[CandidateOut]


class ReadCardIn(BaseModel):
    photo_id: UUID


# ------------------------------------------------------------------ partage


class ShareLinkOut(Out):
    id: int
    token: str
    created_at: datetime


class SharingCollectionOut(BaseModel):
    id: int
    name: str
    shared: bool
    share_photos_only: bool
    share_missing: bool
    links: list[ShareLinkOut]


class SharingOut(BaseModel):
    public_profile: bool
    share_singles: bool
    pseudo: str
    collections: list[SharingCollectionOut]


class PublicCardOut(BaseModel):
    card_ref_id: int
    code: str
    name: str
    group: str
    teams: list[str]
    chase: bool
    parallels: list[str]
    photo_ids: list[UUID]


class PublicMissingOut(BaseModel):
    code: str
    name: str


class PublicCollectionOut(BaseModel):
    id: int
    series_id: int
    name: str
    short_name: str
    universe_id: int
    priority_team: str | None
    cards: list[PublicCardOut]
    missing: list[PublicMissingOut]


class PublicSingleOut(BaseModel):
    name: str
    code: str
    variant: str
    series_name: str
    universe_id: int | None
    photo_ids: list[UUID]


class PublicProfileOut(BaseModel):
    pseudo: str
    avatar_photo_id: UUID | None
    collections: list[PublicCollectionOut]
    singles: list[PublicSingleOut]


class CompareOut(BaseModel):
    """Comparaison avec une collection partagée (ajout) : seulement des cartes déjà visibles."""

    they_have_i_miss: list[PublicMissingOut]
    i_have_they_miss: list[PublicMissingOut]
    following: bool


# ----------------------------------------------------------- administration


class DraftCard(BaseModel):
    code: str
    names: list[str] = []
    teams: list[str] = []
    rookie: bool = False
    ref_id: int | None = None


class DraftGroup(BaseModel):
    name: str
    kind: Literal["base", "insert", "special", "relic", "auto"]
    prefix: str = ""
    cards: list[DraftCard] = []


class Draft(BaseModel):
    groups: list[DraftGroup] = []


class ImportIn(BaseModel):
    universe_id: int
    publisher_id: int
    series_name: str = ""
    season: str = ""
    source: str = ""
    text: str = ""
    use_ai: bool = True


class ImportPatch(BaseModel):
    series_name: str | None = None
    season: str | None = None
    source: str | None = None
    universe_id: int | None = None
    publisher_id: int | None = None
    draft: Draft | None = None


class AnomalyOut(BaseModel):
    type: str
    group: int
    code: str
    detail: str
    proposal: str
    blocking: bool


class ImportOut(BaseModel):
    id: int
    status: str
    series_id: int | None
    series_name: str
    season: str
    source: str
    universe_id: int
    publisher_id: int
    error: str
    created_at: datetime
    counters: dict[str, Any]


class ImportDetailOut(ImportOut):
    draft: Draft
    anomalies: list[AnomalyOut]
    name_problems: list[str]


class AdminSeriesOut(SeriesOut):
    status: str
    followers: int


class AdminSeriesIn(BaseModel):
    status: Literal["published", "hidden"] | None = None
    release_date: date | None = None


class NamedIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)


class UniverseIn(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    slug: str = Field(pattern="^[a-z0-9-]{2,40}$")
    color_light: str = Field(pattern="^#[0-9A-Fa-f]{6}$")
    color_dark: str = Field(pattern="^#[0-9A-Fa-f]{6}$")
    position: int = 0


class ChaseIn(BaseModel):
    reason: str = Field("", max_length=300)
    sources: str = Field("", max_length=1000)


class MergeIn(BaseModel):
    source_id: int
    target_id: int


class QueueItemOut(BaseModel):
    kind: Literal["request", "report"]
    id: int
    status: str
    title: str
    detail: str
    author: str | None
    votes: int = 0
    admin_reply: str
    created_at: datetime
    series_id: int | None = None
    card_ref_id: int | None = None
    target_pseudo: str | None = None
    photo_id: UUID | None = None


class QueueReplyIn(BaseModel):
    status: str
    admin_reply: str = ""
    series_id: int | None = None


class AdminUserOut(BaseModel):
    id: UUID
    email: str
    pseudo: str
    role: str
    status: str
    plan: str
    created_at: datetime
    last_seen_at: datetime | None
    ai_quota_day: int | None
    ai_quota_month: int | None
    collections: int
    photos: int


class AdminUserIn(BaseModel):
    reason: str = Field(min_length=3, max_length=500)  # RG-01 : toute action est motivée et tracée
    status: Literal["active", "suspended"] | None = None
    ai_quota_day: int | None = Field(None, ge=0)
    ai_quota_month: int | None = Field(None, ge=0)
    reset_quotas: bool = False
    delete: bool = False


class AuditOut(Out):
    id: int
    action: str
    target: str
    reason: str
    data: dict[str, Any]
    created_at: datetime


class StatsOut(BaseModel):
    users: int
    users_30d: int
    active_30d: int
    photos: int
    photo_bytes: int
    ai_calls_30d: int
    ai_cost_30d: Decimal
    top_series: list[dict[str, Any]]
    queue_open: int
