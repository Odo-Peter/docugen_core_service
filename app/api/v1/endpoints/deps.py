"""
Auth dependencies. TODO(step 5): implement per ADR 0001 / api-contract.md:

- Parse `Authorization: Bearer dg_<prefix>_<secret>`
- Look up ApiKey by key_prefix, verify sha256(secret) == key_hash
- Reject revoked/unknown keys with 401 (code="unauthorized")
- require_scope(scope) dependency factory: 403 (code="forbidden") if the
  resolved key lacks the scope
- Update last_used_at (best-effort, don't block the request on it)

Every endpoint should depend on get_current_tenant (or require_scope) —
never trust a tenant_id from the request body or URL.
"""

from dataclasses import dataclass

from fastapi import Depends, Header, HTTPException
from collections.abc import Callable


@dataclass
class AuthContext:
    tenant_id: str
    scopes: list[str]


def get_current_tenant(authorization: str = Header(default="")) -> AuthContext:
    raise HTTPException(
        status_code=501,
        detail="auth not implemented yet — see app/api/deps.py TODO (step 5)",
    )


def require_scope(scope: str) -> Callable[..., AuthContext]:
    def _dependency(auth: AuthContext = Depends(get_current_tenant)) -> AuthContext:
        if scope not in auth.scopes:
            raise HTTPException(status_code=403, detail={"code": "forbidden"})
        return auth

    return _dependency
