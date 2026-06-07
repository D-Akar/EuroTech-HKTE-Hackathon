"""Dashboard metadata: which patient is backed by the real Garmin device."""

import os

from fastapi import APIRouter

from .. import wearable_source

router = APIRouter(prefix="/meta", tags=["meta"])


@router.get("")
def get_meta() -> dict:
    """Tell the dashboard which patient carries the live device, the FHIR patient id
    the vitals are stamped with, and whether real wearable data is loaded."""
    return {
        "featured_patient_id": wearable_source.REAL_PATIENT_ID,
        "featured_patient_uuid": os.environ.get("GARMIN_PATIENT_UUID") or None,
        "live_data": wearable_source.is_real(),
    }
