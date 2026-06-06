"""Live current vitals for the featured patient (best-effort, falls back to export)."""

from fastapi import APIRouter, HTTPException

from .. import alerts, data, live_source, wearable_source

router = APIRouter(prefix="/patients/{patient_id}/live", tags=["live"])

_EMPTY = {
    "source": "none",
    "heart_rate": None,
    "stress": None,
    "spo2": None,
    "steps": None,
    "status": "none",
    "alerts": [],
}


@router.get("")
def get_live(patient_id: int) -> dict:
    if data.get_patient(patient_id) is None:
        raise HTTPException(status_code=404, detail="Patient not found")
    if patient_id != wearable_source.REAL_PATIENT_ID:
        return _EMPTY
    snapshot = live_source.live_vitals()
    return {**snapshot, **alerts.live_assessment(patient_id, snapshot)}
