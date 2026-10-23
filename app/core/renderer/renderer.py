"""Secure document rendering using Jinja2 and WeasyPrint.

The renderer is synchronous and independent of FastAPI so it can be
called by both the HTTP service and a background worker.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass

from base64 import b64decode
from urllib.parse import unquote_to_bytes, urlsplit

from jinja2 import StrictUndefined
from jinja2.exceptions import TemplateError
from jinja2.sandbox import SandboxedEnvironment
from weasyprint import CSS, HTML
from weasyprint.urls import URLFetchingError

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

def restricted_url_fetcher(url: str, *args, **kwargs) -> dict:
    """Fetch embedded data URIs only; reject all other resource URLs."""
    parsed = urlsplit(url)

    if parsed.scheme.lower() != "data":
        raise URLFetchingError("Only data: resource URLs are allowed")

    try:
        metadata, separator, payload = url.partition(",")
        if not separator:
            raise ValueError("Malformed data URI")

        media_type = metadata[5:].split(";")
        mime_type = media_type[0] or "text/plain"
        is_base64 = any(
            part.lower() == "base64" for part in media_type[1:]
        )

        content = (
            b64decode(payload, validate=True)
            if is_base64
            else unquote_to_bytes(payload)
        )

        return {
            "string": content,
            "mime_type": mime_type,
            "redirected_url": url,
        }
    except (ValueError, UnicodeError) as exc:
        raise URLFetchingError("Invalid data URI") from exc


class WeasyPrintRenderer(Renderer):
    """Render untrusted HTML/CSS templates into PDF documents."""

    def __init__(self, page_limit: int = PAGE_LIMIT ) -> None:
        if page_limit < 1:
            raise ValueError("page_limit must be at least 1")

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
        context["data"] =  data

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

            if page_count > self.page_limit:
                raise PageLimitExceeded(page_count, self.page_limit)

            content = document.write_pdf()

            if content is None:
                raise TemplateCompileError(
                    "PDF generation returned no document content"
                )

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
            raise TemplateCompileError(
                "The template could not be rendered into a PDF"
            ) from exc


_RENDERERS: dict[str, Renderer] = {
    "pdf": WeasyPrintRenderer()
}

def get_renderer(format: str) -> Renderer:
    """Return the renderer registered for the requested output format."""
    try:
        return _RENDERERS[format.lower()]
    except (KeyError, AttributeError):
        raise ValueError(
            f"Unsupported document format: {format!r}"
        ) from None

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
