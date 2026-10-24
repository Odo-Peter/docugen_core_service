"""Reusable query builders. Every read of tenant-owned data goes through here."""

from typing import TypeVar

from sqlalchemy import Select, select, func
from sqlalchemy.orm import Session

from app.db import Base
from app.models.template import Template
from app.models.template_version import TemplateVersion

T = TypeVar("T", bound=Base)


def active(model: type[T]) -> Select[T]:
    """SELECT model WHERE is_active. Extend with .where(...) as usual."""
    return select(model).where(model.is_active.is_(True))


def tenant_active(model: type[T], tenant_id: str) -> Select[T]:
    """Active rows owned by one tenant. Use for every tenant-owned table."""
    stmt: Select[T] = active(model)
    return stmt.where(model.tenant_id == tenant_id)  # type: ignore[attr-defined]


def get_version(db: Session, tenant_id: str, slug: str, version: int | None = None) -> TemplateVersion | None:
    """Active version of an active template owned by tenant_id.

    version=None returns the highest-numbered active version. None -> 404.
    """
    stmt = (
        select(TemplateVersion)
        .join(Template, Template.id == TemplateVersion.template_id)
        .where(
            Template.tenant_id == tenant_id,
            Template.slug == slug,
            Template.is_active.is_(True),
            TemplateVersion.is_active.is_(True),
        )
    )
    if version is None:
        stmt = stmt.order_by(TemplateVersion.version.desc()).limit(1)
    else:
        stmt = stmt.where(TemplateVersion.version == version)
    return db.scalars(stmt).first()


def next_version_number(db: Session, template_id: str) -> int:
    """Next number for a publish. Counts deactivated versions too (see model)."""
    current = db.scalar(select(func.max(TemplateVersion.version)).where(TemplateVersion.template_id == template_id))
    return (current or 0) + 1
