from fastapi import APIRouter
from app.core.errors import ApiError, ErrorCode

router = APIRouter(tags=["demo"])

@router.get("/demo-error")
async def demo_error() -> None:
    raise ApiError(
        status=404,
        code=ErrorCode.NOT_FOUND,
        title="Resource not found",
        detail="No template with that id: This is a DEMO check",
    )