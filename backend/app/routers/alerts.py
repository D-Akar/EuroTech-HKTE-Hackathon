"""Threshold alerts per patient, from wearable readings and rich vitals."""

from fastapi import APIRouter, HTTPException

from .. import alerts, data, wearable_source

router = APIRouter(prefix="/patients/{patient_id}/alerts", tags=["alerts"])


@router.get("")
def list_alerts(patient_id: int) -> list[dict]:
    if data.get_patient(patient_id) is None:
        raise HTTPException(status_code=404, detail="Patient not found")
    readings = data.get_wearables(patient_id)
    vitals = wearable_source.raw_samples() if patient_id == wearable_source.REAL_PATIENT_ID else []
    return alerts.alerts_for(patient_id, readings, vitals)
