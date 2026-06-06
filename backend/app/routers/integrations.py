"""External integrations — ElevenLabs server-tool callbacks."""

from fastapi import APIRouter, Depends, Header, HTTPException

from .. import data
from ..config import settings
from ..models import PatientContextResponse
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
