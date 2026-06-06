"""Real-time clinical escalation.

When urgent information surfaces (e.g. a nurse learns something alarming during a
phone call), a single ``POST /patients/{id}/escalate`` call:

1. Flips the patient's status to ``urgent`` (stable/attention -> red).
2. Broadcasts the change over SSE so every open dashboard recolors instantly.
3. Places an outbound alert call to the on-call nurse with the patient context.

In-memory, like the rest of the wireframe - escalation history resets on restart.
"""

from __future__ import annotations

import logging
from datetime import datetime
from itertools import count

from fastapi import APIRouter, HTTPException

from .. import data, events
from ..config import settings
from ..models import EscalationRecord, EscalationRequest, Patient, PatientStatus
from ..services import telephony

logger = logging.getLogger(__name__)

router = APIRouter(tags=["escalations"])

# In-memory escalation log, most-recent first.
ESCALATIONS: list[EscalationRecord] = []
_escalation_ids = count(1)


def _nurse_briefing(patient: Patient, reason: str) -> list[str]:
    """Lines the alert agent reads to the nurse (passed as call 'questions')."""
    where = patient.district or "an unknown district"
    return [
        f"This is an urgent escalation for {patient.name}, age {patient.age}, in {where}.",
        f"Reason for escalation: {reason}",
        "Please review the patient's record and follow up immediately.",
    ]


async def perform_escalation(
    patient: Patient,
    reason: str,
    source: str = "phone_call",
    notify_nurse: bool = True,
    nurse_number: str | None = None,
) -> EscalationRecord:
    """Run the escalation for an already-resolved patient.

    Shared by the dashboard route (``POST /patients/{id}/escalate``) and the
    ElevenLabs agent webhook (``POST /integrations/elevenlabs/escalate``): flip
    status -> urgent, push the recolor over SSE, and alert the on-call nurse.
    """
    previous = patient.status
    patient.status = PatientStatus.urgent  # stable/attention -> red

    now = datetime.now()

    # Push the recolor to every connected dashboard right away.
    events.broadcast(
        "patient_status",
        {
            "patient_id": patient.id,
            "status": patient.status.value,
            "previous_status": previous.value,
            "reason": reason,
            "source": source,
            "at": now.isoformat(),
        },
    )

    # Alert the on-call nurse (best-effort; the call outcome is recorded either way).
    nurse_call = None
    if notify_nurse:
        target = nurse_number or settings.nurse_phone_number
        if target:
            nurse_call = await telephony.place_call(
                patient,
                target,
                _nurse_briefing(patient, reason),
                kind="instant",
            )
        else:
            # No number configured -> the dial is skipped silently otherwise, which
            # looks identical to a successful escalation. Make it diagnosable.
            logger.warning(
                "escalation for patient=%s flipped to urgent but NO nurse was dialed: "
                "no NURSE_PHONE_NUMBER set (and no nurse_number passed). Set "
                "NURSE_PHONE_NUMBER in backend/.env to alert the on-call nurse.",
                patient.id,
            )

    record = EscalationRecord(
        id=next(_escalation_ids),
        patient_id=patient.id,
        patient_name=patient.name,
        reason=reason,
        source=source,
        previous_status=previous,
        status=patient.status,
        triggered_at=now,
        nurse_call=nurse_call,
    )
    ESCALATIONS.insert(0, record)
    return record


@router.post("/patients/{patient_id}/escalate", response_model=EscalationRecord)
async def escalate(patient_id: int, body: EscalationRequest) -> EscalationRecord:
    patient = data.get_patient(patient_id)
    if patient is None:
        raise HTTPException(status_code=404, detail="Patient not found")
    return await perform_escalation(
        patient,
        reason=body.reason,
        source=body.source,
        notify_nurse=body.notify_nurse,
        nurse_number=body.nurse_number,
    )


@router.get("/escalations", response_model=list[EscalationRecord])
def list_escalations() -> list[EscalationRecord]:
    return ESCALATIONS
