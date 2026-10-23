"""
POST /v1/documents (api-contract.md). Renders one document, returns the bytes.

A plain `def`, not `async def` (ADR 0001): rendering is CPU-bound and blocking,
so it runs in FastAPI's threadpool instead of stalling the event loop.

Needs the renderer core (step 3) and an existing template version. Until step 3 lands,
the render call raises NotImplementedError and the endpoint returns 500.
"""

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.api.v1.endpoints.deps import AuthContext, require_scope
from app.api.v1.schemas.documents import GenerateDocumentRequest
from app.core.scopes import ApiKeyScope

from app.db import get_db_session

router = APIRouter(tags=["documents"])


@router.post("/documents")
def generate_document(
    body: GenerateDocumentRequest,
    auth: AuthContext = Depends(require_scope(ApiKeyScope.DOCUMENTS_CREATE)),
    session: Session = Depends(get_db_session),
) -> Response:
    raise NotImplementedError("implement in step 6 — see module docstring")


@router.get("/documents/{document_id}")
def get_document(document_id: str) -> dict:
    return {"response": f"Recieved {document_id}"}
