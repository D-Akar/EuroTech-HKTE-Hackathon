"""Durable right-to-erasure tombstones (GDPR Art.17 / PDPO DPP datasubject).

The erasure endpoint deletes a patient's *derived* data from every store, but the
patient's identity + medical **profile** are overlaid at startup from the read-only
FHIR source (`app/fhir_source.py`). Redacting the in-memory roster slot alone is not
durable: the next restart re-applies the overlay and the name/profile reappear.

This store records which patient slots have been erased, so the overlay can keep
them redacted across restarts. In-memory set with best-effort MongoDB persistence
(mirrors the other stores). A tombstone can be lifted with :func:`restore` (e.g. if
the same slot is later reassigned to a new, consenting patient).
"""

from __future__ import annotations

import logging
from datetime import datetime

from .config import settings

log = logging.getLogger("careloop.erasure_store")

_ERASED: set[int] = set()


def _collection():
    try:
        from pymongo import MongoClient
    except ImportError:
        return None
    try:
        client = MongoClient(settings.mongodb_uri, serverSelectionTimeoutMS=1500)
        return client, client[settings.mongodb_db][settings.erasure_collection]
    except Exception:
        return None


def record(patient_id: int) -> None:
    """Tombstone a patient slot as erased (idempotent), persisted best-effort."""
    _ERASED.add(patient_id)
    handle = _collection()
    if handle is None:
        log.warning(
            "Erasure tombstone for patient %s not persisted (Mongo unreachable); "
            "holds in memory until restart.", patient_id,
        )
        return
    client, col = handle
    try:
        col.update_one(
            {"_id": patient_id},
            {"$set": {"_id": patient_id, "erased_at": datetime.now().isoformat()}},
            upsert=True,
        )
    except Exception:  # noqa: BLE001
        log.warning("Erasure tombstone for patient %s not persisted (write failed).", patient_id)
    finally:
        client.close()


def restore(patient_id: int) -> bool:
    """Lift a tombstone (un-erase a slot). Returns True if one existed."""
    existed = patient_id in _ERASED
    _ERASED.discard(patient_id)
    handle = _collection()
    if handle is not None:
        client, col = handle
        try:
            col.delete_one({"_id": patient_id})
        except Exception:  # noqa: BLE001
            pass
        finally:
            client.close()
    return existed


def is_erased(patient_id: int) -> bool:
    return patient_id in _ERASED


def active() -> set[int]:
    """The current set of erased patient slot ids."""
    return set(_ERASED)


def load_persisted() -> int:
    """Load tombstones from Mongo into memory. Call before applying FHIR overlays."""
    handle = _collection()
    if handle is None:
        return 0
    client, col = handle
    try:
        ids = [d["_id"] for d in col.find({}, {"_id": 1})]
    except Exception:  # noqa: BLE001
        client.close()
        return 0
    client.close()
    _ERASED.update(int(i) for i in ids)
    return len(ids)
