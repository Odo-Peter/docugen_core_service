# ruff: noqa: E402
"""Test fixtures: isolated test database, rollback-per-test session, factories."""

import hashlib
import os
import secrets
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.config import get_settings

# --- Point the app at the TEST database before anything creates an engine. ---
ROOT = Path(__file__).resolve().parents[1]


def _test_url():
    url = make_url(os.environ.get("TEST_DATABASE_URL") or get_settings().database_url)
    database = url.database
    if database is None:
        raise ValueError("TEST_DATABASE_URL must include a database name")
    if not database.endswith("_test"):
        url = url.set(database=f"{database}_test")
    return url


TEST_URL = _test_url()
os.environ["DATABASE_URL"] = TEST_URL.render_as_string(hide_password=False)
get_settings.cache_clear()

from app.core.scopes import ApiKeyScope
from app.db import engine, get_db_session
from app.main import app
from app.models.api_key import ApiKey
from app.models.template_version import TemplateVersion
from app.models.template import Template
from app.models.tenant import Tenant

from tests.helpers import INVOICE_CSS, INVOICE_HTML, INVOICE_SCHEMA


@pytest.fixture(scope="session")
def _database():
    """Fresh docgen_test database, built by running the real migrations."""
    assert TEST_URL.database is not None and TEST_URL.database.endswith("_test"), "refusing to drop a non-test database"

    admin = create_engine(TEST_URL.set(database="postgres"), isolation_level="AUTOCOMMIT")

    with admin.connect() as conn:
        conn.execute(text(f'DROP DATABASE IF EXISTS "{TEST_URL.database}" WITH (FORCE)'))
        conn.execute(text(f'CREATE DATABASE "{TEST_URL.database}"'))

    admin.dispose()

    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "migrations"))
    command.upgrade(cfg, "head")
    yield
    engine.dispose()


@pytest.fixture
def db(_database):
    """Session inside an outer transaction that is rolled back after the test.

    Code under test may call commit() (auth stamps last_used_at); with
    create_savepoint that only releases a savepoint, not the outer transaction.
    """
    connection = engine.connect()
    outer = connection.begin()
    session = Session(bind=connection, autoflush=False, join_transaction_mode="create_savepoint")
    try:
        yield session
    finally:
        session.close()
        outer.rollback()
        connection.close()


@pytest.fixture
def api(db):
    """Sync test client whose requests use the rolled-back session."""

    def override():
        yield db

    app.dependency_overrides[get_db_session] = override
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
def set_page_limit(monkeypatch):
    def _set(limit: int) -> None:
        monkeypatch.setattr(get_settings(), "page_limit", limit)

    return _set


# --- Factories ---


@dataclass
class IssuedKey:
    raw: str  # the only time the raw key exists, as in production
    row: ApiKey


@pytest.fixture
def make_tenant(db):
    def _make(name: str) -> Tenant:
        tenant = Tenant(name=name)
        db.add(tenant)
        db.flush()
        return tenant

    return _make


@pytest.fixture
def make_key(db):
    def _make(tenant: Tenant, scopes=(ApiKeyScope.DOCUMENTS_CREATE,)) -> IssuedKey:
        prefix, secret = secrets.token_hex(4), secrets.token_hex(24)
        raw = f"dg_{prefix}_{secret}"
        row = ApiKey(
            tenant_id=tenant.id,
            name="test key",
            key_prefix=prefix,
            key_hash=hashlib.sha256(raw.encode()).hexdigest(),
            scopes=list(scopes),
        )
        db.add(row)
        db.flush()
        return IssuedKey(raw=raw, row=row)

    return _make


@pytest.fixture
def make_template(db):
    def _make(
        tenant: Tenant,
        slug: str = "invoice",
        *,
        versions: int = 1,
        html: str = INVOICE_HTML,
        css: str = INVOICE_CSS,
        schema: dict = INVOICE_SCHEMA,
    ):
        template = Template(tenant_id=tenant.id, slug=slug, name=slug.title())
        db.add(template)
        db.flush()
        rows = [
            TemplateVersion(template_id=template.id, version=n, html=html, css=css, variables_schema=schema) for n in range(1, versions + 1)
        ]
        db.add_all(rows)
        db.flush()
        return SimpleNamespace(template=template, versions=rows)

    return _make


@pytest.fixture
def acme(make_tenant, make_key, make_template):
    """A tenant with a documents:create key and an active 'invoice' template (v1)."""
    tenant = make_tenant("Acme")
    return SimpleNamespace(tenant=tenant, key=make_key(tenant), invoice=make_template(tenant))
