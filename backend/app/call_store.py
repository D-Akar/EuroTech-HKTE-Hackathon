"""In-memory store for call configs, schedules, and call history.

Mirrors the mock-data style of ``app/data.py`` — module-level structures seeded
at import time. Configs and schedules are memory-only; the call *history* is
additionally persisted to MongoDB (best-effort, like ``app/patient_overrides.py``)
so the calls shown under a patient's check-in data survive a backend restart.
"""

from __future__ import annotations

import logging
from itertools import count

from .config import settings
from .models import CallConfig, CallRecord, ScheduledCall

log = logging.getLogger("careloop.call_store")

# Default questions every patient starts with; the practice can edit these.
_DEFAULT_QUESTIONS: list[str] = [
    "How are you feeling today compared to yesterday?",
    "Have you taken your medication as prescribed?",
    "Are you experiencing any new pain or discomfort?",
    "How well did you sleep last night?",
]

# patient_id -> CallConfig
CALL_CONFIGS: dict[int, CallConfig] = {}
SCHEDULES: list[ScheduledCall] = []
CALL_HISTORY: list[CallRecord] = []

_schedule_ids = count(1)
_record_ids = count(1)


# --- Config ------------------------------------------------------------------


def get_config(patient_id: int) -> CallConfig:
    """Return the patient's config, creating a default one on first access."""
    config = CALL_CONFIGS.get(patient_id)
    if config is None:
        config = CallConfig(patient_id=patient_id, questions=list(_DEFAULT_QUESTIONS))
        CALL_CONFIGS[patient_id] = config
    return config


def set_config(
    patient_id: int,
    questions: list[str],
    greeting: str | None,
    system_prompt: str | None = None,
) -> CallConfig:
    config = CallConfig(
        patient_id=patient_id,
        questions=questions,
        greeting=greeting,
        system_prompt=system_prompt,
    )
    CALL_CONFIGS[patient_id] = config
    return config


# --- Schedules ---------------------------------------------------------------


def add_schedule(
    patient_id: int, scheduled_at, recurring: bool, questions: list[str]
) -> ScheduledCall:
    schedule = ScheduledCall(
        id=next(_schedule_ids),
        patient_id=patient_id,
        scheduled_at=scheduled_at,
        recurring=recurring,
        status="pending",
        questions=questions,
    )
    SCHEDULES.append(schedule)
    return schedule


def list_schedules(patient_id: int) -> list[ScheduledCall]:
    return [
        s for s in SCHEDULES if s.patient_id == patient_id and s.status == "pending"
    ]


def get_schedule(schedule_id: int) -> ScheduledCall | None:
    return next((s for s in SCHEDULES if s.id == schedule_id), None)


def cancel_schedule(schedule_id: int) -> ScheduledCall | None:
    schedule = get_schedule(schedule_id)
    if schedule is not None:
        schedule.status = "cancelled"
    return schedule


# --- Call history ------------------------------------------------------------
#
# Persisted to MongoDB best-effort: if the database is unreachable the record
# still lands in memory — it just won't survive a restart. Mirrors the pattern in
# app/patient_overrides.py.


def _history_collection():
    """Return (client, collection) for the call-history store, or None."""
    try:
        from pymongo import MongoClient
    except ImportError:
        return None
    try:
        client = MongoClient(settings.mongodb_uri, serverSelectionTimeoutMS=1500)
        return client, client[settings.mongodb_db][settings.call_history_collection]
    except Exception:
        return None


def _persist_record(record: CallRecord) -> None:
    handle = _history_collection()
    if handle is None:
        log.warning(
            "Call record %s not persisted (Mongo unreachable); it holds in memory "
            "until the next restart.",
            record.id,
        )
        return
    client, col = handle
    try:
        col.update_one(
            {"_id": record.id},
            {"$set": record.model_dump(mode="json")},
            upsert=True,
        )
    except Exception:
        log.warning("Call record %s not persisted (Mongo write failed).", record.id)
    finally:
        client.close()


def load_persisted() -> int:
    """Load saved call records into memory and advance the id counter.

    Called once on startup (see app/infra.py). Best-effort: returns 0 if Mongo is
    unreachable or empty.
    """
    global _record_ids
    handle = _history_collection()
    if handle is None:
        return 0
    client, col = handle
    try:
        docs = list(col.find({}))
    except Exception:
        client.close()
        return 0
    client.close()
    if not docs:
        return 0
    records = [CallRecord.model_validate(d) for d in docs]
    records.sort(key=lambda r: r.triggered_at, reverse=True)  # most-recent first
    CALL_HISTORY[:] = records
    _record_ids = count(max(r.id for r in records) + 1)
    return len(records)


def add_call_record(record: CallRecord) -> CallRecord:
    CALL_HISTORY.insert(0, record)  # most-recent first
    _persist_record(record)
    return record


def next_record_id() -> int:
    return next(_record_ids)


def list_call_records(patient_id: int) -> list[CallRecord]:
    return [r for r in CALL_HISTORY if r.patient_id == patient_id]


def get_call_record(patient_id: int, call_id: int) -> CallRecord | None:
    return next(
        (r for r in CALL_HISTORY if r.id == call_id and r.patient_id == patient_id),
        None,
    )
