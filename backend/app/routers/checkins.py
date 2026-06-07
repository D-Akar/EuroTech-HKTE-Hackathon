"""Daily check-in endpoints, nested under a patient."""

from fastapi import APIRouter, HTTPException

from .. import checkin_store, data
from ..models import CheckIn

router = APIRouter(prefix="/patients/{patient_id}/checkins", tags=["checkins"])


@router.get("", response_model=list[CheckIn])
def list_checkins(patient_id: int) -> list[CheckIn]:
    if data.get_patient(patient_id) is None:
        raise HTTPException(status_code=404, detail="Patient not found")
    # Real check-ins derived from completed AI calls, newest first, then the
    # synthetic daily history. Sort by (date, id) descending: CheckIn has no time
    # field, so several calls on the same day tie on date alone, and the monotonic
    # id (call-derived ids increment in creation order) puts the most recent call
    # on top instead of leaving it buried by an earlier same-day entry.
    derived = checkin_store.list_for_patient(patient_id)
    checkins = derived + data.get_checkins(patient_id)
    checkins.sort(key=lambda c: (c.date, c.id), reverse=True)
    return checkins
