from collections.abc import Generator
from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings


def _normalize_database_url(url: str) -> str:
    """Ensure psycopg2 driver and SSL for Supabase-style hosts."""
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+psycopg2://", 1)
    elif url.startswith("postgresql://") and "+psycopg2" not in url:
        url = url.replace("postgresql://", "postgresql+psycopg2://", 1)

    if "sslmode=" not in url and (
        "supabase.co" in url or "pooler.supabase.com" in url
    ):
        separator = "&" if "?" in url else "?"
        url = f"{url}{separator}sslmode=require"
    return url


@lru_cache
def get_engine() -> Engine:
    settings = get_settings()
    return create_engine(
        _normalize_database_url(settings.database_url),
        pool_pre_ping=True,
    )


@lru_cache
def get_session_factory() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), autocommit=False, autoflush=False)


def get_db() -> Generator[Session, None, None]:
    session = get_session_factory()()
    try:
        yield session
    finally:
        session.close()
