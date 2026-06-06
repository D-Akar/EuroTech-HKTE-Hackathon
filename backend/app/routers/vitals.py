"""Rich per-reading wearable vitals endpoint, additive to /wearables."""

from fastapi import APIRouter, HTTPException

from .. import data, wearable_source

router = APIRouter(prefix="/patients/{patient_id}/vitals", tags=["vitals"])


@router.get("")
def list_vitals(patient_id: int, kind: str | None = None, limit: int = 1000) -> list[dict]:
    if data.get_patient(patient_id) is None:
        raise HTTPException(status_code=404, detail="Patient not found")
    if patient_id != wearable_source.REAL_PATIENT_ID:
        return []
    return wearable_source.raw_samples(kind=kind, limit=limit)
