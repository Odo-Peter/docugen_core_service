from pydantic import BaseModel

class TemplateRef(BaseModel):
    slug: str
    version: int | None = None


class GenerateDocumentRequest(BaseModel):
    template: TemplateRef
    data: dict
    format: str = "pdf"
    options: dict | None = None

