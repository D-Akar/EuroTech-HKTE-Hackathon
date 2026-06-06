"""External integrations - ElevenLabs server-tool callbacks."""

from fastapi import APIRouter, Depends, Header, HTTPException

from .. import data
from ..config import settings
from ..models import AgentEscalationRequest, EscalationRecord, PatientContextResponse
from ..routers.escalations import perform_escalation
from ..services.patient_context import build_patient_context

router = APIRouter(prefix="/integrations/elevenlabs", tags=["integrations"])


def verify_tool_api_key(x_api_key: str = Header(default="")) -> None:
    """Require a valid X-API-Key matching ELEVENLABS_TOOL_API_KEY."""
    expected = settings.elevenlabs_tool_api_key
    if not expected or x_api_key != expected:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")


@router.get(
    "/patient-context",
    response_model=PatientContextResponse,
    dependencies=[Depends(verify_tool_api_key)],
)
def get_patient_context(phone_number: str) -> PatientContextResponse:
    """Look up a patient by phone number and return their full health context."""
    patient = data.get_patient_by_phone(phone_number)
    if patient is None:
        raise HTTPException(status_code=404, detail="Patient not found")
    return build_patient_context(patient)


@router.post(
    "/escalate",
    response_model=EscalationRecord,
    dependencies=[Depends(verify_tool_api_key)],
)
async def escalate_from_agent(body: AgentEscalationRequest) -> EscalationRecord:
    """Escalate the patient the outbound agent is on a call with.

    Mirrors ``POST /patients/{id}/escalate`` but identifies the patient by the
    ``patient_id`` dynamic variable injected at dial time, and is guarded by the
    same X-API-Key as the other ElevenLabs tools. Flips status -> urgent,
    recolors every dashboard over SSE, and places the nurse alert call.
    """
    patient = data.get_patient(body.patient_id)
    if patient is None:
        raise HTTPException(status_code=404, detail="Patient not found")
    return await perform_escalation(patient, reason=body.reason, source=body.source)
