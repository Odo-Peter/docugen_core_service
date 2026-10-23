"""
SQLAlchemy engine and session. Sync engine (psycopg3) — the generation
endpoint is sync too (see app/api/v1/documents.py), so there's no reason to
pull in async SQLAlchemy for M2/M3. Revisit only if a real need appears.
"""

import logging
from collections.abc import Generator

from sqlalchemy import create_engine, DateTime, func, Boolean, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker, Mapped, mapped_column

from datetime import datetime, timezone
from app.config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)

engine = create_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    """Base class for ORM models — import models via app/models/__init__.py
    so Alembic's autogenerate can see them all."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=func.timezone("UTC", func.now()),
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        server_default=func.timezone("UTC", func.now()),
        server_onupdate=func.timezone("UTC", func.now()),
    )

    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=text("true"))

    deactivated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    def deactivate(self) -> None:
        self.is_active = False
        self.deactivated_at = datetime.now(timezone.utc)

    def reactivate(self) -> None:
        self.is_active = True
        self.deactivated_at = None


def get_db_session() -> Generator[Session, None, None]:
    """FastAPI dependency: yields a request-scoped session."""
    db_session = SessionLocal()
    try:
        logger.info(f"Yielding Session: {id(db_session)}")
        yield db_session
        logger.info(f"Committed Session: {id(db_session)}")

    except Exception:
        db_session.rollback()
        raise
    finally:
        db_session.close()
