"""Audit log of access to / modification of patient data (PDPO DPP4 / GDPR Art.32).

Records who did what to which patient's data, when. Used by an HTTP middleware
(every request to a patient resource) and by explicit calls in the high-stakes
paths (export, erasure, consent). In-memory ring buffer with best-effort MongoDB
persistence; the free-text ``detail`` is encrypted at rest when encryption is on.
"""

from __future__ import annotations

import logging
import uuid
from collections import deque
from datetime import datetime

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from .config import settings
from .models import AuditEvent
from .security import crypto

log = logging.getLogger("careloop.audit")

# Keep the most recent N events in memory regardless of Mongo availability.
_RING: deque[AuditEvent] = deque(maxlen=5000)
_SENSITIVE = ("detail",)


def _collection():
    try:
        from pymongo import MongoClient
    except ImportError:
        return None
    try:
        client = MongoClient(settings.mongodb_uri, serverSelectionTimeoutMS=1500)
        return client, client[settings.mongodb_db][settings.audit_collection]
    except Exception:
        return None


def _persist(event: AuditEvent) -> None:
    handle = _collection()
    if handle is None:
        return
    client, col = handle
    try:
        doc = crypto.encrypt_fields(event.model_dump(mode="json"), _SENSITIVE)
        doc["_id"] = doc.pop("id")
        col.insert_one(doc)
    except Exception:  # noqa: BLE001
        pass
    finally:
        client.close()


def record(
    actor: str,
    action: str,
    resource_type: str,
    resource_id: str | None = None,
    detail: str | None = None,
) -> AuditEvent:
    """Append one audit event (best-effort persisted)."""
    event = AuditEvent(
        id=str(uuid.uuid4()),
        at=datetime.now(),
        actor=actor,
        action=action,
        resource_type=resource_type,
        resource_id=str(resource_id) if resource_id is not None else None,
        detail=detail,
    )
    _RING.append(event)
    _persist(event)
    return event


def list_events(limit: int = 200, resource_id: str | None = None) -> list[AuditEvent]:
    events = list(_RING)
    if resource_id is not None:
        events = [e for e in events if e.resource_id == str(resource_id)]
    events.sort(key=lambda e: e.at, reverse=True)
    return events[:limit]


def _actor_from_request(request: Request) -> str:
    """Best-effort actor for the audit log from the request's auth headers."""
    if not settings.auth_enabled:
        return "system"
    from .security.auth import _match_token  # local import to avoid a cycle

    auth = request.headers.get("authorization", "")
    presented = auth[7:].strip() if auth.lower().startswith("bearer ") else request.headers.get(
        "x-api-key", ""
    ).strip()
    role = _match_token(presented) if presented else None
    return f"token:{presented[:6]}…" if role else "anonymous"


# Paths whose mutations touch patient data and should be audited.
_AUDITED_PREFIXES = ("/patients", "/integrations", "/fhir", "/admin", "/audit")
_MUTATING = {"POST", "PUT", "PATCH", "DELETE"}


class AuditMiddleware(BaseHTTPMiddleware):
    """Record every mutating request to patient-data routes (DPP4 / Art.32).

    Reads are covered by explicit ``audit.record`` calls in the high-stakes
    endpoints (export); blanket-logging every GET would drown the log, so the
    middleware focuses on writes.
    """

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        path = request.url.path
        if request.method in _MUTATING and path.startswith(_AUDITED_PREFIXES):
            try:
                record(
                    _actor_from_request(request),
                    f"http.{request.method.lower()}",
                    "endpoint",
                    path,
                    detail=f"status={response.status_code}",
                )
            except Exception:  # noqa: BLE001 - auditing must never break a response
                pass
        return response


def purge_older_than(cutoff: datetime) -> int:
    """Retention: drop events older than ``cutoff``. Returns count removed."""
    keep = [e for e in _RING if e.at >= cutoff]
    removed = len(_RING) - len(keep)
    _RING.clear()
    _RING.extend(keep)
    handle = _collection()
    if handle is not None:
        client, col = handle
        try:
            col.delete_many({"at": {"$lt": cutoff.isoformat()}})
        except Exception:  # noqa: BLE001
            pass
        finally:
            client.close()
    return removed
