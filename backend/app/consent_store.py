"""Consent records (PDPO DPP1/3, GDPR Art.9 explicit consent, PIPL sensitive PI).

A durable, append-only log of each patient's consent decisions, stamped with the
privacy-policy version they agreed to. The voice consent gate (app/checkin_agent.py)
is the capture mechanism for ``method="voice"``; the caregiver portal records
``method="portal"``.

In-memory list with best-effort MongoDB persistence (mirrors app/call_store.py).
The free-text ``note`` is encrypted at rest when encryption is enabled.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime

from .config import settings
from .models import ConsentRecord
from .security import crypto

log = logging.getLogger("careloop.consent_store")

_RECORDS: list[ConsentRecord] = []
_SENSITIVE = ("note",)


def _collection():
    try:
        from pymongo import MongoClient
    except ImportError:
        return None
    try:
        client = MongoClient(settings.mongodb_uri, serverSelectionTimeoutMS=1500)
        return client, client[settings.mongodb_db][settings.consent_collection]
    except Exception:
        return None


def _persist(record: ConsentRecord) -> None:
    handle = _collection()
    if handle is None:
        log.warning("Consent %s not persisted (Mongo unreachable); holds in memory.", record.id)
        return
    client, col = handle
    try:
        doc = crypto.encrypt_fields(record.model_dump(mode="json"), _SENSITIVE)
        doc["_id"] = doc.pop("id")
        col.update_one({"_id": record.id}, {"$set": doc}, upsert=True)
    except Exception:
        log.warning("Consent %s not persisted (write failed).", record.id)
    finally:
        client.close()


def record(
    patient_id: int,
    granted: bool,
    *,
    scope: str = "care_provision",
    method: str = "portal",
    actor: str = "patient",
    note: str | None = None,
) -> ConsentRecord:
    """Append a consent decision and persist it (best-effort)."""
    rec = ConsentRecord(
        id=str(uuid.uuid4()),
        patient_id=patient_id,
        granted=granted,
        scope=scope,
        method=method,
        policy_version=settings.privacy_policy_version,
        recorded_at=datetime.now(),
        actor=actor,
        note=note,
    )
    _RECORDS.append(rec)
    _persist(rec)
    return rec


def list_for_patient(patient_id: int) -> list[ConsentRecord]:
    return sorted(
        (r for r in _RECORDS if r.patient_id == patient_id),
        key=lambda r: r.recorded_at,
        reverse=True,
    )


def latest_for(patient_id: int) -> ConsentRecord | None:
    records = list_for_patient(patient_id)
    return records[0] if records else None


def has_active_consent(patient_id: int) -> bool:
    latest = latest_for(patient_id)
    return bool(latest and latest.granted)


# The base scope every care-delivery use is covered by. A grant for this scope
# authorises using the patient's data to provide and coordinate their care;
# narrower/secondary scopes (e.g. "research") must be granted on their own.
BASE_SCOPE = "care_provision"


def consent_allows(patient_id: int, scope: str = BASE_SCOPE) -> bool:
    """True if the patient has a current, granted consent covering ``scope``.

    Uses the most recent decision **per scope** (a later revocation wins). A grant
    for the base ``care_provision`` scope also covers it; any other scope needs its
    own grant.
    """
    records = list_for_patient(patient_id)  # most-recent first
    for r in records:
        if r.scope == scope:
            return r.granted
    return False


def load_persisted() -> int:
    handle = _collection()
    if handle is None:
        return 0
    client, col = handle
    try:
        docs = list(col.find({}))
    except Exception:
        client.close()
        return 0
    client.close()
    loaded = 0
    for d in docs:
        d = crypto.decrypt_fields(d, _SENSITIVE)
        d["id"] = d.pop("_id")
        try:
            _RECORDS.append(ConsentRecord.model_validate(d))
            loaded += 1
        except Exception:  # noqa: BLE001
            continue
    return loaded


def erase_patient(patient_id: int) -> int:
    """Remove a patient's consent records (right to erasure). Returns count removed."""
    before = len(_RECORDS)
    _RECORDS[:] = [r for r in _RECORDS if r.patient_id != patient_id]
    handle = _collection()
    if handle is not None:
        client, col = handle
        try:
            col.delete_many({"patient_id": patient_id})
        except Exception:  # noqa: BLE001
            pass
        finally:
            client.close()
    return before - len(_RECORDS)


def purge_older_than(cutoff: datetime) -> int:
    """Retention: drop records older than ``cutoff``. Returns count removed."""
    before = len(_RECORDS)
    _RECORDS[:] = [r for r in _RECORDS if r.recorded_at >= cutoff]
    handle = _collection()
    if handle is not None:
        client, col = handle
        try:
            col.delete_many({"recorded_at": {"$lt": cutoff.isoformat()}})
        except Exception:  # noqa: BLE001
            pass
        finally:
            client.close()
    return before - len(_RECORDS)
