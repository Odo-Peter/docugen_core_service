"""Secure document rendering using Jinja2 and WeasyPrint.

The renderer is synchronous and independent of FastAPI so it can be
called by both the HTTP service and a background worker.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass

import base64
from urllib.parse import unquote, urlsplit

from jinja2 import StrictUndefined
from jinja2.exceptions import TemplateError
from jinja2.sandbox import SandboxedEnvironment
from weasyprint import CSS, HTML
from weasyprint.urls import URLFetchingError, URLFetcherResponse

from app.config import get_settings

settings = get_settings()
PAGE_LIMIT = settings.page_limit
PDF_CONTENT_TYPE = "application/pdf"


@dataclass
class RenderResult:
    content: bytes
    content_type: str
    page_count: int


class Renderer(ABC):
    """One renderer per output format."""

    @abstractmethod
    def render(self, *, html: str, css: str, data: dict) -> RenderResult:
        """Render a compiled template and data into document bytes."""
        raise NotImplementedError


class TemplateCompileError(Exception):
    """Raised when a template fails to compile or render."""


class PageLimitExceeded(Exception):
    """Raised when a rendered document would exceed the configured page cap."""

    def __init__(self, page_count: int, limit: int):
        self.page_count = page_count
        self.limit = limit
        super().__init__(f"document has {page_count} pages, limit is {limit}")


def restricted_url_fetcher(url: str) -> URLFetcherResponse:
    """Allow embedded data URIs only; reject filesystem and network access."""
    scheme = urlsplit(url).scheme.lower()
    if scheme != "data":
        raise URLFetchingError(f"Resource URL scheme {scheme or '<missing>'!r} is not allowed")

    try:
        header, sep, data = url[5:].partition(",")
        if not sep:
            raise ValueError("missing comma in data URI")

        mime_type = "text/plain"
        is_base64 = False
        if header:
            parts = header.split(";")
            if parts[0]:
                mime_type = parts[0]
            is_base64 = any(p.strip().lower() == "base64" for p in parts[1:])

        raw = data.encode("ascii") if is_base64 else unquote(data).encode("utf-8")
        body = base64.b64decode(raw) if is_base64 else raw
    except Exception as exc:
        raise URLFetchingError(f"Invalid data URI: {exc}") from exc

    return URLFetcherResponse(
        url,
        body=body,
        headers={"Content-Type": mime_type},
    )


class WeasyPrintRenderer(Renderer):
    """Render untrusted HTML/CSS templates into PDF documents."""

    def __init__(self, page_limit: int = PAGE_LIMIT) -> None:
        if page_limit < 1:
            raise ValueError(f"PAGE_LIMIT must be at least 1; got {page_limit}")

        self.page_limit = page_limit

        # HTML templates need autoescaping to prevent data from being
        # interpreted as markup. CSS is rendered separately without
        # HTML escaping, since HTML entities are not CSS escaping.
        self.html_env = SandboxedEnvironment(
            undefined=StrictUndefined,
            autoescape=True,
        )
        self.css_env = SandboxedEnvironment(
            undefined=StrictUndefined,
            autoescape=False,
        )

    @staticmethod
    def _context(data: dict) -> dict:
        # Support both {{ customer_name }} and {{ data.customer_name }}.
        context = dict(data)
        context["data"] = data

        return context

    def render(self, *, html: str, css: str, data: dict) -> RenderResult:
        try:
            context = self._context(data)

            rendered_html = self.html_env.from_string(html).render(context)
            rendered_css = self.css_env.from_string(css).render(context)

            # No base_url: relative resources have no trusted base.
            # Apply the restricted fetcher to HTML and CSS independently.
            stylesheet = CSS(
                string=rendered_css,
                url_fetcher=restricted_url_fetcher,
            )

            document = HTML(
                string=rendered_html,
                url_fetcher=restricted_url_fetcher,
            ).render(stylesheets=[stylesheet])

            # Count laid-out pages before allocating the final PDF bytes.
            page_count = len(document.pages)
            limit = get_settings().page_limit

            if page_count > limit:
                raise PageLimitExceeded(page_count, limit)

            content = document.write_pdf()

            if content is None:
                raise TemplateCompileError("PDF generation returned no document content")

            return RenderResult(
                content=content,
                content_type=PDF_CONTENT_TYPE,
                page_count=page_count,
            )

        except PageLimitExceeded:
            raise
        except (TemplateError, URLFetchingError) as exc:
            raise TemplateCompileError(str(exc)) from exc
        except Exception as exc:
            # Normalize unexpected rendering failures at the renderer
            # boundary, without leaking internal exception types.
            raise TemplateCompileError("The template could not be rendered into a PDF") from exc


_RENDERERS: dict[str, Renderer] = {"pdf": WeasyPrintRenderer()}


def get_renderer(format: str) -> Renderer:
    """Return the renderer registered for the requested output format."""
    try:
        return _RENDERERS[format.lower()]
    except (KeyError, AttributeError):
        raise ValueError(f"Unsupported document format: {format!r}") from None


def generate_document(
    *,
    template_html: str,
    template_css: str,
    data: dict,
    fmt: str = "pdf",
) -> RenderResult:
    """Generate a document without depending on HTTP or worker APIs."""
    renderer = get_renderer(fmt)
    return renderer.render(
        html=template_html,
        css=template_css,
        data=data,
    )
