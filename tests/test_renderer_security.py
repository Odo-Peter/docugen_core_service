"""Renderer security: templates are untrusted input (ADR 0001, decision 2).

Calls render_document directly: no database, no HTTP.
"""

import base64
import socket
import urllib.parse

import pytest

from app.core.renderer.renderer import TemplateCompileError, generate_document as render_document
from tests.security_support import (
    BROKEN,
    ESCAPES,
    MARKER,
    pdf_image_count,
    pdf_text,
    squash,
    tiny_png,
)

pytestmark = pytest.mark.timeout(60)

DATA = {"customer": {"name": "Acme"}}

DATA_PNG = "data:image/png;base64," + base64.b64encode(tiny_png()).decode()
DATA_CSS = "data:text/css;charset=utf-8," + urllib.parse.quote(
    f'body::before {{ content: "{MARKER}" }}'
)


def render(html: str, css: str = "", data: dict | None = None):
    return render_document(
        template_html=html, template_css=css, data=DATA if data is None else data, fmt="pdf"
    )


def attempt(html: str, css: str = "", data: dict | None = None):
    """Render. A refusal must be a TemplateCompileError; returns None in that case.

    Either policy (refuse loudly, or skip the blocked resource and render) is
    acceptable here. What matters is that nothing is fetched.
    """
    try:
        return render(html, css, data)
    except TemplateCompileError:
        return None


def fill(text: str, mapping: dict[str, str]) -> str:
    for key, value in mapping.items():
        text = text.replace(f"@@{key}@@", value)
    return text


def assert_nothing_loaded(result, canary=None) -> None:
    if canary is not None:
        assert canary.connections == 0, "renderer opened a network connection"
    if result is not None:
        assert MARKER not in squash(pdf_text(result.content)), "local file content reached the PDF"
        assert pdf_image_count(result.content) == 0, "an external image reached the PDF"


# --- The harness itself ---------------------------------------------------
def test_canary_records_a_real_connection(canary):
    socket.create_connection(("127.0.0.1", canary.port), timeout=1).close()
    assert canary.connections == 1


def test_control_data_uri_image_is_loaded():
    result = render(f'<img src="{DATA_PNG}" width="20" height="20">')
    assert pdf_image_count(result.content) == 1


def test_control_data_uri_stylesheet_is_applied():
    result = render(f'<link rel="stylesheet" href="{DATA_CSS}"><p>x</p>')
    assert MARKER in squash(pdf_text(result.content))


# --- Network: nothing may connect out -------------------------------------
NETWORK_CARRIERS = {
    "img": ('<img src="@@U@@" width="20" height="20">', ""),
    "link-stylesheet": ('<link rel="stylesheet" href="@@U@@"><p>x</p>', ""),
    "style-import": ('<style>@import url("@@U@@");</style><p>x</p>', ""),
    "css-import": ("<p>x</p>", '@import url("@@U@@");'),
    "css-background": ('<p class="b">x</p>', '.b { background: url("@@U@@") }'),
    "css-font-face": (
        "<p>x</p>",
        '@font-face { font-family: X; src: url("@@U@@") } p { font-family: X }',
    ),
    "object": ('<object data="@@U@@" type="image/png"></object>', ""),
    "embed": ('<embed src="@@U@@">', ""),
    "svg-image": ('<svg width="10" height="10"><image href="@@U@@" width="10" height="10"/></svg>', ""),
}


@pytest.mark.parametrize("scheme", ["http", "https", "ftp"])
@pytest.mark.parametrize("carrier", list(NETWORK_CARRIERS))
def test_remote_urls_are_never_fetched(carrier, scheme, canary):
    html, css = NETWORK_CARRIERS[carrier]
    url = f"{scheme}://{canary.host}/probe"
    result = attempt(html.replace("@@U@@", url), css.replace("@@U@@", url))
    assert_nothing_loaded(result, canary)


def test_html_in_data_cannot_trigger_a_fetch(canary):
    """Even if a value were rendered unescaped, the fetcher must still refuse."""
    hostile = (
        f'<img src="http://{canary.host}/x.png">'
        f'<link rel="stylesheet" href="http://{canary.host}/x.css">'
    )
    attempt("<p>{{ customer.name }}</p>", data={"customer": {"name": hostile}})
    assert canary.connections == 0


# --- Local files: nothing may be read -------------------------------------
# (html, css, what proves the resource loaded: "text" or "image")
FILE_CARRIERS = {
    "link-stylesheet": ('<link rel="stylesheet" href="@@CSS@@"><p>x</p>', "", "text"),
    "link-bare-path": ('<link rel="stylesheet" href="@@CSS_PATH@@"><p>x</p>', "", "text"),
    "style-import": ('<style>@import url("@@CSS@@");</style><p>x</p>', "", "text"),
    "css-import": ("<p>x</p>", '@import url("@@CSS@@");', "text"),
    "img": ('<img src="@@PNG@@" width="20" height="20">', "", "image"),
    "img-bare-path": ('<img src="@@PNG_PATH@@" width="20" height="20">', "", "image"),
    "object": ('<object data="@@PNG@@" type="image/png"></object>', "", "image"),
    "embed": ('<embed src="@@PNG@@">', "", "image"),
}


@pytest.fixture
def secret_files(tmp_path):
    css = tmp_path / "evil.css"
    css.write_text(f'body::before {{ content: "{MARKER}" }}')
    png = tmp_path / "evil.png"
    png.write_bytes(tiny_png())
    return {"CSS": css.as_uri(), "CSS_PATH": str(css), "PNG": png.as_uri(), "PNG_PATH": str(png)}


DATA_URIS = {"CSS": DATA_CSS, "CSS_PATH": DATA_CSS, "PNG": DATA_PNG, "PNG_PATH": DATA_PNG}


@pytest.mark.parametrize("carrier", list(FILE_CARRIERS))
def test_carrier_control_loads_a_data_uri(carrier):
    """If this fails, the carrier can't observe loading here; drop it, don't ignore it."""
    html, css, signal = FILE_CARRIERS[carrier]
    result = render(fill(html, DATA_URIS), fill(css, DATA_URIS))
    if signal == "text":
        assert MARKER in squash(pdf_text(result.content))
    else:
        assert pdf_image_count(result.content) >= 1


@pytest.mark.parametrize("carrier", list(FILE_CARRIERS))
def test_local_files_are_never_read(carrier, secret_files):
    html, css, _ = FILE_CARRIERS[carrier]
    result = attempt(fill(html, secret_files), fill(css, secret_files))
    assert_nothing_loaded(result)


# --- Sandbox escapes ------------------------------------------------------
@pytest.mark.parametrize("payload", ESCAPES.values(), ids=ESCAPES.keys())
def test_sandbox_escape_is_a_template_error(payload):
    with pytest.raises(TemplateCompileError):
        render(f"<p>{payload}</p>")


SIDE_EFFECTS = {
    "lipsum-os-system": "{{ lipsum.__globals__.os.system('touch @@PATH@@') }}",
    "cycler-os-popen": "{{ cycler.__init__.__globals__.os.popen('touch @@PATH@@') }}",
    "namespace-os-system": "{{ namespace.__init__.__globals__.os.system('touch @@PATH@@') }}",
    "import-os-system": "{{ __import__('os').system('touch @@PATH@@') }}",
}


@pytest.mark.parametrize("payload", SIDE_EFFECTS.values(), ids=SIDE_EFFECTS.keys())
def test_escape_payloads_have_no_side_effects(payload, tmp_path):
    flag = tmp_path / "pwned"
    with pytest.raises(TemplateCompileError):
        render(f"<p>{payload.replace('@@PATH@@', str(flag))}</p>")
    assert not flag.exists(), "payload executed a command"


def test_sandbox_still_allows_normal_templating():
    html = "{% for l in lines %}<p>{{ l.desc | upper }} {{ l.qty * l.price }}</p>{% endfor %}"
    data = {"lines": [{"desc": "consulting", "qty": 10, "price": 120}]}
    text = squash(pdf_text(render(html, data=data).content))
    assert "CONSULTING1200" in text


# --- Failures surface as template errors, never bare exceptions -----------
@pytest.mark.parametrize("template", BROKEN.values(), ids=BROKEN.keys())
def test_broken_templates_raise_template_compile_error(template):
    with pytest.raises(TemplateCompileError):
        render(f"<p>{template}</p>")


# --- Data is data ---------------------------------------------------------
def test_data_is_not_evaluated_as_a_template():
    result = render("<p>{{ customer.name }}</p>", data={"customer": {"name": "{{ 7*7 }}"}})
    text = squash(pdf_text(result.content))
    assert "{{7*7}}" in text
    assert "49" not in text


def test_data_is_html_escaped():
    result = render("<p>{{ customer.name }}</p>", data={"customer": {"name": "<b>bold</b>"}})
    assert "<b>bold</b>" in squash(pdf_text(result.content))