"""schema initial

Revision ID: 0001
Revises:
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001"
down_revision = None


UNIVERSES = [
    # slug, nom, couleur (thème clair, section 11), couleur éclaircie pour le thème sombre
    ("football", "Football", "#2E9E5B", "#4FC07C"),
    ("football-americain", "Football américain", "#8A5A2B", "#C08A55"),
    ("baseball", "Baseball", "#2F6FDB", "#6B9BF0"),
    ("basket", "Basket", "#E8742B", "#F29455"),
    ("hockey", "Hockey", "#1597A8", "#3FC0D1"),
    ("formule-1", "Formule 1", "#D7263D", "#F0596C"),
    ("manga", "Manga", "#D9467A", "#EE78A2"),
    ("star-wars", "Star Wars", "#C9A227", "#E0BE52"),
    ("marvel", "Marvel", "#7A4BD1", "#A382E8"),
]
PUBLISHERS = ["Topps", "Panini", "Upper Deck", "Bandai"]


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS citext")
    op.execute("CREATE EXTENSION IF NOT EXISTS unaccent")
    op.create_table(
        "app_user",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("email", postgresql.CITEXT(), nullable=False),
        sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("password_hash", sa.Text(), nullable=True),
        sa.Column("pseudo", postgresql.CITEXT(), nullable=False),
        sa.Column("avatar_photo_id", sa.UUID(), nullable=True),
        sa.Column("locale", sa.Text(), server_default="fr", nullable=False),
        sa.Column("currency", sa.Text(), server_default="EUR", nullable=False),
        sa.Column("theme", sa.Text(), server_default="auto", nullable=False),
        sa.Column("role", sa.Text(), server_default="collector", nullable=False),
        sa.Column("status", sa.Text(), server_default="active", nullable=False),
        sa.Column("suspended_reason", sa.Text(), nullable=True),
        sa.Column("plan", sa.Text(), server_default="free", nullable=False),
        sa.Column("terms_version", sa.Text(), nullable=True),
        sa.Column("terms_accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("age_confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notify_series_published", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("public_profile", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("share_singles", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("ai_quota_day", sa.Integer(), nullable=True),
        sa.Column("ai_quota_month", sa.Integer(), nullable=True),
        sa.Column("totp_secret", sa.Text(), nullable=True),
        sa.Column("totp_enabled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("role IN ('collector', 'admin')", name="user_role"),
        sa.CheckConstraint("status IN ('active', 'suspended', 'deleting')", name="user_status"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
        sa.UniqueConstraint("pseudo"),
    )
    op.create_table(
        "publisher",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", postgresql.CITEXT(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_table(
        "rate_limit",
        sa.Column("key", sa.Text(), nullable=False),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("count", sa.Integer(), server_default="0", nullable=False),
        sa.PrimaryKeyConstraint("key", "window_start"),
    )
    op.create_table(
        "universe",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("slug", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("color_light", sa.Text(), nullable=False),
        sa.Column("color_dark", sa.Text(), nullable=False),
        sa.Column("position", sa.Integer(), server_default="0", nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug"),
    )
    op.create_table(
        "ai_call",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=True),
        sa.Column("function", sa.Text(), nullable=False),
        sa.Column("model", sa.Text(), nullable=False),
        sa.Column("duration_ms", sa.Integer(), server_default="0", nullable=False),
        sa.Column("input_tokens", sa.Integer(), server_default="0", nullable=False),
        sa.Column("output_tokens", sa.Integer(), server_default="0", nullable=False),
        sa.Column("cost_usd", sa.Numeric(precision=10, scale=6), server_default="0", nullable=False),
        sa.Column("outcome", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["app_user.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ai_call_user_time", "ai_call", ["user_id", "created_at"], unique=False)
    op.create_table(
        "audit_log",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("admin_id", sa.UUID(), nullable=True),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("target", sa.Text(), server_default="", nullable=False),
        sa.Column("reason", sa.Text(), server_default="", nullable=False),
        sa.Column("data", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["admin_id"], ["app_user.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "auth_token",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("token_hash", sa.Text(), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["app_user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index(op.f("ix_auth_token_user_id"), "auth_token", ["user_id"], unique=False)
    op.create_table(
        "job",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=True),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False),
        sa.Column("status", sa.Text(), server_default="queued", nullable=False),
        sa.Column("progress", sa.Integer(), server_default="0", nullable=False),
        sa.Column("result", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False),
        sa.Column("error", sa.Text(), server_default="", nullable=False),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("run_after", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("status IN ('queued', 'running', 'done', 'failed')", name="job_status"),
        sa.ForeignKeyConstraint(["user_id"], ["app_user.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_job_queue", "job", ["status", "run_after"], unique=False)
    op.create_index(op.f("ix_job_user_id"), "job", ["user_id"], unique=False)
    op.create_table(
        "oauth_identity",
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("subject", sa.Text(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["app_user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("provider", "subject"),
    )
    op.create_index(op.f("ix_oauth_identity_user_id"), "oauth_identity", ["user_id"], unique=False)
    op.create_table(
        "photo",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("key_prefix", sa.Text(), nullable=False),
        sa.Column("width", sa.Integer(), nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
        sa.Column("bytes", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["app_user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "sha256"),
    )
    op.create_index(op.f("ix_photo_user_id"), "photo", ["user_id"], unique=False)
    op.create_table(
        "series",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", postgresql.CITEXT(), nullable=False),
        sa.Column("publisher_id", sa.Integer(), nullable=False),
        sa.Column("universe_id", sa.Integer(), nullable=False),
        sa.Column("season", sa.Text(), server_default="", nullable=False),
        sa.Column("release_date", sa.Date(), nullable=True),
        sa.Column("source", sa.Text(), server_default="", nullable=False),
        sa.Column("source_date", sa.Date(), nullable=True),
        sa.Column("status", sa.Text(), server_default="draft", nullable=False),
        sa.Column("version", sa.Integer(), server_default="0", nullable=False),
        sa.Column("card_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("status IN ('draft', 'published', 'hidden')", name="series_status"),
        sa.ForeignKeyConstraint(
            ["publisher_id"],
            ["publisher.id"],
        ),
        sa.ForeignKeyConstraint(
            ["universe_id"],
            ["universe.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_index(op.f("ix_series_universe_id"), "series", ["universe_id"], unique=False)
    op.create_table(
        "session",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("token_hash", sa.Text(), nullable=False),
        sa.Column("user_agent", sa.Text(), server_default="", nullable=False),
        sa.Column("ip", sa.Text(), server_default="", nullable=False),
        sa.Column("mfa_verified", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column(
            "last_seen_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["app_user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index(op.f("ix_session_user_id"), "session", ["user_id"], unique=False)
    op.create_table(
        "team",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("universe_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("franchise", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["universe_id"],
            ["universe.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("universe_id", "name"),
    )
    op.create_table(
        "checklist_import",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("admin_id", sa.UUID(), nullable=True),
        sa.Column("series_id", sa.Integer(), nullable=True),
        sa.Column("universe_id", sa.Integer(), nullable=False),
        sa.Column("publisher_id", sa.Integer(), nullable=False),
        sa.Column("series_name", sa.Text(), server_default="", nullable=False),
        sa.Column("season", sa.Text(), server_default="", nullable=False),
        sa.Column("source", sa.Text(), server_default="", nullable=False),
        sa.Column("source_text", sa.Text(), server_default="", nullable=False),
        sa.Column("use_ai", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("status", sa.Text(), server_default="uploaded", nullable=False),
        sa.Column("draft", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False),
        sa.Column("error", sa.Text(), server_default="", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "status IN ('uploaded', 'analyzing', 'review', 'published', 'failed')", name="import_status"
        ),
        sa.ForeignKeyConstraint(["admin_id"], ["app_user.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["publisher_id"],
            ["publisher.id"],
        ),
        sa.ForeignKeyConstraint(["series_id"], ["series.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["universe_id"],
            ["universe.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "series_group",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("series_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("prefix", sa.Text(), server_default="", nullable=False),
        sa.Column("position", sa.Integer(), server_default="0", nullable=False),
        sa.Column("card_count", sa.Integer(), server_default="0", nullable=False),
        sa.CheckConstraint("kind IN ('base', 'insert', 'special', 'relic', 'auto')", name="group_kind"),
        sa.ForeignKeyConstraint(["series_id"], ["series.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("series_id", "name"),
    )
    op.create_index(op.f("ix_series_group_series_id"), "series_group", ["series_id"], unique=False)
    op.create_table(
        "series_request",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("url", sa.Text(), server_default="", nullable=False),
        sa.Column("note", sa.Text(), server_default="", nullable=False),
        sa.Column("status", sa.Text(), server_default="open", nullable=False),
        sa.Column("series_id", sa.Integer(), nullable=True),
        sa.Column("admin_reply", sa.Text(), server_default="", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("status IN ('open', 'accepted', 'declined', 'published')", name="request_status"),
        sa.ForeignKeyConstraint(["series_id"], ["series.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["app_user.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "series_version",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("series_id", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("admin_id", sa.UUID(), nullable=True),
        sa.Column("summary", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False),
        sa.Column(
            "published_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.ForeignKeyConstraint(["admin_id"], ["app_user.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["series_id"], ["series.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_series_version_series_id"), "series_version", ["series_id"], unique=False)
    op.create_table(
        "user_series",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("series_id", sa.Integer(), nullable=True),
        sa.Column("personal_name", sa.Text(), nullable=True),
        sa.Column("universe_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.Text(), server_default="followed", nullable=False),
        sa.Column("priority_team_id", sa.Integer(), nullable=True),
        sa.Column("shared", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("share_photos_only", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("share_missing", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("status IN ('followed', 'reserve')", name="user_series_status"),
        sa.CheckConstraint("series_id IS NOT NULL OR personal_name IS NOT NULL", name="user_series_target"),
        sa.ForeignKeyConstraint(
            ["priority_team_id"],
            ["team.id"],
        ),
        sa.ForeignKeyConstraint(
            ["series_id"],
            ["series.id"],
        ),
        sa.ForeignKeyConstraint(
            ["universe_id"],
            ["universe.id"],
        ),
        sa.ForeignKeyConstraint(["user_id"], ["app_user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "series_id"),
    )
    op.create_index(op.f("ix_user_series_series_id"), "user_series", ["series_id"], unique=False)
    op.create_index(op.f("ix_user_series_user_id"), "user_series", ["user_id"], unique=False)
    op.create_table(
        "card_ref",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("series_id", sa.Integer(), nullable=False),
        sa.Column("group_id", sa.Integer(), nullable=False),
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("code_key", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), server_default="", nullable=False),
        sa.Column("rookie", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("position", sa.Integer(), server_default="0", nullable=False),
        sa.Column("status", sa.Text(), server_default="active", nullable=False),
        sa.Column("merged_into_id", sa.Integer(), nullable=True),
        sa.Column("search_tokens", postgresql.ARRAY(sa.Text()), server_default="{}", nullable=False),
        sa.Column(
            "search_tsv",
            postgresql.TSVECTOR(),
            sa.Computed("array_to_tsvector(search_tokens)", persisted=True),
            nullable=False,
        ),
        sa.CheckConstraint("status IN ('active', 'hidden')", name="card_ref_status"),
        sa.ForeignKeyConstraint(
            ["group_id"],
            ["series_group.id"],
        ),
        sa.ForeignKeyConstraint(
            ["merged_into_id"],
            ["card_ref.id"],
        ),
        sa.ForeignKeyConstraint(["series_id"], ["series.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("series_id", "code_key"),
    )
    op.create_index(op.f("ix_card_ref_group_id"), "card_ref", ["group_id"], unique=False)
    op.create_index("ix_card_ref_search", "card_ref", ["search_tsv"], unique=False, postgresql_using="gin")
    op.create_index("ix_card_ref_series_position", "card_ref", ["series_id", "position"], unique=False)
    op.create_table(
        "official_parallel",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("series_id", sa.Integer(), nullable=False),
        sa.Column("group_id", sa.Integer(), nullable=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("print_run", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["group_id"], ["series_group.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["series_id"], ["series.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_official_parallel_series_id"), "official_parallel", ["series_id"], unique=False)
    op.create_table(
        "personal_card",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("user_series_id", sa.BigInteger(), nullable=False),
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("code_key", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), server_default="", nullable=False),
        sa.Column("quantity", sa.SmallInteger(), server_default="1", nullable=False),
        sa.Column("photo_id", sa.UUID(), nullable=True),
        sa.Column("note", sa.Text(), server_default="", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("quantity BETWEEN 0 AND 999", name="personal_card_quantity"),
        sa.ForeignKeyConstraint(["photo_id"], ["photo.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["app_user.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_series_id"], ["user_series.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_series_id", "code_key"),
    )
    op.create_index(op.f("ix_personal_card_user_id"), "personal_card", ["user_id"], unique=False)
    op.create_index(
        op.f("ix_personal_card_user_series_id"), "personal_card", ["user_series_id"], unique=False
    )
    op.create_table(
        "series_request_vote",
        sa.Column("request_id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(["request_id"], ["series_request.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["app_user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("request_id", "user_id"),
    )
    op.create_table(
        "share_link",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("user_series_id", sa.BigInteger(), nullable=False),
        sa.Column("token", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["app_user.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_series_id"], ["user_series.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token"),
    )
    op.create_index(op.f("ix_share_link_user_id"), "share_link", ["user_id"], unique=False)
    op.create_table(
        "card_ref_team",
        sa.Column("card_ref_id", sa.Integer(), nullable=False),
        sa.Column("team_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["card_ref_id"], ["card_ref.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["team_id"],
            ["team.id"],
        ),
        sa.PrimaryKeyConstraint("card_ref_id", "team_id"),
    )
    op.create_index(op.f("ix_card_ref_team_team_id"), "card_ref_team", ["team_id"], unique=False)
    op.create_table(
        "chase_mark",
        sa.Column("card_ref_id", sa.Integer(), nullable=False),
        sa.Column("reason", sa.Text(), server_default="", nullable=False),
        sa.Column("sources", sa.Text(), server_default="", nullable=False),
        sa.Column("marked_on", sa.Date(), server_default=sa.text("CURRENT_DATE"), nullable=False),
        sa.Column("author_id", sa.UUID(), nullable=True),
        sa.ForeignKeyConstraint(["author_id"], ["app_user.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["card_ref_id"], ["card_ref.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("card_ref_id"),
    )
    op.create_table(
        "purchase",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("series_id", sa.Integer(), nullable=True),
        sa.Column("series_name", sa.Text(), nullable=False),
        sa.Column("universe_id", sa.Integer(), nullable=True),
        sa.Column("card_ref_id", sa.Integer(), nullable=True),
        sa.Column("code", sa.Text(), server_default="", nullable=False),
        sa.Column("name", sa.Text(), server_default="", nullable=False),
        sa.Column("variant", sa.Text(), server_default="", nullable=False),
        sa.Column("as_parallel", sa.Boolean(), nullable=True),
        sa.Column("applied", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("photo_id", sa.UUID(), nullable=True),
        sa.Column("price", sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column("fees", sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column("bought_on", sa.Date(), nullable=True),
        sa.Column("platform", sa.Text(), server_default="", nullable=False),
        sa.Column("note", sa.Text(), server_default="", nullable=False),
        sa.Column("sold", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("sale_price", sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column("sale_fees", sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column("sold_on", sa.Date(), nullable=True),
        sa.Column("sale_removed_copy", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["card_ref_id"],
            ["card_ref.id"],
        ),
        sa.ForeignKeyConstraint(["photo_id"], ["photo.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["series_id"],
            ["series.id"],
        ),
        sa.ForeignKeyConstraint(
            ["universe_id"],
            ["universe.id"],
        ),
        sa.ForeignKeyConstraint(["user_id"], ["app_user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_purchase_card_ref_id"), "purchase", ["card_ref_id"], unique=False)
    op.create_index(op.f("ix_purchase_series_id"), "purchase", ["series_id"], unique=False)
    op.create_index(op.f("ix_purchase_user_id"), "purchase", ["user_id"], unique=False)
    op.create_table(
        "report",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("reporter_id", sa.UUID(), nullable=True),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("series_id", sa.Integer(), nullable=True),
        sa.Column("card_ref_id", sa.Integer(), nullable=True),
        sa.Column("target_user_id", sa.UUID(), nullable=True),
        sa.Column("photo_id", sa.UUID(), nullable=True),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), server_default="open", nullable=False),
        sa.Column("admin_reply", sa.Text(), server_default="", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("kind IN ('catalog', 'content')", name="report_kind"),
        sa.CheckConstraint("status IN ('open', 'resolved', 'dismissed')", name="report_status"),
        sa.ForeignKeyConstraint(["card_ref_id"], ["card_ref.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["photo_id"], ["photo.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["reporter_id"], ["app_user.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["series_id"], ["series.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["target_user_id"], ["app_user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "user_card",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("card_ref_id", sa.Integer(), nullable=False),
        sa.Column("quantity", sa.SmallInteger(), server_default="0", nullable=False),
        sa.Column("parallel_count", sa.SmallInteger(), server_default="0", nullable=False),
        sa.Column(
            "owned",
            sa.Boolean(),
            sa.Computed("quantity > 0 OR parallel_count > 0", persisted=True),
            nullable=False,
        ),
        sa.Column("photo_id", sa.UUID(), nullable=True),
        sa.Column("wanted", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("note", sa.Text(), server_default="", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("quantity BETWEEN 0 AND 999", name="user_card_quantity"),
        sa.ForeignKeyConstraint(
            ["card_ref_id"],
            ["card_ref.id"],
        ),
        sa.ForeignKeyConstraint(["photo_id"], ["photo.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["app_user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "card_ref_id"),
    )
    op.create_index(op.f("ix_user_card_card_ref_id"), "user_card", ["card_ref_id"], unique=False)
    op.create_table(
        "user_parallel",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("user_card_id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("photo_id", sa.UUID(), nullable=True),
        sa.Column("purchase_id", sa.BigInteger(), nullable=True),
        sa.Column("sold", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["photo_id"], ["photo.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["purchase_id"], ["purchase.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_card_id"], ["user_card.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["app_user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("purchase_id"),
    )
    op.create_index(op.f("ix_user_parallel_user_card_id"), "user_parallel", ["user_card_id"], unique=False)
    op.create_index(op.f("ix_user_parallel_user_id"), "user_parallel", ["user_id"], unique=False)
    # Cycle app_user ↔ photo : la clé étrangère est posée une fois les deux tables créées.
    op.create_foreign_key(
        "fk_app_user_avatar_photo", "app_user", "photo", ["avatar_photo_id"], ["id"], ondelete="SET NULL"
    )

    # Données de référence : les univers et leurs couleurs, les éditeurs courants.
    universe = sa.table(
        "universe",
        sa.column("slug"),
        sa.column("name"),
        sa.column("color_light"),
        sa.column("color_dark"),
        sa.column("position"),
    )
    op.bulk_insert(
        universe,
        [
            {"slug": slug, "name": name, "color_light": light, "color_dark": dark, "position": position}
            for position, (slug, name, light, dark) in enumerate(UNIVERSES)
        ],
    )
    op.bulk_insert(sa.table("publisher", sa.column("name")), [{"name": name} for name in PUBLISHERS])


def downgrade() -> None:
    op.drop_constraint("fk_app_user_avatar_photo", "app_user", type_="foreignkey")
    op.drop_index(op.f("ix_user_parallel_user_id"), table_name="user_parallel")
    op.drop_index(op.f("ix_user_parallel_user_card_id"), table_name="user_parallel")
    op.drop_table("user_parallel")
    op.drop_index(op.f("ix_user_card_card_ref_id"), table_name="user_card")
    op.drop_table("user_card")
    op.drop_table("report")
    op.drop_index(op.f("ix_purchase_user_id"), table_name="purchase")
    op.drop_index(op.f("ix_purchase_series_id"), table_name="purchase")
    op.drop_index(op.f("ix_purchase_card_ref_id"), table_name="purchase")
    op.drop_table("purchase")
    op.drop_table("chase_mark")
    op.drop_index(op.f("ix_card_ref_team_team_id"), table_name="card_ref_team")
    op.drop_table("card_ref_team")
    op.drop_index(op.f("ix_share_link_user_id"), table_name="share_link")
    op.drop_table("share_link")
    op.drop_table("series_request_vote")
    op.drop_index(op.f("ix_personal_card_user_series_id"), table_name="personal_card")
    op.drop_index(op.f("ix_personal_card_user_id"), table_name="personal_card")
    op.drop_table("personal_card")
    op.drop_index(op.f("ix_official_parallel_series_id"), table_name="official_parallel")
    op.drop_table("official_parallel")
    op.drop_index("ix_card_ref_series_position", table_name="card_ref")
    op.drop_index("ix_card_ref_search", table_name="card_ref", postgresql_using="gin")
    op.drop_index(op.f("ix_card_ref_group_id"), table_name="card_ref")
    op.drop_table("card_ref")
    op.drop_index(op.f("ix_user_series_user_id"), table_name="user_series")
    op.drop_index(op.f("ix_user_series_series_id"), table_name="user_series")
    op.drop_table("user_series")
    op.drop_index(op.f("ix_series_version_series_id"), table_name="series_version")
    op.drop_table("series_version")
    op.drop_table("series_request")
    op.drop_index(op.f("ix_series_group_series_id"), table_name="series_group")
    op.drop_table("series_group")
    op.drop_table("checklist_import")
    op.drop_table("team")
    op.drop_index(op.f("ix_session_user_id"), table_name="session")
    op.drop_table("session")
    op.drop_index(op.f("ix_series_universe_id"), table_name="series")
    op.drop_table("series")
    op.drop_index(op.f("ix_photo_user_id"), table_name="photo")
    op.drop_table("photo")
    op.drop_index(op.f("ix_oauth_identity_user_id"), table_name="oauth_identity")
    op.drop_table("oauth_identity")
    op.drop_index(op.f("ix_job_user_id"), table_name="job")
    op.drop_index("ix_job_queue", table_name="job")
    op.drop_table("job")
    op.drop_index(op.f("ix_auth_token_user_id"), table_name="auth_token")
    op.drop_table("auth_token")
    op.drop_table("audit_log")
    op.drop_index("ix_ai_call_user_time", table_name="ai_call")
    op.drop_table("ai_call")
    op.drop_table("universe")
    op.drop_table("rate_limit")
    op.drop_table("publisher")
    op.drop_table("app_user")
