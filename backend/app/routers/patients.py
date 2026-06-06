"""Patient endpoints."""

from fastapi import APIRouter, HTTPException

from .. import data, fhir_source
from ..models import MedicalProfile, Patient

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


@router.get("/{patient_id}/profile", response_model=MedicalProfile)
def get_patient_profile(patient_id: int) -> MedicalProfile:
    """Real FHIR clinical record for an MongoDB-backed patient (404 if mock)."""
    profile = fhir_source.get_profile(patient_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="No FHIR profile for this patient")
    return profile
