"""Authentication + Role-Based Access Control (PDPO DPP4 / GDPR Art.32).

Protected endpoints depend on :func:`require_role`. A caller presents a bearer
token (``Authorization: Bearer <token>``) or ``X-API-Key`` header, which is mapped
to a role via ``CARELOOP_AUTH_TOKENS``.

**Config-gated, default OFF.** When ``settings.auth_enabled`` is false, every
request resolves to a synthetic ``system``/``admin`` principal so the open demo and
the existing frontend keep working untouched. Turn it on in backend/.env and the
same dependencies become real, enforced access control.

Roles (least privilege):
- ``coordinator`` - operational dashboard / triage.
- ``clinician``  - coordinator + clinical detail, data export.
- ``admin``      - everything, incl. erasure, audit log, retention.
"""

from __future__ import annotations

import hmac
from dataclasses import dataclass

from fastapi import Depends, Header, HTTPException, status

from ..config import settings

# Role hierarchy: a role implicitly satisfies the roles ranked at or below it.
_RANK = {"coordinator": 1, "clinician": 2, "admin": 3}


@dataclass(frozen=True)
class Principal:
    """The authenticated caller."""

    subject: str
    role: str

    def has_role(self, required: str) -> bool:
        return _RANK.get(self.role, 0) >= _RANK.get(required, 99)


# Principal used when auth is disabled, so unprotected demo runs keep working.
_SYSTEM = Principal(subject="system", role="admin")


def _match_token(presented: str) -> str | None:
    """Constant-time lookup of a presented token -> role, or None."""
    for token, role in settings.auth_tokens.items():
        if hmac.compare_digest(presented, token):
            return role
    return None


def get_principal(
    authorization: str = Header(default=""),
    x_api_key: str = Header(default=""),
) -> Principal:
    """Resolve the calling principal from the request headers."""
    if not settings.auth_enabled:
        return _SYSTEM

    presented = ""
    if authorization.lower().startswith("bearer "):
        presented = authorization[7:].strip()
    elif x_api_key:
        presented = x_api_key.strip()

    if not presented:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    role = _match_token(presented)
    if role is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    return Principal(subject=f"token:{presented[:6]}…", role=role)


def require_role(minimum: str):
    """Dependency factory: require at least ``minimum`` role (respects hierarchy)."""

    def _dep(principal: Principal = Depends(get_principal)) -> Principal:
        if not principal.has_role(minimum):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires '{minimum}' role or higher",
            )
        return principal

    return _dep
