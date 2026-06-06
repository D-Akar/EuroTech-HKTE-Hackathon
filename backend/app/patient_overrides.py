"""Persist dashboard-edited patient phone numbers in MongoDB.

A practice can edit a patient's check-in number from the dashboard. The new number
is written to a small Mongo collection (``PHONE_OVERRIDES_COLLECTION``) keyed by the
dashboard patient slot id, and re-applied onto the live ``Patient`` objects on every
backend startup — *after* the FHIR overlay (see ``app/infra.py``) — so an edited
number survives restarts and FHIR re-overlays and is used by both 'Call now' and
scheduled calls (which read ``patient.phone_number``).

All Mongo access is best-effort, matching ``app/fhir_source.py``: if the database is
unreachable the in-memory edit still takes effect — it just won't survive a restart.
"""

from __future__ import annotations

import logging

from . import data
from .config import settings
from .models import Patient

log = logging.getLogger("careloop.patient_overrides")


def read_overrides() -> dict[int, str]:
    """All saved overrides, keyed by patient slot id. ``{}`` if Mongo is unreachable."""
    try:
        from pymongo import MongoClient
        from pymongo.errors import PyMongoError
    except ImportError:
        return {}
    try:
        client = MongoClient(settings.mongodb_uri, serverSelectionTimeoutMS=1500)
        col = client[settings.mongodb_db][settings.phone_overrides_collection]
        out = {
            d["_id"]: d["phone_number"]
            for d in col.find({}, {"phone_number": 1})
            if d.get("phone_number")
        }
        client.close()
        return out
    except PyMongoError:
        return {}
    except Exception:
        return {}


def _persist(patient_id: int, phone_number: str) -> bool:
    """Upsert one override. ``True`` on success, ``False`` if Mongo is unreachable."""
    try:
        from pymongo import MongoClient
        from pymongo.errors import PyMongoError
    except ImportError:
        return False
    try:
        client = MongoClient(settings.mongodb_uri, serverSelectionTimeoutMS=1500)
        col = client[settings.mongodb_db][settings.phone_overrides_collection]
        col.update_one(
            {"_id": patient_id},
            {"$set": {"phone_number": phone_number}},
            upsert=True,
        )
        client.close()
        return True
    except PyMongoError:
        return False
    except Exception:
        return False


def set_phone(patient_id: int, phone_number: str) -> str:
    """Normalize, persist (best-effort), and return the cleaned E.164 number.

    Raises ``ValueError`` if the number normalizes to empty.
    """
    cleaned = data._normalize_phone(phone_number)
    if not cleaned:
        raise ValueError("Empty or invalid phone number")
    if not _persist(patient_id, cleaned):
        log.warning(
            "Phone override for patient %s not persisted (Mongo unreachable); "
            "the change holds in memory until the next restart.",
            patient_id,
        )
    return cleaned


def apply(patients: list[Patient]) -> int:
    """Overlay saved overrides onto ``patients`` in place. Returns the count applied."""
    overrides = read_overrides()
    if not overrides:
        return 0
    applied = 0
    for p in patients:
        num = overrides.get(p.id)
        if num:
            p.phone_number = num
            applied += 1
    return applied
