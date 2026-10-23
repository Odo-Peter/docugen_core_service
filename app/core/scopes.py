from enum import StrEnum


class ApiKeyScope(StrEnum):
    DOCUMENTS_CREATE = "documents:create"
    TEMPLATES_READ = "templates:read"
    TEMPLATES_WRITE = "templates:write"


# ADR: the public demo key can render and read templates but not author them.
DEMO_KEY_SCOPES: frozenset[ApiKeyScope] = frozenset({ApiKeyScope.DOCUMENTS_CREATE, ApiKeyScope.TEMPLATES_READ})
