# Document Generation Service

A templated document generation API: structured JSON + a template in, a generated PDF out.

Built as a portfolio project demonstrating production-oriented API design — not a tutorial app. See [`docs/adr/0001-architecture-and-stack.md`](docs/adr/0001-architecture-and-stack.md) for the full architecture reasoning and [`docs/api-contract.md`](docs/api-contract.md) for the API surface.

**Status:** scaffold only. Milestones 2 (vertical slice) and 3 (template management) are being built next — see [Roadmap](#roadmap).

## Stack

Python · FastAPI · SQLAlchemy 2.x · Alembic · PostgreSQL · WeasyPrint + Jinja2 · Docker Compose

Reasoning for every choice lives in the ADR — this README won't repeat it.

## Local development

Requires [uv](https://github.com/astral-sh/uv), Docker, and Docker Compose.

```bash
# 1. Install dependencies and set up a local virtualenv
uv sync

# 2. Copy env config
cp .env.example .env

# 3. Start Postgres + the API (runs migrations automatically)
docker compose up --build

# API now serving at http://localhost:8000
# Interactive docs: http://localhost:8000/docs
```

Running tests locally (outside Docker, against a local venv):

```bash
uv sync --extra dev
uv run pytest
```

Pre-commit hooks (ruff lint + format):

```bash
uv run pre-commit install
```

## Creating a tenant + API key

Once the CLI is implemented (step 5):

```bash
docker compose exec api python -m scripts.create_tenant --name "Acme Inc"
# prints the raw API key once — store it, it is not recoverable
```

## Project layout

```
app/
  api/v1/           # HTTP layer — routers, request/response models
  core/renderer/     # Renderer interface + generate_document() — no HTTP deps
  models/            # SQLAlchemy ORM models
  config.py           # Settings (env-driven)
  db.py                # Engine/session
  main.py               # FastAPI app assembly
migrations/         # Alembic
docs/
  adr/               # Architecture decision records
  api-contract.md     # API surface (source of truth alongside openapi.json)
tests/
scripts/            # create-tenant CLI, etc.
```

The `app/core/renderer` package is intentionally decoupled from FastAPI — it's called directly by the sync endpoint today, and will be called unchanged by a queue worker at milestone 4.

## Roadmap

| Milestone                                            | Status                 |
| ---------------------------------------------------- | ---------------------- |
| 1. Architecture & stack decision                     | ✅ Done — see ADR 0001 |
| 2. Vertical slice (sync generation, seeded template) | 🚧 In progress         |
| 3. Template management (CRUD, versions)              | Planned                |
| 4. Async jobs & batching                             | Planned                |
| 5. Webhooks                                          | Planned                |
| 6. Admin UI                                          | Planned                |
| 7. Docs & case study                                 | Planned                |

## License

TODO: pick a license (MIT is the usual default for a portfolio piece meant to be freely readable/forkable).
