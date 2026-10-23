from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from scalar_fastapi.scalar_fastapi import get_scalar_api_reference

app = FastAPI(
    title="Docgen Service Core",
    description="Templated document generation API — structured JSON + a template in, a PDF out.",
    version="0.1.0",
    openapi_url="/v1/openapi.json",
    docs_url="/docs",
    redoc_url="/redoc",
)


@app.get("/v1/")
async def root(request: Request) -> dict[str, str]:
    return {"message": "Hello World"}


@app.get("/v1/ready")
async def ready() -> dict[str, str]:
    return {"status": "ready"}


@app.get("/v1/scalar", include_in_schema=False)
async def scalar_html(request: Request) -> HTMLResponse:
    openapi_url = f"{request.url.scheme}://{request.url.hostname}{app.openapi_url}"
    return get_scalar_api_reference(openapi_url=openapi_url, title=app.title)
