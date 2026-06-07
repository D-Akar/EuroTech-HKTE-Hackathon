"""Auto-escalation driven by live wearable vitals.

The dashboard polls ``GET /patients/{id}/live`` every few seconds. When the
featured patient's live vitals cross into the urgent band - e.g. heart rate over
the urgent threshold during exertion, or blood oxygen below the critical line -
we don't wait for a clinician to notice. The moment a reading is out of range we:

1. Flip the patient to ``urgent`` on the map, pushed live to every dashboard
   over SSE (the marker turns red with no refresh).
2. Place an ElevenLabs emergency call to the patient automatically.
3. If the patient does not answer that call, route the emergency to the on-call
   nurse (``NURSE_PHONE_NUMBER``).

The vitals trigger fires **once per episode**: a per-patient latch is cleared
after the call goes out and only re-armed once the patient's vitals return to a
normal range, so one workout doesn't redial them on every poll.

``emergency_call`` is the shared entry point used by both the backend Garmin
``/live`` path and the frontend BLE/demo path (via ``POST .../calls/emergency``),
so no-answer-routes-to-nurse behaves identically however the call was triggered.
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime

from . import call_store, data, events
from .config import settings
from .models import CallRecord, Patient, PatientStatus
from .services import telephony

log = logging.getLogger(__name__)

# How long to let the patient's phone ring before we conclude they did not answer
# and route the emergency to the nurse. Tunable; kept short for a live demo (a
# rejected/ignored call routes to the nurse this many seconds later).
NO_ANSWER_SECS = 20.0

# A patient call shorter than this (and with no spoken turns) reads as "not picked
# up" - a connected check-in runs far longer than a few seconds of ringing.
_ANSWERED_MIN_SECS = 8

# Per-patient latch. True = ready to fire on the next urgent reading. Set False
# after a call is placed; re-armed when the live status returns to non-urgent.
_armed: dict[int, bool] = {}

# Minimum gap between emergency escalations for the same patient. One episode
# (patient call + nurse fallback) resolves well within this window, so a fresh
# trigger - a watch HR bouncing across the urgent line, a second dashboard tab, a
# page reload - cannot spam the patient and nurse with back-to-back calls. This is
# the source-agnostic backstop: the /live path also has the _armed latch, but the
# frontend BLE/demo path reaches emergency_call directly with no other guard.
_EMERGENCY_COOLDOWN_SECS = 180.0

# patient_id -> monotonic time the last emergency escalation was placed.
_last_emergency: dict[int, float] = {}


def reset() -> None:
    """Clear all latches (used by tests for isolation)."""
    _armed.clear()
    _last_emergency.clear()


async def maybe_autocall(patient_id: int, assessment: dict) -> CallRecord | None:
    """Auto-flip to urgent and emergency-call the patient when vitals are out of range.

    Idempotent across the polling loop: returns the placed ``CallRecord`` the
    first time the patient crosses into urgent, then ``None`` on every subsequent
    poll until they recover and cross again.
    """
    if assessment.get("status") != "urgent":
        _armed[patient_id] = True  # recovered (or never urgent) -> re-arm
        return None

    if not _armed.get(patient_id, True):
        return None  # already escalated this episode; stay quiet
    _armed[patient_id] = False

    patient = data.get_patient(patient_id)
    if patient is None:
        return None

    alerts = assessment.get("alerts", [])
    reason = next(
        (a["message"] for a in alerts if a.get("severity") == "critical"),
        alerts[0]["message"] if alerts else "Live vitals out of range",
    )
    _flip_to_urgent(patient, reason, source="wearable")
    return await emergency_call(patient, reason)


def _flip_to_urgent(patient: Patient, reason: str, source: str) -> None:
    """Turn the patient red on the map and push the recolor to every dashboard."""
    previous = patient.status
    patient.status = PatientStatus.urgent
    events.broadcast(
        "patient_status",
        {
            "patient_id": patient.id,
            "status": patient.status.value,
            "previous_status": previous.value,
            "reason": reason,
            "source": source,
            "at": datetime.now().isoformat(),
        },
    )
    log.info("Auto-escalation: patient %s -> urgent (%s)", patient.id, reason)


async def emergency_call(patient: Patient, reason: str) -> CallRecord | None:
    """Call the patient; if they don't pick up, route the emergency to the nurse.

    Used by the Garmin ``/live`` path and the frontend BLE/demo path alike. The
    patient call is placed now; the no-answer check runs in the background so the
    caller (a request handler) returns immediately.

    Suppressed (returns ``None``) if another escalation for this patient went out
    within ``_EMERGENCY_COOLDOWN_SECS`` - the backstop against repeat-fire spam.
    """
    now = time.monotonic()
    last = _last_emergency.get(patient.id)
    if last is not None and (now - last) < _EMERGENCY_COOLDOWN_SECS:
        log.info(
            "Emergency for patient %s suppressed: within %.0fs cooldown of the last call.",
            patient.id, _EMERGENCY_COOLDOWN_SECS,
        )
        return None
    _last_emergency[patient.id] = now

    to_number = patient.phone_number
    if not to_number:
        log.warning("Emergency: patient %s has no phone number; routing to nurse now.", patient.id)
        await _route_to_nurse(patient, reason)
        return None

    questions = call_store.get_config(patient.id).questions
    call = await telephony.place_call(
        patient, to_number, questions, kind="auto", watch_for_emergency=True
    )

    # Persist this episode: poll the call's analysis in the background until it's
    # done so it materializes into a saved check-in summary, even though no one may
    # have the patient open in the dashboard.
    if call.conversation_id:
        from . import conversation_store  # late import avoids an import cycle

        asyncio.create_task(conversation_store.ensure_materialized(call.conversation_id))

    # If the dial never connected, escalate to the nurse promptly; otherwise give
    # the patient's phone time to ring before deciding they didn't answer.
    delay = NO_ANSWER_SECS if call.status == "initiated" else 1.0
    asyncio.create_task(_route_to_nurse_if_unanswered(patient, call, reason, delay))
    return call


def _patient_answered(detail) -> bool:
    """True if the patient actually picked up (spoke, or the call ran long enough)."""
    if detail is None:
        return False  # couldn't confirm -> fail safe and alert the nurse
    if any((t.role == "user" and (t.message or "").strip()) for t in detail.transcript):
        return True
    if detail.call_duration_secs and detail.call_duration_secs >= _ANSWERED_MIN_SECS:
        return True
    return False


async def _route_to_nurse_if_unanswered(
    patient: Patient, call: CallRecord, reason: str, delay: float
) -> None:
    """Background: wait out the ring, and alert the nurse if the patient didn't answer."""
    try:
        await asyncio.sleep(delay)
        if call.status == "initiated" and call.conversation_id:
            from . import conversation_store  # late import avoids an import cycle

            detail = await conversation_store.get_detail(call.conversation_id)
            if _patient_answered(detail):
                log.info("Patient %s answered the emergency call; no nurse routing.", patient.id)
                return
        await _route_to_nurse(patient, reason)
    except Exception:  # noqa: BLE001 - a background task must never crash the loop
        log.exception("Nurse follow-up failed for patient %s", patient.id)


def _nurse_briefing(patient: Patient, reason: str) -> list[str]:
    """Key points the alert agent should convey to the nurse."""
    where = patient.district or "an unknown district"
    return [
        f"Patient {patient.name}, age {patient.age}, in {where}.",
        f"Reason for the alert: {reason}",
        "The patient did NOT answer their automated emergency check-in call.",
        "Ask the nurse to follow up with the patient immediately.",
    ]


def _nurse_system_prompt(patient: Patient, reason: str) -> str:
    """Persona override so the agent briefs the NURSE, not the patient.

    Without this the call inherits the patient check-in persona and greets the
    nurse as if they were the unwell patient ("I can tell you're not feeling
    well..."). This makes the agent speak to the nurse as a colleague.
    """
    where = patient.district or "an unknown district"
    return (
        "You are Careloop, an automated clinical escalation line for an elderly-care "
        "service. IMPORTANT: you are calling the ON-CALL NURSE, not the patient. Do "
        "not greet this person as a patient, do not ask how they are feeling, and do "
        "not run a check-in. Speak to them as a clinical colleague. "
        f"A wearable alert fired for {patient.name}, age {patient.age}, in {where}, and "
        "the patient did NOT answer their automated emergency check-in call. "
        f"Reason for the alert: {reason}. "
        "Calmly brief the nurse: state the patient's name, the reason for the alert, "
        "and that the patient did not answer. Ask them to follow up with the patient "
        "immediately. Keep it under a minute, confirm they have noted it, then end the "
        "call politely."
    )


def _nurse_first_message(patient: Patient) -> str:
    """Opening line the agent says to the nurse."""
    return (
        f"Hello, this is the Careloop care line with an urgent escalation about "
        f"{patient.name}. They did not answer their emergency check-in call. "
        "May I give you the details?"
    )


async def _route_to_nurse(patient: Patient, reason: str) -> CallRecord | None:
    """Place the outbound alert call to the on-call nurse."""
    nurse = settings.nurse_phone_number
    if not nurse:
        log.warning(
            "Patient %s did not answer but NO nurse was dialed: set NURSE_PHONE_NUMBER.",
            patient.id,
        )
        return None
    log.info("Routing unanswered emergency for patient %s to nurse %s.", patient.id, nurse)
    return await telephony.place_call(
        patient,
        nurse,
        _nurse_briefing(patient, reason),
        kind="instant",
        system_prompt=_nurse_system_prompt(patient, reason),
        first_message=_nurse_first_message(patient),
        is_nurse_call=True,
    )
