from typing import Any, Literal
from pydantic import BaseModel, Field
from dataclasses import dataclass


class TemplateRef(BaseModel):
    slug: str = Field(
        ...,
        min_length=3,
        max_length=64,
        pattern=r"^[a-z0-9-]{3,64}$",
    )
    version: int | None = Field(default=None, ge=1)


class DocumentOptions(BaseModel):
    filename: str | None = Field(default=None, pattern=r"^[A-Za-z0-9._-]{1,100}$")


class GenerateDocumentRequest(BaseModel):
    template: TemplateRef
    data: dict[str, Any]
    format: Literal["pdf"] = "pdf"
    options: DocumentOptions | None = None


@dataclass(frozen=True)
class GeneratedDocument:
    content: bytes
    content_type: str
    page_count: int
    template_version: int
    filename: str
