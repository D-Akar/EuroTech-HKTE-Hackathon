"""Wearable-reading endpoints, nested under a patient."""

from fastapi import APIRouter, HTTPException

from .. import data
from ..models import WearableReading

router = APIRouter(prefix="/patients/{patient_id}/wearables", tags=["wearables"])


@router.get("", response_model=list[WearableReading])
def list_wearables(patient_id: int) -> list[WearableReading]:
    if data.get_patient(patient_id) is None:
        raise HTTPException(status_code=404, detail="Patient not found")
    return data.get_wearables(patient_id)
