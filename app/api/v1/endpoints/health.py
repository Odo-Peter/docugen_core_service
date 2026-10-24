"""GET /v1/health — liveness only, no auth. Matches api-contract.md."""

from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict:
    return {"status": "ok"}
