"""Shared constants and small helpers for the API tests."""

VALID_DATA = {
    "customer": {"name": "Acme"},
    "lines": [{"desc": "Consulting", "qty": 10, "price": 120}],
}

INVOICE_HTML = """<html><body>
<h1>Invoice for {{ customer.name }}</h1>
{% for line in lines %}<p>{{ line.desc }}: {{ line.qty * line.price }}</p>{% endfor %}
</body></html>"""

INVOICE_CSS = "@page { size: A4; margin: 20mm }"

INVOICE_SCHEMA = {
    "type": "object",
    "required": ["customer", "lines"],
    "properties": {
        "customer": {
            "type": "object",
            "required": ["name"],
            "properties": {"name": {"type": "string"}},
        },
        "lines": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["desc", "qty", "price"],
                "properties": {
                    "desc": {"type": "string"},
                    "qty": {"type": "number"},
                    "price": {"type": "number"},
                },
            },
        },
    },
}


def pages_html(n: int) -> str:
    """HTML that renders to exactly n pages."""
    paragraphs = ["<p>page 1</p>"] + [
        f'<p style="break-before: page">page {i}</p>' for i in range(2, n + 1)
    ]
    return "<html><body>" + "".join(paragraphs) + "</body></html>"


def bearer(raw_key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {raw_key}"}


def tamper(raw_key: str) -> str:
    """Same key with the last character changed."""
    return raw_key[:-1] + ("0" if raw_key[-1] != "0" else "1")


def generate(api, raw_key: str | None = None, *, slug="invoice", version=None, data=None, **extra):
    template: dict = {"slug": slug}
    if version is not None:
        template["version"] = version
    body = {"template": template, "data": VALID_DATA if data is None else data, **extra}
    headers = bearer(raw_key) if raw_key else {}
    return api.post("/v1/documents", json=body, headers=headers)


def assert_problem(resp, status: int, code: str) -> dict:
    """Assert an RFC 9457 problem+json response with the contract's code."""
    assert resp.status_code == status, resp.text
    assert resp.headers["content-type"].startswith("application/problem+json")
    body = resp.json()
    assert body["status"] == status
    assert body["code"] == code
    return body


def valid_body(**overrides) -> dict:
    """A request that would succeed against the 'invoice' fixture template."""
    return {"template": {"slug": "invoice"}, "data": VALID_DATA, **overrides}


def post_raw(api, raw_key: str | None, body: dict):
    headers = bearer(raw_key) if raw_key else {}
    return api.post("/v1/documents", json=body, headers=headers)


def error_fields(resp) -> list[str]:
    """Field paths a 422 points at, whichever shape the error body has."""
    body = resp.json()
    if "errors" in body:  # problem+json
        raw = [e["path"] for e in body["errors"]]
    else:  # FastAPI default: {"detail": [{"loc": ["body", "template", "version"], ...}]}
        raw = [".".join(str(part) for part in e["loc"]) for e in body["detail"]]
    return [path.removeprefix("body.") for path in raw]