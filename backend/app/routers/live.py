"""Live current vitals for the featured patient (best-effort, falls back to export)."""

from fastapi import APIRouter, HTTPException

from .. import alerts, data, live_monitor, live_source, wearable_source

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
async def get_live(patient_id: int) -> dict:
    if data.get_patient(patient_id) is None:
        raise HTTPException(status_code=404, detail="Patient not found")
    if patient_id != wearable_source.REAL_PATIENT_ID:
        return _EMPTY
    snapshot = live_source.live_vitals()
    assessment = alerts.live_assessment(patient_id, snapshot)
    # If the live reading is out of range, auto-escalate (flip to urgent on the
    # map + place an ElevenLabs check-in call) - once per episode.
    await live_monitor.maybe_autocall(patient_id, assessment)
    return {**snapshot, **assessment}
