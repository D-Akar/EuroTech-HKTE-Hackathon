"""In-memory store for call configs, schedules, and call history.

Mirrors the mock-data style of ``app/data.py`` — module-level structures seeded
at import time. Resets on every restart. Replace with a real datastore later.
"""

from __future__ import annotations

from itertools import count

from .models import CallConfig, CallRecord, ScheduledCall

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


def set_config(patient_id: int, questions: list[str], greeting: str | None) -> CallConfig:
    config = CallConfig(patient_id=patient_id, questions=questions, greeting=greeting)
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


def add_call_record(record: CallRecord) -> CallRecord:
    CALL_HISTORY.insert(0, record)  # most-recent first
    return record


def next_record_id() -> int:
    return next(_record_ids)


def list_call_records(patient_id: int) -> list[CallRecord]:
    return [r for r in CALL_HISTORY if r.patient_id == patient_id]
