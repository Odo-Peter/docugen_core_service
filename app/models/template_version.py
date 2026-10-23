"""TemplateVersion model (ADR 0001, api-contract.md).

Content is immutable: a publish writes a new row, and template_id, version,
html, css and variables_schema never change afterwards (enforced by the guard
below). The only permitted mutation is Base.deactivate(), which retires a bad
version so renders fall back to the previous active one.

There is no tenant_id here. Ownership comes from the parent Template, so every
read must join through it (see get_version in app/core/queries.py).
"""

from typing import Any

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    event,
    inspect,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, Mapper
from sqlalchemy.engine import Connection

from app.db import Base
from app.models.prefix_ids import prefixed_id_column

_IMMUTABLE_COLUMNS = ("template_id", "version", "html", "css", "variables_schema")


class TemplateVersion(Base):
    __tablename__ = "template_versions"
    __table_args__ = (
        UniqueConstraint("template_id", "version", name="uq_template_versions_template_version"),
        CheckConstraint("version >= 1", name="ck_template_versions_version_positive"),
    )

    id: Mapped[str] = prefixed_id_column("ver_")
    template_id: Mapped[str] = mapped_column(
        String(50), ForeignKey("templates.id"), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    html: Mapped[str] = mapped_column(Text, nullable=False)
    css: Mapped[str] = mapped_column(Text, nullable=False, default="")
    variables_schema: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)


@event.listens_for(TemplateVersion, "before_update")
def _forbid_content_edits(
    mapper: Mapper[TemplateVersion],
    connection: Connection,
    target: TemplateVersion,
) -> None:
    state = inspect(target)
    for column in _IMMUTABLE_COLUMNS:
        if state.attrs[column].history.has_changes():
            raise ValueError(f"template versions are immutable: {column} cannot change")