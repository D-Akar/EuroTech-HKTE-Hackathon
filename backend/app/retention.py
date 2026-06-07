"""Data-retention engine (PDPO DPP2 / GDPR Art.5(1)(e) storage limitation).

Each data class has a retention period (days) configured in app/config.py; data
older than that is purged. A purge runs on a daily APScheduler job (registered in
app/scheduler.py) and can be triggered on demand via the admin endpoint.

A retention of ``0`` means "keep indefinitely" (the default), so retention is a
no-op until a practice configures real limits — which keeps the demo unchanged.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta

from . import audit, call_store, checkin_store, consent_store
from .config import settings

log = logging.getLogger("careloop.retention")


def run() -> dict[str, int]:
    """Purge expired data across all stores. Returns {class: count_removed}."""
    now = datetime.now()
    today = date.today()
    removed: dict[str, int] = {}

    if settings.retention_checkins_days > 0:
        cutoff = today - timedelta(days=settings.retention_checkins_days)
        removed["checkins"] = checkin_store.purge_older_than(cutoff)

    if settings.retention_calls_days > 0:
        cutoff_dt = now - timedelta(days=settings.retention_calls_days)
        removed["calls"] = call_store.purge_older_than(cutoff_dt)

    if settings.retention_audit_days > 0:
        cutoff_dt = now - timedelta(days=settings.retention_audit_days)
        removed["audit"] = audit.purge_older_than(cutoff_dt)

    if settings.retention_consent_days > 0:
        cutoff_dt = now - timedelta(days=settings.retention_consent_days)
        removed["consent"] = consent_store.purge_older_than(cutoff_dt)

    total = sum(removed.values())
    if total:
        log.info("Retention purge removed %d record(s): %s", total, removed)
    return removed
