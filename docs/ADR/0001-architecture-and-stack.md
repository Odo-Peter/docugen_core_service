# ADR 0001: Architecture and stack

- **Status:** Accepted
- **Date:** 2026-09-30
- **Scope:** Milestones 2 and 3 (vertical slice, template management). Async jobs, batching, webhooks, and the admin UI are decided at a high level but deferred; see "Decided, deferred".

## Context

This project is an open-source, templated document generation service: structured JSON plus a template reference in, a generated PDF out. It is built by one developer alongside full-time work, so every choice is judged on three things: production credibility, speed of delivery without learning a new language, and whether it can be defended to a client.

Guiding rules: boring and recognizable tools over trendy ones, a working vertical slice before infrastructure, and every added component must earn its place.

## Milestone scope

| Milestone | Status | Content |
|---|---|---|
| 2. Vertical slice | In scope | One seeded template, synchronous PDF generation over the API, API key auth |
| 3. Template management | In scope | Template CRUD, immutable versions, validation |
| 4. Async jobs and batching | Deferred | Celery queue, job status polling, batch submission |
| 5. Webhooks | Deferred | Completion callbacks (depends on jobs) |
| 6. Admin UI | Deferred | Vite app for templates and job history |
| 7. Docs and case study | Deferred | README, architecture write-up |

## Decisions in effect now

### 1. API: Python, FastAPI, SQLAlchemy 2.x, Alembic, pytest + httpx

**Options considered:** FastAPI, Flask, Django (+ DRF).

**Decision:** FastAPI.

**Why:**
- The JSON payload is the product's contract. Pydantic models make it explicit, and the OpenAPI docs page doubles as a live demo surface.
- The PDF ecosystem (WeasyPrint, ReportLab) is Python-native, so the API stays in the language of its hardest dependency.
- Flask would mean hand-assembling validation, docs, and auth. Django brings an ORM, admin, and auth this service does not need.

**Trade-off to remember:** PDF rendering is CPU-bound and blocking. `async def` endpoints do not make it async, and rendering inside one would stall the event loop. The sync generation endpoint is a plain `def` (run in the threadpool).

**Seam to keep from day one:** generation lives in a plain function, `generate_document(template, data) -> bytes`, with no HTTP objects inside it. The endpoint calls it directly now; a queue worker can call it later without restructuring.

### 2. PDF generation: WeasyPrint + Jinja2 (HTML/CSS templates)

**Options considered:** ReportLab, WeasyPrint, LaTeX, headless Chromium.

**Decision:** WeasyPrint as the primary engine, behind a small `Renderer` interface keyed by output format.

**Why:**
- Templates are managed through the API, so they are stored data. With ReportLab a template is code, and storing executable code from API clients is a security problem. HTML/CSS plus Jinja2 is a document plus variables.
- HTML/CSS templates are editable by non-developers and previewable later in the admin UI.

**Controls built in from the start:**
- Jinja2 `SandboxedEnvironment` with strict undefined variables. Templates are untrusted input.
- Custom WeasyPrint `url_fetcher` that allows only `data:` URIs, blocking `file://` and all network access (SSRF). Bundled fonts are loaded from the image, not fetched.
- Each template declares its variables as JSON Schema; data is validated before rendering and returns 422 with clear errors.
- Fonts are bundled explicitly in the image.

**Known weakness and plan:** WeasyPrint is slower and uses more memory than ReportLab on very large documents. Benchmark 1-, 100-, and 1,000-page documents (time and peak memory), publish the numbers in the case study, and set a documented page cap. A ReportLab engine behind the same interface is added only if the benchmark justifies it. DOCX, if built, is a separate renderer with its own template format.

### 3. Data model (milestones 2 and 3)

Tables are added by Alembic migrations as each milestone needs them.

| Table | Key fields | Milestone |
|---|---|---|
| tenants | id, name, created_at | 2 |
| api_keys | id, tenant_id, name, key_prefix, key_hash, scopes, last_used_at, revoked_at | 2 |
| templates | id, tenant_id, slug, name, created_at, deleted_at | 2 |
| template_versions | id, template_id, version, html, css, variables_schema (JSONB), created_at | 2 |

**Rules:**
- Template versions are immutable: editing creates a new version, so any past render can be reproduced.
- API keys are stored as a SHA-256 hash with a short prefix and shown once on creation. Scopes (`documents:create`, `templates:read`, `templates:write`) let a demo key render but not author templates.
- Every tenant-owned query is filtered by `tenant_id` through one data-access layer, with a test that tenant A cannot read tenant B's data.
- Templates are soft-deleted; public ids are UUIDs; request body size is capped.
- No document payloads or outputs are stored in this phase: the sync endpoint returns the PDF bytes directly.

**Deliberately out of scope:** user accounts and logins, roles, billing, usage metering. The first tenant and key are created with a CLI command that prints the key once.

**Template assets (decided):** logos and images are embedded in templates as data URIs, and fonts are bundled in the image. There are no asset endpoints or assets table; immutable versions would make uploads awkward, and nothing in M2 or M3 needs them. Template size is capped to keep embedded images reasonable. Revisit if a real need for shared or large assets appears.

### 4. Deployment (milestones 2 and 3)

**Options considered:** single VPS with docker compose and Caddy, free PaaS tiers, Oracle Cloud free tier, Kubernetes.

**Decision:** Two named deployments.
- **Reference deployment:** `docker compose` (api, postgres, reverse proxy). Documented for self-hosting and used for development.
- **Live demo deployment:** free tiers. API on a Render free web service, Postgres on Neon (not Render's free Postgres, which expires after 30 days).

**Demo safeguards:** a dedicated demo tenant whose key has no `templates:write` scope, payload cap, render timeout, low page cap, and a simple per-key rate limit.

**Known costs:** cold starts after idle and very limited CPU and memory. Acceptable for a demo; documented in the README. The fallback is a small VPS running the compose stack.

**Domain:** optional for now. A Cloudflare-registered domain can front the API (`api.` and docs) whenever wanted.

## Decided, deferred

These decisions are made but nothing is built until the stated milestone. Detailed design rules are written as a follow-up ADR when milestone 4 starts.

- **Async jobs and batching (M4): Celery with a Redis broker.** RQ is the runner-up. Postgres is the source of truth for job state; tasks are idempotent; the queue is added after the synchronous slice works. One job is one document and a batch is a shared `batch_id`. The `jobs` table arrives in the M4 migration.
- **Webhooks (M5):** signed, retried delivery as its own task; `webhook_deliveries` table arrives in the M5 migration.
- **File storage (first needed at M4, for job outputs):** all storage goes through a thin interface over boto3 and an S3-compatible endpoint. Development and self-hosting use the community `pgsty/minio` fork in compose (pinned tag; upstream MinIO's community edition was archived in 2026 and its official Docker Hub images were removed in September 2026, an accepted and documented risk). The hosted demo points the same code at a hosted S3-compatible service by configuration.
- **Admin UI (M6):** a Vite app; authenticates with a tenant API key held in memory for the session.

## Consequences

- Docker is the deployable unit (WeasyPrint needs system libraries and fonts).
- Memory is the binding constraint in every environment; the page cap comes from the benchmark.
- Three seams keep later change cheap: the `generate_document` function, the `Renderer` interface, and Postgres as the owner of persistent state.

## Verify before relying on it

- Current free-tier terms for Render and Neon.
- At milestone 4: Redis and object-storage options for the demo, the `pgsty/minio` image name and tags, and a presigned-URL and expiry-rule spike.

## Revisit when

- The page-cap benchmark shows WeasyPrint cannot meet the target document sizes (add a ReportLab engine).
- The free demo deployment makes the link feel broken (move to the VPS).
- A real client needs DOCX or multi-region storage (new ADR).
