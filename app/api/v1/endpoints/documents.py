"""
POST /v1/documents — see api-contract.md for the full request/response
shape and error table. TODO(step 6): implement against a CLI-seeded
template (step 5) once the renderer core (step 3) and auth (step 5) exist.

Deliberately a plain `def`, not `async def` — see ADR 0001's trade-off note:
WeasyPrint rendering is CPU-bound and blocking, so this runs in FastAPI's
threadpool rather than stalling the event loop.
"""

from fastapi import APIRouter, Depends, Response

from app.api.v1.endpoints.deps import AuthContext, require_scope
from app.api.v1.schemas.templates import GenerateDocumentRequest

router = APIRouter(tags=["documents"])


@router.post("/documents")
def generate_document(
    body: GenerateDocumentRequest,
    auth: AuthContext = Depends(require_scope("documents:create")),
) -> Response:
    # TODO(step 6):
    #   1. Look up the template (+ version, default latest) for auth.tenant_id
    #      -> 404 (code="not_found") if missing, including other tenants' templates
    #   2. Validate body.data against the template's variables_schema
    #      -> 422 (code="validation_failed") with per-field errors
    #   3. Call app.core.renderer.generate_document(...)
    #      -> map TemplateCompileError to 422 "template_error"
    #      -> map PageLimitExceeded to 422 "page_limit_exceeded"
    #   4. Return the PDF bytes with the headers specified in api-contract.md:
    #      Content-Type, Content-Disposition, X-Template-Version, X-Page-Count
    raise NotImplementedError("implement in step 6 — see module docstring")


@router.get("/documents/{document_id}")
def get_document(document_id: str) -> dict:
    return {"response": f"Recieved {document_id}"}

