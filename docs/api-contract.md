# API contract (draft v1)

Companion to ADR 0001. This fixes the public shape of the API before any app code is written. Pydantic models are written to match it, and the generated `openapi.json` is committed and diffed in CI so the contract cannot drift silently.

**Scope:** milestones 2 (synchronous generation) and 3 (template management). Jobs, batching, and webhooks are deferred; see the last section.

## Conventions

- **Base path:** `/v1`. JSON everywhere except the PDF response of the generation endpoint.
- **Auth:** `Authorization: Bearer <api_key>`. Keys look like `dg_<prefix>_<secret>`; the prefix is used for lookup, the full key is hashed. The tenant is derived from the key, so tenant ids never appear in URLs.
- **Scopes:** each key carries scopes: `documents:create`, `templates:read`, `templates:write`. A missing scope returns 403. The public demo key gets everything except `templates:write`.
- **IDs:** UUID strings. **Timestamps:** ISO 8601 UTC. **Template slugs:** lowercase `a-z0-9-`, 3 to 64 characters, unique per tenant.
- **Pagination:** cursor based. `?limit=50&cursor=...` returns `{"data": [...], "next_cursor": "..." | null}`. Max limit 100.
- **Formats:** the `format` field defaults to `"pdf"`. It exists from day one so DOCX is additive later.
- **Limits (configurable):** request body 5 MB (413), render timeout 30 s, page cap set from the benchmark.

## Errors

All errors use `application/problem+json` (RFC 9457) with a stable `code`:

```json
{
  "type": "https://docs.example.com/errors/validation_failed",
  "title": "Request validation failed",
  "status": 422,
  "code": "validation_failed",
  "detail": "data does not match the template's variables_schema",
  "errors": [
    {"path": "data.customer.name", "message": "is required"}
  ]
}
```

| Status | `code` | When |
|---|---|---|
| 401 | `unauthorized` | Missing, malformed, or revoked key |
| 403 | `forbidden` | Key lacks the required scope |
| 404 | `not_found` | Unknown template or version (also for other tenants' resources) |
| 409 | `conflict` | Slug already exists |
| 413 | `payload_too_large` | Body over the size limit |
| 422 | `validation_failed` | Bad request body, or `data` fails the template's JSON Schema |
| 422 | `template_error` | Template fails to compile or render (strict undefined variables, sandbox violation) |
| 422 | `page_limit_exceeded` | Document would exceed the page cap |
| 429 | `rate_limited` | Per-key limit hit; `Retry-After` header set |
| 504 | `render_timeout` | Render exceeded the time limit |
| 500 | `internal_error` | Unexpected failure; response carries a request id |

Every response includes `X-Request-Id`.

## Health (M2)

- `GET /v1/health` returns `200 {"status": "ok"}`. No auth. Liveness only.

## Document generation (M2)

### `POST /v1/documents`

Scope: `documents:create`. Renders one document and returns the bytes directly.

Request:

```json
{
  "template": {"slug": "invoice", "version": 3},
  "data": {"customer": {"name": "Acme"}, "lines": [{"desc": "Consulting", "qty": 10, "price": 120}]},
  "format": "pdf",
  "options": {"filename": "invoice-0042.pdf"}
}
```

`template.version` is optional and defaults to the latest version.

Response `200`:
- `Content-Type: application/pdf`
- `Content-Disposition: inline; filename="invoice-0042.pdf"`
- `X-Template-Version: 3`
- `X-Page-Count: 1`

Errors: 401, 403, 404, 413, 422 (`validation_failed`, `template_error`, `page_limit_exceeded`), 429, 504.

In M2 the only template is seeded by the CLI; the endpoints below arrive in M3.

## Templates (M3)

| Method and path | Purpose | Scope |
|---|---|---|
| `POST /v1/templates` | Create template with version 1 | `templates:write` |
| `GET /v1/templates` | List (summaries, no html/css) | `templates:read` |
| `GET /v1/templates/{slug}` | Template summary and current version number | `templates:read` |
| `PATCH /v1/templates/{slug}` | Rename (name only) | `templates:write` |
| `DELETE /v1/templates/{slug}` | Soft delete | `templates:write` |
| `POST /v1/templates/{slug}/versions` | Publish a new immutable version | `templates:write` |
| `GET /v1/templates/{slug}/versions` | List versions | `templates:read` |
| `GET /v1/templates/{slug}/versions/{n}` | Full version: html, css, schema | `templates:read` |

Create body (`POST /v1/templates`); the new-version body has the same fields minus `slug` and `name`:

```json
{
  "slug": "invoice",
  "name": "Invoice",
  "html": "<html>...{{ customer.name }}...</html>",
  "css": "@page { size: A4; margin: 20mm } ...",
  "variables_schema": {"type": "object", "required": ["customer"], "properties": {}}
}
```

On create and on new version, the template is compiled in the Jinja2 sandbox with strict undefined variables. A compile failure returns 422 `template_error` and nothing is stored. Editing never mutates a version: a new version is created and `current_version` advances.

## Data model changes this contract implies

1. `api_keys.scopes` (text array), included in the M2 migration (already reflected in ADR 0001).
2. Creating the first tenant and key is a CLI command (`create-tenant`) that prints the key once. Key-management endpoints are deferred.

## Decision: template assets

There are no asset endpoints. Templates embed small images as `data:` URIs and fonts are bundled in the image. Immutable versions would make uploads awkward, and nothing in M2 or M3 needs them. The renderer only resolves `data:` URIs; any other URL in a template is blocked. Template `html` plus `css` is capped at 1 MB (413 `payload_too_large`).

## Deferred (not part of this contract yet)

Planned for later milestones and intentionally left out of the current scope:

- **M4, async jobs and batching:** asynchronous submission, job status polling, result download, batch submission with aggregate status, idempotency keys.
- **M5, webhooks:** signed completion callbacks with retries and a delivery history.
- **M6, admin UI:** a Vite app on top of this same API, authenticating with a tenant API key.

These get their own section here (and a follow-up ADR) when their milestone starts.
