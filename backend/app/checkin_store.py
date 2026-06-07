"""Store for check-ins derived from completed AI check-in calls.

The synthetic daily check-ins live in ``app/data.py``. When an outbound call
completes and ElevenLabs returns its extracted data, ``conversation_store``
materializes it here as a real ``CheckIn`` so it shows up alongside the mock
history in the patient's check-in panel.

Keyed by ``conversation_id`` so it is idempotent: re-fetching the same completed
call updates the same entry instead of creating a duplicate. Persisted to MongoDB
best-effort (like ``app/call_store.py``) so a call-derived check-in survives a
restart; if Mongo is unreachable the entry still holds in memory.
"""

from __future__ import annotations

import logging
from datetime import date
from itertools import count

from .config import settings
from .models import CheckIn, ConversationDetail
from .security import crypto

log = logging.getLogger("careloop.checkin_store")

# Free-text health notes are encrypted at rest when encryption is enabled.
_SENSITIVE = ("notes",)

# conversation_id -> CheckIn derived from that call.
_STORE: dict[str, CheckIn] = {}

# Call-derived check-ins use a high id base so they never collide with the mock
# ids seeded in app/data.py (patient_id * 100 + day, well under this). Public so
# readers (e.g. question_gen) can tell a real call-derived check-in from a seed.
CALL_DERIVED_ID_BASE = 1_000_000
_ID_BASE = CALL_DERIVED_ID_BASE
_ids = count(_ID_BASE)


# --- Building a CheckIn from a completed conversation ------------------------


def _build_notes(detail: ConversationDetail, values: dict[str, object]) -> str:
    """Free-text notes for the check-in: the call summary, else extracted flags."""
    if detail.transcript_summary and detail.transcript_summary.strip():
        return detail.transcript_summary.strip()

    parts: list[str] = []
    symptoms = values.get("new_symptoms")
    if isinstance(symptoms, str) and symptoms.strip() and symptoms.strip().lower() != "none":
        parts.append(f"New symptoms: {symptoms.strip()}")
    if values.get("needs_followup") is True:
        reason = values.get("followup_reason")
        if isinstance(reason, str) and reason.strip():
            parts.append(f"Flagged for follow-up: {reason.strip()}")
        else:
            parts.append("Flagged for follow-up.")
    return " ".join(parts) if parts else "AI check-in call completed."


def _build_checkin(
    detail: ConversationDetail, patient_id: int, when: date, checkin_id: int
) -> CheckIn:
    values = {p.id: p.value for p in detail.data_collection}

    mood = values.get("mood")
    mood = mood.strip() if isinstance(mood, str) and mood.strip() else "-"

    pain = values.get("pain_level")
    pain_level = (
        int(pain) if isinstance(pain, (int, float)) and not isinstance(pain, bool) else 0
    )

    # A "done" call that produced any transcript/data was answered; otherwise fall
    # back to the agent's own success classification.
    answered = bool(detail.transcript) or detail.call_successful == "success"

    return CheckIn(
        id=checkin_id,
        patient_id=patient_id,
        date=when,
        mood=mood,
        pain_level=pain_level,
        answered=answered,
        notes=_build_notes(detail, values),
    )


def record_from_conversation(
    detail: ConversationDetail, patient_id: int, when: date
) -> CheckIn:
    """Upsert the check-in derived from one completed call. Idempotent per call."""
    existing = _STORE.get(detail.conversation_id)
    checkin_id = existing.id if existing is not None else next(_ids)
    checkin = _build_checkin(detail, patient_id, when, checkin_id)
    _STORE[detail.conversation_id] = checkin
    _persist(detail.conversation_id, checkin)
    return checkin


def list_for_patient(patient_id: int) -> list[CheckIn]:
    return [c for c in _STORE.values() if c.patient_id == patient_id]


def merged_recent(patient_id: int, limit: int) -> list[CheckIn]:
    """Recent check-ins for a patient, **real call-derived first** (newest first),
    then the synthetic seed history as backfill - so the voice agent and its context
    reflect the patient's actual prior conversations, not just the mock baseline.

    Mirrors the ordering used in question generation (call-derived ids are monotonic
    from CALL_DERIVED_ID_BASE, so id breaks same-day ties to keep the newest on top).
    """
    from . import data  # late import: data does not import checkin_store

    real = sorted(list_for_patient(patient_id), key=lambda c: (c.date, c.id), reverse=True)
    synthetic = sorted(data.get_checkins(patient_id), key=lambda c: c.date, reverse=True)
    return (real + synthetic)[:limit]


def erase_patient(patient_id: int) -> int:
    """Remove a patient's call-derived check-ins (right to erasure). Returns count."""
    ids = [cid for cid, c in _STORE.items() if c.patient_id == patient_id]
    for cid in ids:
        _STORE.pop(cid, None)
    handle = _collection()
    if handle is not None:
        client, col = handle
        try:
            col.delete_many({"patient_id": patient_id})
        except Exception:  # noqa: BLE001
            pass
        finally:
            client.close()
    return len(ids)


def purge_older_than(cutoff: date) -> int:
    """Retention: drop call-derived check-ins dated before ``cutoff``. Returns count."""
    ids = [cid for cid, c in _STORE.items() if c.date < cutoff]
    for cid in ids:
        _STORE.pop(cid, None)
    handle = _collection()
    if handle is not None:
        client, col = handle
        try:
            col.delete_many({"date": {"$lt": cutoff.isoformat()}})
        except Exception:  # noqa: BLE001
            pass
        finally:
            client.close()
    return len(ids)


# --- MongoDB persistence (best-effort) ---------------------------------------


def _collection():
    """Return (client, collection) for the call-derived check-in store, or None."""
    try:
        from pymongo import MongoClient
    except ImportError:
        return None
    try:
        client = MongoClient(settings.mongodb_uri, serverSelectionTimeoutMS=1500)
        return client, client[settings.mongodb_db][settings.checkins_collection]
    except Exception:
        return None


def _persist(conversation_id: str, checkin: CheckIn) -> None:
    handle = _collection()
    if handle is None:
        log.warning(
            "Check-in for conversation %s not persisted (Mongo unreachable); it "
            "holds in memory until the next restart.",
            conversation_id,
        )
        return
    client, col = handle
    try:
        doc = crypto.encrypt_fields(checkin.model_dump(mode="json"), _SENSITIVE)
        col.update_one({"_id": conversation_id}, {"$set": doc}, upsert=True)
    except Exception:
        log.warning("Check-in for conversation %s not persisted (write failed).", conversation_id)
    finally:
        client.close()


def load_persisted() -> int:
    """Load saved call-derived check-ins into memory and advance the id counter.

    Called once on startup (see app/infra.py). Best-effort: returns 0 if Mongo is
    unreachable or empty.
    """
    global _ids
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
    if not docs:
        return 0
    max_id = _ID_BASE - 1
    for d in docs:
        conversation_id = d.pop("_id")
        d = crypto.decrypt_fields(d, _SENSITIVE)
        checkin = CheckIn.model_validate(d)
        _STORE[conversation_id] = checkin
        max_id = max(max_id, checkin.id)
    _ids = count(max_id + 1)
    return len(docs)
