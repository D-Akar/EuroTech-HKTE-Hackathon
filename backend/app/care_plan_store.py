"""Store for uploaded patient care plans.

Behind a small functional interface (get/set/delete). Plans are held in memory and
persisted to MongoDB best-effort (like app/patient_overrides.py) so an uploaded
care plan survives a backend restart; if Mongo is unreachable the upload still
takes effect in memory.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from .config import settings
from .fhir_careplan import extract_care_plan, locate_care_plan, parse_document
from .models import CarePlanContext, StoredCarePlan
from .security import crypto

log = logging.getLogger("careloop.care_plan_store")

# The original uploaded clinical document is encrypted at rest when enabled.
_SENSITIVE = ("raw",)

# patient_id -> latest uploaded plan
_STORE: dict[int, StoredCarePlan] = {}


def _collection():
    """Return (client, collection) for the care-plan store, or None."""
    try:
        from pymongo import MongoClient
    except ImportError:
        return None
    try:
        client = MongoClient(settings.mongodb_uri, serverSelectionTimeoutMS=1500)
        return client, client[settings.mongodb_db][settings.care_plans_collection]
    except Exception:
        return None


def _persist(patient_id: int, stored: StoredCarePlan) -> None:
    handle = _collection()
    if handle is None:
        log.warning(
            "Care plan for patient %s not persisted (Mongo unreachable); it holds "
            "in memory until the next restart.",
            patient_id,
        )
        return
    client, col = handle
    try:
        doc = crypto.encrypt_fields(stored.model_dump(mode="json"), _SENSITIVE)
        col.update_one({"_id": patient_id}, {"$set": doc}, upsert=True)
    except Exception:
        log.warning("Care plan for patient %s not persisted (Mongo write failed).", patient_id)
    finally:
        client.close()


def _delete_persisted(patient_id: int) -> None:
    handle = _collection()
    if handle is None:
        return
    client, col = handle
    try:
        col.delete_one({"_id": patient_id})
    except Exception:
        pass
    finally:
        client.close()


def load_persisted() -> int:
    """Load saved care plans into memory. Called once on startup (app/infra.py).

    Best-effort: returns 0 if Mongo is unreachable or empty.
    """
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
    for d in docs:
        patient_id = d.pop("_id")
        d = crypto.decrypt_fields(d, _SENSITIVE)
        _STORE[patient_id] = StoredCarePlan.model_validate(d)
    return len(docs)


def parse_care_plan(raw: str) -> CarePlanContext:
    """Parse raw JSON/XML/text into a CarePlanContext (no storage)."""
    resource = parse_document(raw)
    care_plan, refs = locate_care_plan(resource)
    return extract_care_plan(care_plan, refs)


def get(patient_id: int) -> StoredCarePlan | None:
    return _STORE.get(patient_id)


def set(patient_id: int, raw: str, ctx: CarePlanContext) -> StoredCarePlan:
    stored = StoredCarePlan(care_plan=ctx, raw=raw, uploaded_at=datetime.now(timezone.utc))
    _STORE[patient_id] = stored
    _persist(patient_id, stored)
    return stored


def delete(patient_id: int) -> bool:
    removed = _STORE.pop(patient_id, None) is not None
    if removed:
        _delete_persisted(patient_id)
    return removed
