"""Template model (ADR 0001, api-contract.md).

A template is the stable identity (slug + name).
Its content lives in immutable TemplateVersion rows. Soft-deleted via Base.is_active / Base.deactivated_at;
read it through tenant_active() in app/core/queries.py.
"""

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.prefix_ids import prefixed_id_column


class Template(Base):
    __tablename__ = "templates"
    __table_args__ = (
        Index(
            "uq_templates_tenant_slug_active",
            "tenant_id",
            "slug",
            unique=True,
            postgresql_where=text("is_active"),
        ),
        CheckConstraint("slug ~ '^[a-z0-9-]{3,64}$'", name="ck_templates_slug_format"),
    )

    id: Mapped[str] = prefixed_id_column("tpl_")
    tenant_id: Mapped[str] = mapped_column(String(50), ForeignKey("tenants.id"), nullable=False)
    slug: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
