"""Migrations versionnées (T-03). L'adresse de la base vient de la configuration de l'application."""

from alembic import context
from sqlalchemy import create_engine

from app.config import get_settings
from app.models import Base

target_metadata = Base.metadata


def run() -> None:
    url = context.get_x_argument(as_dictionary=True).get("url") or get_settings().database_url
    engine = create_engine(url)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()


run()
