# ADR 0001: Architecture and stack

- **Status:** Accepted. Amended 2026-10-24 (see [Amendments](#amendments)).
- **Date:** 2026-09-30
- **Scope:** Milestones 2 and 3 (vertical slice, template management). Async jobs, batching, webhooks, and the admin UI are decided at a high level but deferred; see "Decided, deferred".

## Context

This project is an open-source, templated document generation service: structured JSON plus a template reference in, a generated PDF out. Every choice is judged on: production credibility, speed of delivery, and viability.

Guiding rules: boring and recognizable tools over trendy ones, a working vertical slice before infrastructure, and every added component must earn its place.

## Milestone scope

| Milestone                  | Status                                          | Content                                                                |
| -------------------------- | ----------------------------------------------- | ---------------------------------------------------------------------- |
| 2. Vertical slice          | In progress (core built, hardening outstanding) | Seeded template, synchronous PDF generation over the API, API key auth |
| 3. Template management     | Not started                                     | Template CRUD, immutable versions, validation                          |
| 4. Async jobs and batching | Deferred                                        | Celery queue, job status polling, batch submission                     |
| 5. Webhooks                | Deferred                                        | Completion callbacks (depends on jobs)                                 |
| 6. Admin UI                | Deferred                                        | Vite app for templates and job history                                 |
| 7. Docs and case study     | Deferred                                        | README, architecture write-up                                          |

Detailed status per item lives in the README roadmap and the implementation table in `api-contract.md`.

## Decisions in effect now

### 1. API: Python, FastAPI, SQLAlchemy 2.x, Alembic, pytest + httpx

**Options considered:** FastAPI, Flask, Django (+ DRF).

**Decision:** FastAPI.

**Why:**

- The JSON payload is the product's contract. Pydantic models make it explicit, and the OpenAPI docs page doubles as a live demo surface.
- The PDF ecosystem (WeasyPrint, ReportLab) is Python-native, so the API stays in the language of its hardest dependency.
- Flask would mean hand-assembling validation, docs, and auth. Django brings an ORM, admin, and auth this service does not need.

**Layering:**

- **Routers** (`app/api/v1/endpoints`) parse the request, resolve auth through dependencies, call a service, and shape the HTTP response. No business logic.
- **Services** (e.g. `DocumentService`) hold the use-case logic and raise `ApiError`. They take typed request schemas and return plain result objects, never `Response` objects.
- **Core** (`app/core`) holds everything with no HTTP dependency: the renderer, query helpers (`queries.py`), scopes (`scopes.py`), and errors (`errors.py`).

**Trade-off to remember:** PDF rendering is CPU-bound and blocking. `async def` endpoints do not make it async, and rendering inside one would stall the event loop. The generation endpoint is a plain `def` (run in the threadpool).

**Seam to keep from day one:** rendering lives in a plain function in `app/core/renderer`, `render_document(template_html, template_css, data, fmt) -> RenderResult` (content, content type, page count), with no HTTP objects inside it. The service calls it directly now; a queue worker can call it later without restructuring.

### 2. PDF generation: WeasyPrint + Jinja2 (HTML/CSS templates)

**Options considered:** ReportLab, WeasyPrint, LaTeX, headless Chromium.

**Decision:** WeasyPrint as the primary engine, behind a small `Renderer` interface keyed by output format.

**Why:**

- Templates are managed through the API, so they are stored data. With ReportLab a template is code, and storing executable code from API clients is a security problem. HTML/CSS plus Jinja2 is a document plus variables.
- HTML/CSS templates are editable by non-developers and previewable later in the admin UI.

**Controls built in from the start:**

- Jinja2 `SandboxedEnvironment` with strict undefined variables. Templates are untrusted input.
- Custom WeasyPrint `url_fetcher` that allows only `data:` URIs, blocking `file://` and all network access (SSRF). Bundled fonts are loaded from the image, not fetched.
- Each template declares its variables as JSON Schema; request data is validated before rendering and returns 422 with per-field errors. Schemas themselves are validated at publish time (M3).
- Fonts are bundled explicitly in the image.
- `format` is typed `Literal["pdf"]`, so unsupported formats fail request validation. DOCX is additive later.
- `options.filename` is restricted to `[A-Za-z0-9._-]` so the `Content-Disposition` header cannot be injected.

**Known weakness and plan:** WeasyPrint is slower and uses more memory than ReportLab on very large documents. Benchmark 1-, 100-, and 1,000-page documents (time and peak memory), publish the numbers in the case study, and set a documented page cap. A ReportLab engine behind the same interface is added only if the benchmark justifies it. DOCX, if built, is a separate renderer with its own template format. **Status: benchmark pending; `PAGE_LIMIT` is unset until it runs.**

**Render timeout (open):** a runaway render cannot be cancelled from a threadpool worker, since Python cannot kill a thread and WeasyPrint has no cancellation. Real enforcement of the 30 s limit requires rendering in a subprocess with a timeout. Until then the page cap is the practical limit.

### 3. Data model (milestones 2 and 3)

Tables are added by Alembic migrations as each milestone needs them.

| Table             | ID prefix | Key fields                                                               | Milestone |
| ----------------- | --------- | ------------------------------------------------------------------------ | --------- |
| tenants           | `tnt_`    | id, name, description                                                    | 2         |
| api_keys          | `key_`    | id, tenant_id, name, key_prefix, key_hash, scopes (text[]), last_used_at | 2         |
| templates         | `tpl_`    | id, tenant_id, slug, name                                                | 2         |
| template_versions | `ver_`    | id, template_id, version, html, css, variables_schema (JSONB)            | 2         |

Every table also carries four columns inherited from the declarative `Base`: `created_at`, `updated_at` (UTC, timestamptz), `is_active`, and `deactivated_at`.

**Rules:**

_Identity_

- IDs are prefixed ULIDs (`<prefix><ULID>`), generated in the application, stored as `String(50)`. Every foreign key is `String(50)`, not a UUID column.

_Deactivation instead of deletion_

- Rows are deactivated, never deleted. `Base.deactivate()` sets `is_active` false and stamps `deactivated_at`; `reactivate()` reverses it. Always use these methods, never set the flag directly, so the two columns cannot disagree.
- Reads go through `app/core/queries.py` (`active()`, `tenant_active()`, `get_version()`). Every tenant-owned query is filtered by `tenant_id` and `is_active` there, with a test that tenant A cannot read tenant B's data. A deactivated resource looks the same as a missing one (404).
- Joins are not filtered automatically: when joining a second table, filter its `is_active` explicitly.

_Uniqueness_

- Tenant names are unique case-insensitively among active tenants (partial unique index on `lower(name)` where `is_active`). Deactivating a tenant frees its name.
- Template slugs are unique per tenant among active templates (partial unique index), and a `CHECK` enforces `^[a-z0-9-]{3,64}$`. Deactivating a template frees its slug; reactivating it can collide with a newer template and must return 409.
- `api_keys.key_prefix` is globally unique and not partial, so a deactivated key's prefix is never reissued.

_Template versions_

- Versions are immutable: editing creates a new version, so any past render can be reproduced. An ORM `before_update` guard rejects changes to content columns. It does not cover bulk updates or raw SQL; add a Postgres trigger if anything else ever writes to this table.
- Numbered from 1 per template (`UNIQUE (template_id, version)`, `CHECK (version >= 1)`). Numbers are never reused, even after a version is deactivated: the next number is the maximum over all rows, active or not. Two concurrent publishes can compute the same number; the unique constraint rejects the loser, which retries once or returns 409.
- Versions have no `tenant_id`. Ownership comes from the parent template, so versions are always read through it.
- "Latest" means the highest-numbered active version of an active template. `current_version` is derived, not stored, so there is no second source of truth to drift.

_Other_

- API keys are stored as a SHA-256 hash of the full key string with a short lookup prefix, and shown once on creation. Never store the raw key.
- No document payloads or outputs are stored in this phase: the sync endpoint returns the PDF bytes directly.
- Request body size is capped.

**Deliberately out of scope:** user accounts and logins, roles, billing, usage metering. Tenants and keys are created by a script that prints the key once.

**Template assets (decided):** logos and images are embedded in templates as data URIs, and fonts are bundled in the image. There are no asset endpoints or assets table; immutable versions would make uploads awkward, and nothing in M2 or M3 needs them. Template size is capped to keep embedded images reasonable. Revisit if a real need for shared or large assets appears.

### 4. Deployment (milestones 2 and 3)

**Options considered:** single VPS with docker compose and Caddy, free PaaS tiers, Oracle Cloud free tier, Kubernetes.

**Decision:** Two named deployments.

- **Reference deployment:** `docker compose` (api, postgres). Documented for self-hosting and used for development. A reverse proxy is added for a real self-hosted setup.
- **Live demo deployment:** free tiers. API on a Render free web service, Postgres on Neon (not Render's free Postgres, which expires after 30 days).

**Reference deployment configuration:**

- Everything is configured through `.env`. Postgres credentials and database name are interpolated into both services, so the container-side `DATABASE_URL` is built from the same variables as the database and cannot drift. `POSTGRES_PASSWORD` is required: compose refuses to start without it.
- Host ports are overridable (`POSTGRES_HOST_PORT`, `API_HOST_PORT`) for machines where 5432 or 8000 is taken. Only the host side changes; containers talk to each other on the internal network at `db:5432`.
- The Postgres data lives in a named volume. `make clean` and `make reset-db` remove it.

**Image pinning:** the base image is `python:3.12-slim-bookworm`, not the floating `python:3.12-slim`. That tag moved to Debian 13, which renamed `libgdk-pixbuf2.0-0` and broke the build with no change on our side. `uv` is pinned to a specific release for the same reason. Both are bumped deliberately.

**Demo safeguards:** a dedicated demo tenant whose key has no `templates:write` scope, payload cap, render timeout, low page cap, and a simple per-key rate limit.

**Known costs:** cold starts after idle and very limited CPU and memory. Acceptable for a demo; documented in the README. The fallback is a small VPS running the compose stack.

**Domain:** optional for now. A Cloudflare-registered domain can front the API (`api.` and docs) whenever wanted.

### 5. Authentication, scopes, and errors

**Key format:** `dg_<prefix>_<secret>`. Prefix and secret are hex (`secrets.token_hex`), because the parser splits on `_` and an underscore inside either part would break it.

**Validation:** the prefix locates the row; the SHA-256 of the full key string is compared to `key_hash` with `hmac.compare_digest`. A key is valid only if the key and its tenant are both active, so deactivating a tenant stops all of its keys. Every failure returns the same 401, so a caller cannot tell a wrong secret from a deactivated key. `last_used_at` is updated at most once per minute per key.

**Scopes:** `documents:create`, `templates:read`, `templates:write`, defined as a `StrEnum` (`ApiKeyScope`, in `app/core/scopes.py`) so the model and the API layer can both import it. They are stored as `text[]` with no native Postgres enum, so adding a scope never needs `ALTER TYPE`. A `TypeDecorator` validates on write and returns enum members on read. There is no default: every key's privileges are chosen explicitly. The demo key gets `documents:create` and `templates:read`.

**Context:** auth resolves to a frozen `AuthContext` (tenant id, key id, scopes). The tenant always comes from the key, never from the body or URL.

**Errors:** every error is raised as `ApiError` and rendered as RFC 9457 `application/problem+json` with a stable `code` string. The `ErrorCode` values must equal the codes in `api-contract.md`.

## Decided, deferred

These decisions are made but nothing is built until the stated milestone. Detailed design rules are written as a follow-up ADR when milestone 4 starts.

- **Async jobs and batching (M4): Celery with a Redis broker.** RQ is the runner-up. Postgres is the source of truth for job state; tasks are idempotent; the queue is added after the synchronous slice works. One job is one document and a batch is a shared `batch_id`. The `jobs` table arrives in the M4 migration.
- **Webhooks (M5):** signed, retried delivery as its own task; `webhook_deliveries` table arrives in the M5 migration.
- **File storage (first needed at M4, for job outputs):** all storage goes through a thin interface over boto3 and an S3-compatible endpoint. Development and self-hosting use the community `pgsty/minio` fork in compose (pinned tag; upstream MinIO's community edition was archived in 2026 and its official Docker Hub images were removed in September 2026, an accepted and documented risk). The hosted demo points the same code at a hosted S3-compatible service by configuration.
- **Admin UI (M6):** a Vite app; authenticates with a tenant API key held in memory for the session.

## Consequences

- Docker is the deployable unit (WeasyPrint needs system libraries and fonts).
- Memory is the binding constraint in every environment; the page cap comes from the benchmark.
- Three seams keep later change cheap: `render_document`, the `Renderer` interface, and Postgres as the owner of persistent state.
- Soft deletion means every query must remember the active filter. The helpers in `app/core/queries.py` are the mitigation, and reviews should treat a bare `select(Model)` on a tenant-owned table as a bug.
- The immutability guard is ORM-level only.

## Verify before relying on it

- Current free-tier terms for Render and Neon.
- At milestone 4: Redis and object-storage options for the demo, the `pgsty/minio` image name and tags, and a presigned-URL and expiry-rule spike.
- The generated migration: partial unique indexes render with their `WHERE` clause, the `CHECK` constraints are present, and `scopes` renders as a plain `text[]` with no import from `app`.

## Revisit when

- The page-cap benchmark shows WeasyPrint cannot meet the target document sizes (add a ReportLab engine).
- Render timeouts matter in practice (move rendering to a subprocess).
- The free demo deployment makes the link feel broken (move to the VPS).
- Something other than the ORM needs to write template versions (add a database trigger for immutability).
- A real client needs DOCX or multi-region storage (new ADR).

## Amendments

**2026-10-24**

- IDs changed from UUIDs to prefixed ULID strings.
- Soft deletion unified: `is_active` and `deactivated_at` on `Base` replace `templates.deleted_at` and `api_keys.revoked_at`.
- Template versions: added the immutability guard, the `version >= 1` check, never-reused numbering, and the rule that they are read through the parent template.
- API keys: the full key string is hashed (previously ambiguous between the full key and the secret); a key is valid only while its tenant is active; scopes are typed with a `StrEnum` and stored as `text[]`.
- Added the layering (routers, services, core) and renamed the rendering seam to `render_document`.
- Deployment: pinned the base image to bookworm and `uv` to a release; moved compose configuration to `.env` interpolation; added the named volume and `make` targets.
- Added decision 5 (authentication, scopes, errors).
