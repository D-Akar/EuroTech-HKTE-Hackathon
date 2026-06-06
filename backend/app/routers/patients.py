"""Patient endpoints."""

from fastapi import APIRouter, HTTPException

from .. import data, fhir_source, patient_overrides
from ..models import MedicalProfile, Patient, PhoneUpdate

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


@router.put("/{patient_id}/phone", response_model=Patient)
def update_patient_phone(patient_id: int, body: PhoneUpdate) -> Patient:
    """Set the patient's check-in phone number.

    Persisted to MongoDB (best-effort) and applied to the live patient, so every
    later 'Call now' and scheduled call dials the saved number without re-typing.
    """
    patient = data.get_patient(patient_id)
    if patient is None:
        raise HTTPException(status_code=404, detail="Patient not found")
    try:
        cleaned = patient_overrides.set_phone(patient_id, body.phone_number)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid phone number")
    patient.phone_number = cleaned
    return patient


@router.get("/{patient_id}/profile", response_model=MedicalProfile)
def get_patient_profile(patient_id: int) -> MedicalProfile:
    """Real FHIR clinical record for an MongoDB-backed patient (404 if mock)."""
    profile = fhir_source.get_profile(patient_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="No FHIR profile for this patient")
    return profile
