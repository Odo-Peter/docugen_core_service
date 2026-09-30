"""
SQLAlchemy engine and session. Sync engine (psycopg3) — the generation
endpoint is sync too (see app/api/v1/documents.py), so there's no reason to
pull in async SQLAlchemy for M2/M3. Revisit only if a real need appears.
"""

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings

settings = get_settings()

engine = create_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    """Base class for ORM models — import models via app/models/__init__.py
    so Alembic's autogenerate can see them all."""


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency: yields a request-scoped session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
