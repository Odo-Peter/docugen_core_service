# API contract (v1)

Companion to ADR 0001. This fixes the public shape of the API. Pydantic models are written to match it, and the generated `openapi.json` is committed and diffed in CI so the contract cannot drift silently.

**Scope:** milestones 2 (synchronous generation) and 3 (template management). Jobs, batching, and webhooks are deferred; see the last section. The [implementation status](#implementation-status) table at the end shows what is enforced today versus specified here.

## Conventions

- **Base path:** `/v1`. JSON everywhere except the PDF response of the generation endpoint.
- **Auth:** `Authorization: Bearer <api_key>`. Keys look like `dg_<prefix>_<secret>` where prefix and secret are hex. The prefix is used for lookup and the full key string is hashed. The tenant is derived from the key, so tenant ids never appear in URLs. A key works only while the key and its tenant are both active.
- **Scopes:** each key carries scopes: `documents:create`, `templates:read`, `templates:write`. A missing scope returns 403. The public demo key gets `documents:create` and `templates:read`.
- **IDs:** prefixed ULID strings, e.g. `tnt_01JABCDEFGHJKMNPQRSTVWXYZ0`. The prefix identifies the resource type and the ULID part is time-sortable.

  | Resource         | Prefix |
  | ---------------- | ------ |
  | Tenant           | `tnt_` |
  | API key          | `key_` |
  | Template         | `tpl_` |
  | Template version | `ver_` |

- **Timestamps:** ISO 8601 UTC.
- **Template slugs:** lowercase `a-z0-9-`, 3 to 64 characters, unique per tenant among active templates.
- **Deactivation:** resources are deactivated, not deleted. A deactivated or other-tenant resource is indistinguishable from a missing one (404). A deactivated template's slug can be reused.
- **Pagination:** cursor based. `?limit=50&cursor=...` returns `{"data": [...], "next_cursor": "..." | null}`. Max limit 100.
- **Formats:** the `format` field defaults to `"pdf"` and currently accepts only `"pdf"`. It exists from day one so DOCX is additive later.
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
  "errors": [{ "path": "data.customer.name", "message": "is required" }]
}
```

| Status | `code`                | When                                                                                                             |
| ------ | --------------------- | ---------------------------------------------------------------------------------------------------------------- |
| 401    | `unauthorized`        | Missing or malformed key, unknown or deactivated key, or deactivated tenant. All cases return the same response. |
| 403    | `forbidden`           | Key lacks the required scope                                                                                     |
| 404    | `not_found`           | Unknown or deactivated template or version, or another tenant's resource                                         |
| 409    | `conflict`            | Slug already used by an active template, or a version number collision after retry                               |
| 413    | `payload_too_large`   | Body over the size limit                                                                                         |
| 422    | `validation_failed`   | Bad request body, or `data` fails the template's JSON Schema                                                     |
| 422    | `template_error`      | Template fails to compile or render (strict undefined variables, sandbox violation)                              |
| 422    | `page_limit_exceeded` | Document would exceed the page cap                                                                               |
| 429    | `rate_limited`        | Per-key limit hit; `Retry-After` header set                                                                      |
| 504    | `render_timeout`      | Render exceeded the time limit                                                                                   |
| 500    | `internal_error`      | Unexpected failure; response carries a request id                                                                |

The 401 response also carries `WWW-Authenticate: Bearer`. Every response includes `X-Request-Id`.

## Health (M2)

- `GET /v1/health` returns `200 {"status": "ok"}`. No auth. Liveness only.

## Document generation (M2)

### `POST /v1/documents`

Scope: `documents:create`. Renders one document and returns the bytes directly.

Request:

```json
{
  "template": { "slug": "invoice", "version": 3 },
  "data": {
    "customer": { "name": "Acme" },
    "lines": [{ "desc": "Consulting", "qty": 10, "price": 120 }]
  },
  "format": "pdf",
  "options": { "filename": "invoice-0042.pdf" }
}
```

| Field              | Rules                                                                                       |
| ------------------ | ------------------------------------------------------------------------------------------- |
| `template.slug`    | Required. Matches the slug format.                                                          |
| `template.version` | Optional integer >= 1. Defaults to the latest version: the highest-numbered active version. |
| `data`             | Required object. Validated against the template version's `variables_schema`.               |
| `format`           | Optional. Only `"pdf"` is accepted.                                                         |
| `options.filename` | Optional. `[A-Za-z0-9._-]`, 1 to 100 characters. Defaults to `<slug>.pdf`.                  |

Response `200`:

- `Content-Type: application/pdf`
- `Content-Disposition: inline; filename="invoice-0042.pdf"`
- `X-Template-Version: 3`
- `X-Page-Count: 1`

Errors: 401, 403, 404, 413, 422 (`validation_failed`, `template_error`, `page_limit_exceeded`), 429, 504.

Until the template endpoints below exist, templates are created by the dev seed script.

## Templates (M3, not yet implemented)

| Method and path                         | Purpose                                        | Scope             |
| --------------------------------------- | ---------------------------------------------- | ----------------- |
| `POST /v1/templates`                    | Create template with version 1                 | `templates:write` |
| `GET /v1/templates`                     | List active templates (summaries, no html/css) | `templates:read`  |
| `GET /v1/templates/{slug}`              | Template summary and current version number    | `templates:read`  |
| `PATCH /v1/templates/{slug}`            | Rename (name only)                             | `templates:write` |
| `DELETE /v1/templates/{slug}`           | Deactivate (soft delete)                       | `templates:write` |
| `POST /v1/templates/{slug}/versions`    | Publish a new immutable version                | `templates:write` |
| `GET /v1/templates/{slug}/versions`     | List versions                                  | `templates:read`  |
| `GET /v1/templates/{slug}/versions/{n}` | Full version: html, css, schema                | `templates:read`  |

Create body (`POST /v1/templates`); the new-version body has the same fields minus `slug` and `name`:

```json
{
  "slug": "invoice",
  "name": "Invoice",
  "html": "<html>...{{ customer.name }}...</html>",
  "css": "@page { size: A4; margin: 20mm } ...",
  "variables_schema": {
    "type": "object",
    "required": ["customer"],
    "properties": {}
  }
}
```

Behaviour:

- On create and on new version, `variables_schema` is checked as a valid JSON Schema and the template is compiled in the Jinja2 sandbox with strict undefined variables. Either failure returns 422 (`validation_failed` for the schema, `template_error` for the template) and nothing is stored.
- Editing never mutates a version: a new version is created. Version numbers start at 1 and are never reused.
- `current_version` in the summary is derived: the highest-numbered active version.
- Concurrent publishes to the same template can collide on the version number; the loser is retried once and then returns 409.
- `DELETE` deactivates the template. Its slug can then be reused; reactivation, if ever exposed, returns 409 when the slug is taken.

## Data model changes this contract implies

1. `api_keys.scopes` is a text array holding the scope strings above.
2. Every table carries `is_active` and `deactivated_at` from the shared base, which replace per-table `deleted_at` and `revoked_at` columns.
3. Tenants and the first key are created by a script that prints the key once. Key-management endpoints are deferred.

## Decision: template assets

There are no asset endpoints. Templates embed small images as `data:` URIs and fonts are bundled in the image. Immutable versions would make uploads awkward, and nothing in M2 or M3 needs them. The renderer only resolves `data:` URIs; any other URL in a template is blocked. Template `html` plus `css` is capped at 1 MB (413 `payload_too_large`).

## Implementation status

Last updated 2026-10-24.

| Item                                                                               | Status                                         |
| ---------------------------------------------------------------------------------- | ---------------------------------------------- |
| `GET /v1/health`                                                                   | Implemented                                    |
| `POST /v1/documents` (lookup, schema validation, render, headers)                  | Implemented, end-to-end run to be verified     |
| API key auth, scopes, tenant-active check (401/403)                                | Implemented                                    |
| `ApiError` as problem+json                                                         | Implemented                                    |
| FastAPI's own request-validation errors mapped to `validation_failed` problem+json | Implemented                                    |
| `ErrorCode` string values equal the codes in this document                         | Implemented                                    |
| `X-Request-Id` on every response                                                   | Implemented                                    |
| 413 body size limit                                                                | Pending                                        |
| 429 per-key rate limit                                                             | Pending                                        |
| 422 `page_limit_exceeded`                                                          | Mapped; limit value pending the benchmark      |
| 504 `render_timeout`                                                               | Pending; needs subprocess rendering (ADR 0001) |
| Template endpoints                                                                 | Not started (M3)                               |
| `openapi.json` committed and diffed in CI                                          | Pending                                        |

## Deferred (not part of this contract yet)

Planned for later milestones and intentionally left out of the current scope:

- **M4, async jobs and batching:** asynchronous submission, job status polling, result download, batch submission with aggregate status, idempotency keys.
- **M5, webhooks:** signed completion callbacks with retries and a delivery history.
- **M6, admin UI:** a Vite app on top of this same API, authenticating with a tenant API key.

These get their own section here (and a follow-up ADR) when their milestone starts.
