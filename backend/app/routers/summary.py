"""Summary statistics per patient."""

from fastapi import APIRouter, HTTPException

from .. import data, summary, wearable_source

router = APIRouter(prefix="/patients/{patient_id}/summary", tags=["summary"])


@router.get("")
def get_summary(patient_id: int) -> dict:
    if data.get_patient(patient_id) is None:
        raise HTTPException(status_code=404, detail="Patient not found")
    readings = data.get_wearables(patient_id)
    vitals = wearable_source.raw_samples() if patient_id == wearable_source.REAL_PATIENT_ID else []
    return summary.compute_summary(readings, vitals)
