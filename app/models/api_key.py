"""
ApiKey model. TODO(step 2 + step 5): fields per ADR 0001 — id, tenant_id,
name, key_prefix, key_hash, scopes, last_used_at, revoked_at.

Keys are stored as a SHA-256 hash with a short lookup prefix and shown once
on creation (see the create-tenant CLI, step 5). Never store the raw key.
"""

from sqlalchemy import DateTime, String, ForeignKey, ARRAY
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime

from app.models.prefix_ids import prefixed_id_column
from app.db import Base

class ApiKey(Base):
    __tablename__ = "api_keys"

    id: Mapped[str] = prefixed_id_column("key_")
    tenant_id: Mapped[str] = mapped_column(
        String(50), ForeignKey("tenants.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    key_prefix: Mapped[str] = mapped_column(String(16), unique=True, index=True, nullable=False)
    key_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    scopes: Mapped[list[str]] = mapped_column(ARRAY(String(50)), nullable=False)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)