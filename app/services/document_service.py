from jsonschema import Draft202012Validator
from fastapi import status
from sqlalchemy.orm import Session

from app.api.v1.schemas.documents import GenerateDocumentRequest, GeneratedDocument
from app.core.errors import ApiError, ErrorCode
from app.core.renderer.renderer import (
    PageLimitExceeded,
    TemplateCompileError,
    generate_document as render_document,
)

from app.core.queries import get_version


class DocumentService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def generate_document(self, *, tenant_id: str, request_data: GenerateDocumentRequest) -> GeneratedDocument:
        # Active version of an active template owned by this tenant.
        # Other tenants' and deactivated templates look the same as missing ones.

        version = get_version(self.session, tenant_id, request_data.template.slug, request_data.template.version)

        if version is None:
            raise ApiError(
                status=status.HTTP_404_NOT_FOUND,
                code=ErrorCode.NOT_FOUND,
                title="Template or version not found",
            )

        # Validate data against the template's JSON Schema
        validator = Draft202012Validator(version.variables_schema)
        errors = [
            {"path": ".".join(["data", *map(str, e.absolute_path)]), "message": e.message} for e in validator.iter_errors(request_data.data)
        ]

        if errors:
            raise ApiError(
                status=status.HTTP_422_UNPROCESSABLE_CONTENT,
                code=ErrorCode.VALIDATION_FAILED,
                title="Request validation failed",
                detail="data does not match the template's variables_schema",
                errors=errors,
            )

        # Render
        try:
            result = render_document(
                template_html=version.html,
                template_css=version.css,
                data=request_data.data,
                fmt=request_data.format,
            )
        except TemplateCompileError as exc:
            raise ApiError(
                status=status.HTTP_422_UNPROCESSABLE_CONTENT,
                code=ErrorCode.TEMPLATE_ERROR,
                title="Template failed to render",
                detail=str(exc),
            ) from exc

        except PageLimitExceeded as exc:
            raise ApiError(
                status=status.HTTP_422_UNPROCESSABLE_CONTENT,
                code=ErrorCode.PAGE_LIMIT_EXCEEDED,
                title="Document exceeds the page limit",
                detail=str(exc),
            ) from exc

        filename = (request_data.options.filename if request_data.options else None) or f"{request_data.template.slug}.pdf"

        return GeneratedDocument(
            content=result.content,
            content_type=result.content_type,
            page_count=result.page_count,
            template_version=version.version,
            filename=filename,
        )
