"""Tenant model (ADR 0001). created_at / updated_at come from Base."""

from sqlalchemy import Index, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.prefix_ids import prefixed_id_column
from app.db import Base


class Tenant(Base):
    __tablename__ = "tenants"

    id: Mapped[str] = prefixed_id_column("tnt_")
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500))


# Case-insensitive unique name, only among active tenants.
Index(
    "uq_tenants_name_lower_active",
    func.lower(Tenant.name),
    unique=True,
    postgresql_where=Tenant.is_active.is_(True),
)
