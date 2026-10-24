"""
POST /v1/documents (api-contract.md). Renders one document, returns the bytes.

A plain `def`, not `async def` (ADR 0001): rendering is CPU-bound and blocking,
so it runs in FastAPI's threadpool instead of stalling the event loop..
"""

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.api.v1.endpoints.deps import AuthContext, require_scope
from app.api.v1.schemas.documents import GenerateDocumentRequest
from app.core.scopes import ApiKeyScope
from app.services.document_service import DocumentService

from app.db import get_db_session

router = APIRouter(tags=["documents"])


@router.post("/documents")
def generate_document(
    body: GenerateDocumentRequest,
    auth: AuthContext = Depends(require_scope(ApiKeyScope.DOCUMENTS_CREATE)),
    db_session: Session = Depends(get_db_session),
) -> Response:
    document_service = DocumentService(session=db_session)

    result = document_service.generate_document(tenant_id=auth.tenant_id, request_data=body)

    return Response(
        content=result.content,
        media_type=result.content_type,
        headers={
            "Content-Disposition": f'inline; filename="{result.filename}"',
            "X-Template-Version": str(result.template_version),
            "X-Page-Count": str(result.page_count),
        },
    )
