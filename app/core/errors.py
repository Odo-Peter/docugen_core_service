"""API errors rendered as RFC 9457 problem+json (api-contract.md, Errors)."""

from typing import Any
from enum import StrEnum

from fastapi import Request
from fastapi.responses import JSONResponse


class ErrorCode(StrEnum):
    UNAUTHORIZED = "unauthorized"
    FORBIDDEN = "forbidden"
    NOT_FOUND = "not_found"
    VALIDATION_ERROR = "validation_failed"
    TEMPLATE_ERROR = "template_error"
    PAGE_LIMIT_EXCEEDED = "page_limit_exceeded"
    CONFLICT = "conflict"
    INTERNAL = "internal"


class ApiError(Exception):
    def __init__(
        self,
        status: int,
        code: ErrorCode,
        title: str,
        detail: str | None = None,
        errors: list[dict[str, Any]] | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.status = status
        self.code = code
        self.title = title
        self.detail = detail
        self.errors = errors
        self.headers = headers


async def api_error_handler(request: Request, exception: ApiError) -> JSONResponse:
    body: dict[str, Any] = {
        "type": f"https://docs.docugen.com/errors/{exception.code}",
        "title": exception.title,
        "status": exception.status,
        "code": exception.code,
    }

    if exception.detail:
        body["detail"] = exception.detail
    if exception.errors:
        body["errors"] = exception.errors

    return JSONResponse(body, status_code=exception.status, media_type="application/problem+json", headers=exception.headers)
