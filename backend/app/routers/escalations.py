"""Real-time clinical escalation.

When urgent information surfaces (e.g. a nurse learns something alarming during a
phone call), a single ``POST /patients/{id}/escalate`` call:

1. Flips the patient's status to ``urgent`` (stable/attention -> red).
2. Broadcasts the change over SSE so every open dashboard recolors instantly.
3. Places an outbound alert call to the on-call nurse with the patient context.

In-memory, like the rest of the wireframe — escalation history resets on restart.
"""

from __future__ import annotations

from datetime import datetime
from itertools import count

from fastapi import APIRouter, HTTPException

from .. import data, events
from ..config import settings
from ..models import EscalationRecord, EscalationRequest, Patient, PatientStatus
from ..services import telephony

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


@router.post("/patients/{patient_id}/escalate", response_model=EscalationRecord)
async def escalate(patient_id: int, body: EscalationRequest) -> EscalationRecord:
    patient = data.get_patient(patient_id)
    if patient is None:
        raise HTTPException(status_code=404, detail="Patient not found")

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
            "reason": body.reason,
            "source": body.source,
            "at": now.isoformat(),
        },
    )

    # Alert the on-call nurse (best-effort; the call outcome is recorded either way).
    nurse_call = None
    if body.notify_nurse:
        nurse_number = body.nurse_number or settings.nurse_phone_number
        if nurse_number:
            nurse_call = await telephony.place_call(
                patient,
                nurse_number,
                _nurse_briefing(patient, body.reason),
                kind="instant",
            )

    record = EscalationRecord(
        id=next(_escalation_ids),
        patient_id=patient.id,
        patient_name=patient.name,
        reason=body.reason,
        source=body.source,
        previous_status=previous,
        status=patient.status,
        triggered_at=now,
        nurse_call=nurse_call,
    )
    ESCALATIONS.insert(0, record)
    return record


@router.get("/escalations", response_model=list[EscalationRecord])
def list_escalations() -> list[EscalationRecord]:
    return ESCALATIONS
