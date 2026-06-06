"""Daily check-in endpoints, nested under a patient."""

from fastapi import APIRouter, HTTPException

from .. import data
from ..models import CheckIn

router = APIRouter(prefix="/patients/{patient_id}/checkins", tags=["checkins"])


@router.get("", response_model=list[CheckIn])
def list_checkins(patient_id: int) -> list[CheckIn]:
    if data.get_patient(patient_id) is None:
        raise HTTPException(status_code=404, detail="Patient not found")
    return data.get_checkins(patient_id)
