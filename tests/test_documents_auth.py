import pytest

from app.core.scopes import ApiKeyScope
from tests.helpers import assert_problem, generate, tamper, VALID_DATA


def test_missing_header_is_401(api):
    resp = generate(api, None)
    assert_problem(resp, 401, "unauthorized")
    assert resp.headers["www-authenticate"].startswith("Bearer")


@pytest.mark.parametrize(
    "authorization",
    [
        "Bearer not-a-key",
        "Bearer dg_only_two_parts_x",
        "Bearer dg_deadbeef_" + "a" * 48,  # well formed, unknown prefix
        "Basic dXNlcjpwYXNz",  # wrong scheme
        "Bearer",
    ],
)
def test_bad_credentials_are_401(api, acme, authorization):
    resp = api.post(
        "/v1/documents",
        json={"template": {"slug": "invoice"}, "data": VALID_DATA},
        headers={"Authorization": authorization},
    )
    assert_problem(resp, 401, "unauthorized")


def test_tampered_secret_is_401(api, acme):
    assert_problem(generate(api, tamper(acme.key.raw)), 401, "unauthorized")


def test_deactivated_key_is_401(api, db, acme):
    acme.key.row.deactivate()
    db.flush()
    assert_problem(generate(api, acme.key.raw), 401, "unauthorized")


def test_deactivated_tenant_stops_its_active_keys(api, db, acme):
    acme.tenant.deactivate()
    db.flush()
    assert acme.key.row.is_active  # the key itself is still active
    assert_problem(generate(api, acme.key.raw), 401, "unauthorized")


def test_failures_are_indistinguishable(api, db, acme):
    """A caller can't tell a wrong secret from a deactivated key."""
    wrong_secret = generate(api, tamper(acme.key.raw))
    acme.key.row.deactivate()
    db.flush()
    deactivated = generate(api, acme.key.raw)
    assert wrong_secret.status_code == deactivated.status_code == 401
    assert wrong_secret.json() == deactivated.json()


def test_valid_key_works_and_stamps_last_used(api, db, acme):
    assert acme.key.row.last_used_at is None
    assert generate(api, acme.key.raw).status_code == 200
    db.refresh(acme.key.row)
    assert acme.key.row.last_used_at is not None


def test_key_without_documents_scope_is_403(api, make_key, acme):
    read_only = make_key(acme.tenant, scopes=[ApiKeyScope.TEMPLATES_READ])
    assert_problem(generate(api, read_only.raw), 403, "forbidden")


def test_demo_key_scopes_can_render(api, make_key, acme):
    demo = make_key(
        acme.tenant, scopes=[ApiKeyScope.DOCUMENTS_CREATE, ApiKeyScope.TEMPLATES_READ]
    )
    assert generate(api, demo.raw).status_code == 200