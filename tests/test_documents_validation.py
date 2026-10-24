"""Request-body validation for POST /v1/documents (422 before any lookup or render)."""

import pytest
from tests.helpers import VALID_DATA, error_fields, post_raw, valid_body, bearer, assert_problem


# --- template.version must be an integer >= 1 ---
@pytest.mark.parametrize("version", [0, -1, 1.5, "abc"])
def test_invalid_template_version_is_rejected(api, acme, version):
    resp = post_raw(api, acme.key.raw, valid_body(template={"slug": "invoice", "version": version}))
    assert resp.status_code == 422
    assert "template.version" in error_fields(resp)


def test_template_version_one_is_the_lowest_accepted(api, acme):
    resp = post_raw(api, acme.key.raw, valid_body(template={"slug": "invoice", "version": 1}))
    assert resp.status_code == 200
    assert resp.headers["x-template-version"] == "1"


def test_malformed_request_uses_problem_json(api, acme):
    resp = api.post(
        "/v1/documents",
        json={"template": {"slug": "Bad Slug"}, "data": {}},
        headers=bearer(acme.key.raw),
    )
    assert_problem(resp, 422, "validation_failed")


# --- format: only "pdf", case-sensitive ---
@pytest.mark.parametrize("fmt", ["docx", "PDF", "", "html"])
def test_unsupported_format_is_rejected(api, acme, fmt):
    resp = post_raw(api, acme.key.raw, valid_body(format=fmt))
    assert resp.status_code == 422
    assert "format" in error_fields(resp)


def test_format_pdf_is_accepted_explicitly(api, acme):
    assert post_raw(api, acme.key.raw, valid_body(format="pdf")).status_code == 200


# --- options.filename: [A-Za-z0-9._-], 1 to 100 characters ---
BAD_FILENAMES = [
    pytest.param('a"b.pdf', id="double-quote"),
    pytest.param("a\r\nX-Injected: 1.pdf", id="crlf-header-injection"),
    pytest.param("a.pdf\n", id="trailing-newline"),
    pytest.param("../secret.pdf", id="path-traversal"),
    pytest.param("dir/a.pdf", id="slash"),
    pytest.param("my file.pdf", id="space"),
    pytest.param("", id="empty"),
    pytest.param("a" * 97 + ".pdf", id="101-chars"),
]


@pytest.mark.parametrize("filename", BAD_FILENAMES)
def test_invalid_filename_is_rejected(api, acme, filename):
    resp = post_raw(api, acme.key.raw, valid_body(options={"filename": filename}))
    assert resp.status_code == 422
    assert "options.filename" in error_fields(resp)
    assert "x-injected" not in resp.headers  # nothing from the input reached a header


@pytest.mark.parametrize("filename", ["invoice-0042.pdf", "a.b_c-d.pdf", "a" * 96 + ".pdf"])
def test_valid_filename_is_echoed_in_content_disposition(api, acme, filename):
    resp = post_raw(api, acme.key.raw, valid_body(options={"filename": filename}))
    assert resp.status_code == 200
    assert resp.headers["content-disposition"] == f'inline; filename="{filename}"'


# --- required fields ---
@pytest.mark.parametrize(
    ("body", "field"),
    [
        pytest.param({"data": VALID_DATA}, "template", id="template-missing"),
        pytest.param({"template": None, "data": VALID_DATA}, "template", id="template-null"),
        pytest.param({"template": "invoice", "data": VALID_DATA}, "template", id="template-string"),
        pytest.param({"template": {"version": 1}, "data": VALID_DATA}, "template.slug", id="slug-missing"),
        pytest.param({"template": {"slug": "Bad Slug"}, "data": VALID_DATA}, "template.slug", id="slug-format"),
        pytest.param({"template": {"slug": "invoice"}}, "data", id="data-missing"),
        pytest.param({"template": {"slug": "invoice"}, "data": []}, "data", id="data-not-object"),
    ],
)
def test_required_fields_and_shapes(api, acme, body, field):
    resp = post_raw(api, acme.key.raw, body)
    assert resp.status_code == 422
    assert field in error_fields(resp)


def test_empty_body_reports_every_missing_field(api, acme):
    resp = post_raw(api, acme.key.raw, {})
    assert resp.status_code == 422
    assert {"template", "data"} <= set(error_fields(resp))


# --- ordering: validation runs before lookup, but after auth ---
def test_validation_runs_before_template_lookup(api, acme):
    """A malformed request for a template that doesn't exist is 422, not 404."""
    body = valid_body(template={"slug": "does-not-exist", "version": 0})
    assert post_raw(api, acme.key.raw, body).status_code == 422


def test_auth_is_checked_before_body_validation(api, acme):
    """No key + malformed body is 401, so bad input can't probe an unauthenticated API."""
    assert post_raw(api, None, {}).status_code == 401
