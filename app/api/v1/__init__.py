from fastapi import APIRouter

from app.api.v1.endpoints.health import router as health_router
from app.api.v1.endpoints.documents import router as documents_router

# TODO(step 8, M3): from app.api.v1.templates import router as templates_router

router = APIRouter(prefix="/v1")
router.include_router(health_router)
router.include_router(documents_router)

# TODO(step 8, M3): router.include_router(templates_router)
