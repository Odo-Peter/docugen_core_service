"""Tenant model (ADR 0001). created_at / updated_at come from Base."""

from sqlalchemy import Boolean, Index, String, func, text
from sqlalchemy.orm import Mapped, mapped_column
from ulid import ULID

from app.db import Base


class Tenant(Base):
    __tablename__ = "tenants"

    _custom_table_prefix_ = "tnt_"

    id: Mapped[str] = mapped_column(
        String(50),
        primary_key=True,
        default=lambda: f"{Tenant._custom_table_prefix_}{ULID()}",
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500))
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )


# Case-insensitive unique name, only among active tenants.
Index(
    "uq_tenants_name_lower_active",
    func.lower(Tenant.name),
    unique=True,
    postgresql_where=Tenant.is_active.is_(True),
)