"""Alembic environment. Uses APP_DATABASE_URL, or a URL passed in by the caller."""

from alembic import context
from sqlalchemy import create_engine

from app.core.config import get_settings
from app.models import Base

target_metadata = Base.metadata


def run() -> None:
    url = context.config.attributes.get("url") or get_settings().database_url
    engine = create_engine(url)
    with engine.connect() as conn:
        context.configure(connection=conn, target_metadata=target_metadata, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


run()
