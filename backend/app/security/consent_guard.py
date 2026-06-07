"""Consent enforcement for data-use endpoints (PDPO DPP1/3, GDPR Art.9, PIPL).

A thin guard that releases a patient's special-category data only when an active,
granted consent record covers the requested purpose (``scope``).

**Config-gated, default OFF** (``settings.consent_enforcement``). When disabled it
is a no-op so the open demo keeps working; the spoken consent gate in
``checkin_agent.py`` still runs on every call regardless. When enabled, a missing
or revoked consent yields HTTP 451 (Unavailable For Legal Reasons), which is
distinct from the 401/403 the auth layer raises.
"""

from __future__ import annotations

from fastapi import HTTPException

from .. import consent_store
from ..config import settings


def enforce(patient_id: int, scope: str = consent_store.BASE_SCOPE) -> None:
    """Raise 451 if consent enforcement is on and ``scope`` is not consented."""
    if not settings.consent_enforcement:
        return
    if not consent_store.consent_allows(patient_id, scope):
        raise HTTPException(
            status_code=451,
            detail=(
                f"No active patient consent for scope '{scope}'. "
                "Record consent before releasing this data."
            ),
        )
