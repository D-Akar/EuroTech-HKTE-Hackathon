"""Patient endpoints."""

from fastapi import APIRouter, HTTPException

from .. import data
from ..models import Patient

router = APIRouter(prefix="/patients", tags=["patients"])


@router.get("", response_model=list[Patient])
def list_patients() -> list[Patient]:
    return data.get_patients()


@router.get("/{patient_id}", response_model=Patient)
def get_patient(patient_id: int) -> Patient:
    patient = data.get_patient(patient_id)
    if patient is None:
        raise HTTPException(status_code=404, detail="Patient not found")
    return patient
