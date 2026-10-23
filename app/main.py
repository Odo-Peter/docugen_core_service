from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from scalar_fastapi.scalar_fastapi import get_scalar_api_reference

from app.api.v1 import router as v1_router
from app.core.errors import ApiError, api_error_handler

app = FastAPI(
    title="Docugen Service Core",
    description="Templated document generation API — structured JSON + a template in, a PDF out.",
    version="0.1.0",
    openapi_url="/v1/openapi.json",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.include_router(v1_router)


async def _api_error_handler(request: Request, exc: Exception):
    if not isinstance(exc, ApiError):
        raise exc
    return await api_error_handler(request, exc)


app.add_exception_handler(ApiError, _api_error_handler)


@app.get("/v1/")
async def root(request: Request) -> dict[str, str]:
    return {"message": "Hello World"}


@app.get("/v1/scalar", include_in_schema=False)
async def scalar_html() -> HTMLResponse:
    return get_scalar_api_reference(
        openapi_url=app.openapi_url,
        title=app.title,
    )


# TODO(step 4): once the page-cap benchmark is done and settings.page_limit
# is set for real, add a startup check here that refuses to boot in
# app_env="production" with page_limit == 0, so this can't silently ship
# unbounded.
