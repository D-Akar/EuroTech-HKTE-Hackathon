"""Places outbound AI check-in calls via the ElevenLabs Twilio integration.

The per-patient context (recent check-ins + wearables) and the practice's
questions are passed as ElevenLabs *dynamic variables*. The agent's prompt in
the ElevenLabs dashboard must reference them:
``{{patient_name}}``, ``{{patient_age}}``, ``{{recent_summary}}``, ``{{questions}}``.
"""

from __future__ import annotations

from datetime import datetime

import httpx

from .. import call_store, conversation_store, data
from ..config import settings
from ..models import CallRecord, Patient

# How many recent check-ins to summarise into the call context.
_RECENT_CHECKINS = 3


async def build_recent_summary(patient_id: int) -> str:
    """Human-readable summary of recent phone check-ins and latest wearables.

    Opens with a digest of the patient's most recent completed AI call (pulled
    from ElevenLabs, best-effort) so the agent knows what was said last time.
    """
    checkins = sorted(
        data.get_checkins(patient_id), key=lambda c: c.date, reverse=True
    )[:_RECENT_CHECKINS]
    wearables = sorted(
        data.get_wearables(patient_id), key=lambda w: w.timestamp, reverse=True
    )

    lines: list[str] = []
    prior_call = await conversation_store.latest_digest(patient_id)
    if prior_call:
        lines.append(prior_call)
    if checkins:
        lines.append("Recent phone check-ins:")
        for c in checkins:
            answered = "answered" if c.answered else "no answer"
            lines.append(
                f"- {c.date.isoformat()}: mood {c.mood}, pain {c.pain_level}/10 "
                f"({answered}). Notes: {c.notes}"
            )
    if wearables:
        w = wearables[0]
        lines.append(
            f"Latest wearable reading ({w.timestamp.date().isoformat()}): "
            f"heart rate {w.heart_rate} bpm, {w.steps} steps, "
            f"{w.sleep_hours}h sleep."
        )
    if not lines:
        return "No recent check-in or wearable data available."
    return "\n".join(lines)


async def build_dynamic_variables(
    patient: Patient, questions: list[str]
) -> dict[str, str]:
    """Build the ElevenLabs dynamic-variable map injected into the call."""
    numbered = "\n".join(f"{i}. {q}" for i, q in enumerate(questions, start=1))
    return {
        "patient_name": patient.name,
        "patient_age": str(patient.age),
        "recent_summary": await build_recent_summary(patient.id),
        "questions": numbered,
    }


async def place_call(
    patient: Patient,
    to_number: str,
    questions: list[str],
    kind: str = "instant",
) -> CallRecord:
    """Place an outbound call and record the outcome in the call history."""
    triggered_at = datetime.now()
    record_id = call_store.next_record_id()

    if not settings.is_configured:
        record = CallRecord(
            id=record_id,
            patient_id=patient.id,
            triggered_at=triggered_at,
            kind=kind,
            to_number=to_number,
            status="failed",
            error="Telephony not configured. Set ELEVENLABS_* vars in backend/.env.",
        )
        return call_store.add_call_record(record)

    payload = {
        "agent_id": settings.elevenlabs_agent_id,
        "agent_phone_number_id": settings.elevenlabs_agent_phone_number_id,
        "to_number": to_number,
        "conversation_initiation_client_data": {
            "dynamic_variables": await build_dynamic_variables(patient, questions),
        },
    }
    headers = {"xi-api-key": settings.elevenlabs_api_key}

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                settings.elevenlabs_outbound_url, json=payload, headers=headers
            )
        resp.raise_for_status()
        body = resp.json()
        if not body.get("success", False):
            raise RuntimeError(body.get("message") or "ElevenLabs reported failure")
        record = CallRecord(
            id=record_id,
            patient_id=patient.id,
            triggered_at=triggered_at,
            kind=kind,
            to_number=to_number,
            status="initiated",
            conversation_id=body.get("conversation_id"),
            call_sid=body.get("callSid"),
        )
    except Exception as exc:  # noqa: BLE001 — surface any failure to the record
        record = CallRecord(
            id=record_id,
            patient_id=patient.id,
            triggered_at=triggered_at,
            kind=kind,
            to_number=to_number,
            status="failed",
            error=str(exc),
        )

    return call_store.add_call_record(record)
