"""Configuration lue dans l'environnement. Aucune valeur secrète n'a de défaut utilisable en production."""

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="CC_", extra="ignore")

    env: Literal["dev", "test", "staging", "prod"] = "dev"
    app_version: str = "0.1.0"
    # Questions ouvertes (section 17) : nom du produit et éditeur restent de la configuration.
    product_name: str = "Mes collections de cartes"
    app_url: str = "http://localhost:5173"

    database_url: str = "postgresql+psycopg://postgres@127.0.0.1:5433/cc_dev"

    session_cookie: str = "cc_session"
    session_days: int = 60
    cookie_secure: bool = False  # True en recette et en production (HTTPS)
    admin_require_totp: bool = True  # S-01
    terms_version: str = "2026-11"

    storage_backend: Literal["local", "s3"] = "local"
    storage_local_dir: str = "./var/storage"
    s3_bucket: str = ""
    s3_endpoint: str = ""
    s3_region: str = "fr-par"
    s3_access_key: str = ""
    s3_secret_key: str = ""
    photo_max_bytes: int = 10 * 1024 * 1024  # 8.2 : envoi jusqu'à 10 Mo

    mail_backend: Literal["console", "smtp"] = "console"
    mail_from: str = "Mes collections de cartes <bonjour@example.org>"
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""

    ai_backend: Literal["off", "fake", "anthropic"] = "fake"
    anthropic_api_key: str = ""
    ai_model_photo: str = "claude-haiku-5-5"
    ai_model_import: str = "claude-sonnet-5-5"
    # RG-20 : quotas par défaut de l'offre gratuite, réglables par utilisateur.
    ai_quota_day: int = 10
    ai_quota_month: int = 100

    google_client_id: str = ""
    google_client_secret: str = ""
    apple_client_id: str = ""
    apple_team_id: str = ""
    apple_key_id: str = ""
    apple_private_key: str = ""

    account_deletion_days: int = 30  # délai annoncé à l'utilisateur (F-31)
    export_retention_days: int = 7


@lru_cache
def get_settings() -> Settings:
    return Settings()
