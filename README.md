# Document Generation Service

A templated document generation API: structured JSON + a template in, a generated PDF out.

Built as a project demonstrating production-oriented API design. See [`docs/adr/0001-architecture-and-stack.md`](docs/adr/0001-architecture-and-stack.md) for the architecture reasoning and [`docs/api-contract.md`](docs/api-contract.md) for the API surface.

**Status:** milestone 2 (vertical slice) is mostly built: multi-tenant API-key auth, versioned templates in the data model, and synchronous PDF generation. Template management endpoints, the page-cap benchmark, and the full test suite are next. See the [roadmap](#roadmap).

## Stack

Python · FastAPI · SQLAlchemy 2.x · Alembic · PostgreSQL · WeasyPrint + Jinja2 · jsonschema · Docker Compose · uv

Reasoning for each choice lives in the ADR; this README won't repeat it.

## Local development

Requires [uv](https://github.com/astral-sh/uv), Docker, Docker Compose, and make.

```bash
# 1. Config. Set POSTGRES_PASSWORD (compose refuses to start without it).
cp .env.example .env

# 2. Start Postgres + the API (the api container runs migrations first)
make start

# API: http://localhost:8000    Interactive docs: http://localhost:8000/docs
```

If port 5432 or 8000 is already taken on your machine, set `POSTGRES_HOST_PORT` / `API_HOST_PORT` in `.env`. Only the host side changes. If you change the Postgres port, update the port in `DATABASE_URL` too, since that value is used by tools running on your host.

### Make targets

| Command         | What it does                                                               |
| --------------- | -------------------------------------------------------------------------- |
| `make start`    | Build and start all services (detached)                                    |
| `make stop`     | Stop and remove containers (data volume kept)                              |
| `make restart`  | Stop, then start                                                           |
| `make build`    | Rebuild images without starting                                            |
| `make logs`     | Follow logs from all services                                              |
| `make ps`       | Show service status                                                        |
| `make clean`    | Stop everything and delete the Postgres data volume                        |
| `make reset-db` | Delete only the Postgres data volume and bring services back up            |
| `make test`     | Run the test suite (`make test ARGS="-k health -x"` passes args to pytest) |
| `make test-cov` | Run tests with a coverage report                                           |

Changing the Postgres user, password or database name has no effect on an existing volume. Run `make reset-db` after changing them.

### Create a dev tenant and API key

```bash
uv run python -m scripts.seed_dev
```

This creates a tenant, an API key, and an `invoice` template with one version, then prints the key once. It runs on your host, so `DATABASE_URL` in `.env` must point at `localhost` and your Postgres host port. The `create_tenant` CLI that will replace it is not implemented yet.

### Generate a document

```bash
export KEY=dg_xxxxxxxx_xxxxxxxx...   # printed by the seed script

curl -s -D - -X POST http://localhost:8000/v1/documents \
  -H "Authorization: Bearer $KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "template": {"slug": "invoice"},
    "data": {"customer": {"name": "Acme"},
             "lines": [{"desc": "Consulting", "qty": 10, "price": 120}]},
    "options": {"filename": "invoice-0042.pdf"}
  }' --output invoice.pdf
```

You should get `200` with `Content-Type: application/pdf`, `X-Template-Version`, and `X-Page-Count` headers.

### Tests and linting

```bash
make test
uv run pre-commit install    # ruff lint + format on commit
```

Tests run on your host and import the app, which imports WeasyPrint, so the host needs WeasyPrint's system libraries (Pango and GDK-Pixbuf; package names vary by distro release). Tests that touch the database need Postgres running (`make start`) and should use a separate test database so they don't disturb your dev data.

## Project layout

```
app/
  api/v1/
    endpoints/       # routers + auth dependencies (HTTP layer only)
    schemas/         # Pydantic request/response models
  services/          # use-case logic (e.g. DocumentService); raises ApiError
  core/
    renderer/        # Renderer interface + render_document(); no HTTP deps
    queries.py       # active()/tenant_active()/get_version(): all reads go here
    scopes.py        # ApiKeyScope enum
    errors.py        # ApiError -> RFC 9457 problem+json
  models/            # SQLAlchemy models, prefixed-ID helper, custom column types
  config.py          # Settings (env-driven)
  db.py              # Engine, session, declarative Base (timestamps, is_active)
  main.py            # FastAPI app assembly
migrations/          # Alembic
docs/
  adr/               # Architecture decision records
  api-contract.md    # API surface
tests/
scripts/             # seed_dev.py (create_tenant CLI planned)
```

The `app/core` package has no dependency on FastAPI. The service calls `render_document` directly today, and a queue worker will call it unchanged at milestone 4.

## Roadmap

| Milestone                                         | Status                                     |
| ------------------------------------------------- | ------------------------------------------ |
| 1. Architecture and stack decision                | Done, see ADR 0001                         |
| 2. Vertical slice (sync generation, auth, models) | In progress: core built; outstanding below |
| 3. Template management (CRUD, versions)           | Not started                                |
| 4. Async jobs and batching                        | Planned                                    |
| 5. Webhooks                                       | Planned                                    |
| 6. Admin UI                                       | Planned                                    |
| 7. Docs and case study                            | Planned                                    |

**Outstanding for milestone 2:**

- Verify the first migration end to end (partial indexes, `CHECK` constraints, `text[]` scopes)
- Run the page-cap benchmark and set `PAGE_LIMIT`
- Test suite: happy path, 401/403/404/422, tenant isolation, deactivated key and tenant
- Map FastAPI's request-validation errors to the contract's problem+json
- `X-Request-Id`, request-size limit, per-key rate limit
- Commit `openapi.json` and diff it in CI
- Replace the seed script with the `create_tenant` CLI

## Known issues

- **Python version mismatch.** The Docker image runs Python 3.12, but a local `uv sync` may pick a newer interpreter (3.13 has been seen). Add a `.python-version` file and align `requires-python` so tests and production run the same version.
- **Render timeout is not enforced.** A runaway render keeps its worker busy until it finishes. The page cap is the practical limit until rendering moves to a subprocess (see ADR 0001).
- **Template immutability is enforced in the ORM only.** Bulk updates and raw SQL bypass it.

## License

TODO: pick a license (MIT is the usual default for a portfolio piece meant to be freely readable and forkable).
