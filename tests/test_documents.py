from tests.helpers import (
    INVOICE_CSS,
    assert_problem,
    generate,
    pages_html,
)


# --- Happy path ---
def test_generates_pdf_with_contract_headers(api, acme):
    resp = generate(api, acme.key.raw, options={"filename": "invoice-0042.pdf"})
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert resp.content.startswith(b"%PDF")
    assert resp.headers["content-disposition"] == 'inline; filename="invoice-0042.pdf"'
    assert resp.headers["x-template-version"] == "1"
    assert resp.headers["x-page-count"] == "1"


def test_default_filename_is_slug(api, acme):
    resp = generate(api, acme.key.raw)
    assert resp.headers["content-disposition"] == 'inline; filename="invoice.pdf"'


def test_latest_version_is_default_and_version_can_be_pinned(api, acme, make_template):
    make_template(acme.tenant, "multi-version", versions=2)
    assert generate(api, acme.key.raw, slug="multi-version").headers["x-template-version"] == "2"
    pinned = generate(api, acme.key.raw, slug="multi-version", version=1)
    assert pinned.headers["x-template-version"] == "1"


# --- 404 ---
def test_unknown_template_and_version_are_404(api, acme):
    assert_problem(generate(api, acme.key.raw, slug="nope"), 404, "not_found")
    assert_problem(generate(api, acme.key.raw, version=99), 404, "not_found")


def test_other_tenants_template_is_404(api, acme, make_tenant, make_key):
    globex_key = make_key(make_tenant("Globex"))
    assert_problem(generate(api, globex_key.raw), 404, "not_found")


def test_same_slug_can_exist_in_two_tenants(api, acme, make_tenant, make_key, make_template):
    globex = make_tenant("Globex")
    make_template(globex)
    globex_key = make_key(globex)
    assert generate(api, globex_key.raw).status_code == 200
    assert generate(api, acme.key.raw).status_code == 200


def test_deactivated_template_is_404_and_slug_can_be_reused(api, db, acme, make_template):
    acme.invoice.template.deactivate()
    db.flush()
    assert_problem(generate(api, acme.key.raw), 404, "not_found")

    make_template(acme.tenant)  # same slug; allowed because the old row is inactive
    assert generate(api, acme.key.raw).status_code == 200


def test_deactivated_latest_version_falls_back_to_previous(api, db, acme, make_template):
    made = make_template(acme.tenant, "two-versions", versions=2)
    made.versions[1].deactivate()
    db.flush()

    fallback = generate(api, acme.key.raw, slug="two-versions")
    assert fallback.status_code == 200
    assert fallback.headers["x-template-version"] == "1"
    assert_problem(generate(api, acme.key.raw, slug="two-versions", version=2), 404, "not_found")


# --- 422 ---
def test_missing_required_field_is_validation_failed(api, acme):
    resp = generate(api, acme.key.raw, data={"customer": {}, "lines": []})
    body = assert_problem(resp, 422, "validation_failed")
    assert body["errors"]
    # jsonschema reports a missing required key at the parent object's path.
    assert any(e["path"] == "data.customer" and "name" in e["message"] for e in body["errors"])


def test_wrong_type_reports_the_leaf_path(api, acme):
    data = {"customer": {"name": "Acme"}, "lines": [{"desc": "x", "qty": "ten", "price": 1}]}
    body = assert_problem(generate(api, acme.key.raw, data=data), 422, "validation_failed")
    assert any(e["path"] == "data.lines.0.qty" for e in body["errors"])


def test_undefined_template_variable_is_template_error(api, acme, make_template):
    make_template(acme.tenant, "broken", html="<p>{{ nope }}</p>", schema={"type": "object"})
    resp = generate(api, acme.key.raw, slug="broken", data={})
    assert_problem(resp, 422, "template_error")


def test_sandbox_violation_is_template_error(api, acme, make_template):
    make_template(acme.tenant, "sandboxed", html="<p>{{ ''.__class__ }}</p>", schema={"type": "object"})
    resp = generate(api, acme.key.raw, slug="sandboxed", data={})
    assert_problem(resp, 422, "template_error")


def test_document_over_page_limit_is_422(api, acme, make_template, set_page_limit):
    make_template(acme.tenant, "long-doc", html=pages_html(3), css=INVOICE_CSS, schema={"type": "object"})
    set_page_limit(2)
    assert_problem(generate(api, acme.key.raw, slug="long-doc", data={}), 422, "page_limit_exceeded")


def test_document_at_page_limit_is_allowed(api, acme, make_template, set_page_limit):
    make_template(acme.tenant, "short-doc", html=pages_html(2), css=INVOICE_CSS, schema={"type": "object"})
    set_page_limit(2)
    resp = generate(api, acme.key.raw, slug="short-doc", data={})
    assert resp.status_code == 200
    assert resp.headers["x-page-count"] == "2"
