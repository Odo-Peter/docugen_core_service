"""
Auth dependencies (ADR 0001 / api-contract.md).

Authorization: Bearer dg_<prefix>_<secret>
  - the prefix locates the key row; SHA-256 of the FULL key string is compared to key_hash in constant time
  - a key is valid only if the key AND its tenant are both active
  - the tenant always comes from the key, never from the body or URL

Every endpoint depends on get_current_tenant or require_scope.
"""

import hashlib
import hmac
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from fastapi import Depends, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.core.scopes import ApiKeyScope
from app.core.errors import ApiError, ErrorCode
from app.api.v1.schemas.api_keys import ApiKeyPrefix

from app.models.api_key import ApiKey
from app.models.tenant import Tenant
from app.db import get_db_session

bearer_scheme = HTTPBearer(auto_error=False)
_LAST_USED_THROTTLE = timedelta(minutes=1)


@dataclass(frozen=True)
class AuthContext:
    tenant_id: str
    key_id: str
    scopes: frozenset[ApiKeyScope]


def _unauthorized(
    *,
    detail: str = "Provide a valid API key in the Authorization header.",
    error: str = "invalid_token",
) -> ApiError:
    """401 when the API key is missing, malformed, or revoked."""
    return ApiError(
        status=status.HTTP_401_UNAUTHORIZED,
        code=ErrorCode.UNAUTHORIZED,
        title="Unauthorized",
        detail=detail,
        headers={"WWW-Authenticate": ('Bearer realm="api", ' f'error="{error}", ' f'error_description="{detail}"')},
    )


def get_current_tenant(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    session: Session = Depends(get_db_session),
) -> AuthContext:
    if credentials is None:
        raise _unauthorized()

    raw_key = credentials.credentials
    parts = raw_key.split("_")

    if len(parts) != 3 or parts[0] != ApiKeyPrefix.PREFIX:
        raise _unauthorized()

    key = session.scalars(
        select(ApiKey)
        .join(Tenant, Tenant.id == ApiKey.tenant_id)
        .where(ApiKey.key_prefix == parts[1], ApiKey.is_active.is_(True), Tenant.is_active.is_(True))
    ).first()

    digest = hashlib.sha256(raw_key.encode()).hexdigest()
    if key is None or not hmac.compare_digest(key.key_hash, digest):
        raise _unauthorized()

    # Read everything needed before the commit below expires
    context = AuthContext(
        tenant_id=key.tenant_id,
        key_id=key.id,
        scopes=frozenset(ApiKeyScope(s) for s in key.scopes),
    )

    # Throttled so a busy key doesn't write a row on every request
    now = datetime.now(timezone.utc)

    if key.last_used_at is None or now - key.last_used_at > _LAST_USED_THROTTLE:
        key.last_used_at = now
        session.commit()

    return context


def require_scope(scope: str) -> Callable[..., AuthContext]:
    def _dependency(auth: AuthContext = Depends(get_current_tenant)) -> AuthContext:
        if scope not in auth.scopes:
            raise ApiError(
                status=status.HTTP_403_FORBIDDEN,
                code=ErrorCode.FORBIDDEN,
                title="Missing required scope",
                detail=f"this key does not have the {scope} scope",
            )
        return auth

    return _dependency
