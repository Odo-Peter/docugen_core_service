import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# TODO(step 7): a db session fixture (transaction-per-test, rolled back at
# the end) and a tenant/api-key factory fixture, once step 2's models and
# step 5's auth exist. The tenant-isolation test from ADR 0001 depends on
# having two seeded tenants + keys available here.
