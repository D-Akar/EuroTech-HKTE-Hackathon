"""Clinician-ready PDF report endpoint, nested under a patient."""

from datetime import date

from fastapi import APIRouter, HTTPException, Response

from .. import alerts, care_plan_store, data, fhir_source, wearable_source
from ..report_pdf import build_report_pdf
from ..report_summary import build_summary

router = APIRouter(prefix="/patients/{patient_id}/report", tags=["reports"])


@router.get(
    ".pdf",
    responses={200: {"content": {"application/pdf": {}}}},
    response_class=Response,
)
def patient_report_pdf(patient_id: int) -> Response:
    """Build and stream a clinician-ready PDF for one patient."""
    patient = data.get_patient(patient_id)
    if patient is None:
        raise HTTPException(status_code=404, detail="Patient not found")

    checkins = data.get_checkins(patient_id)
    wearables = data.get_wearables(patient_id)
    vitals = (
        wearable_source.raw_samples()
        if patient_id == wearable_source.REAL_PATIENT_ID
        else []
    )
    alert_list = alerts.alerts_for(patient_id, wearables, vitals)
    profile = fhir_source.get_profile(patient_id)  # None for mock patients
    stored_plan = care_plan_store.get(patient_id)
    care_plan = stored_plan.care_plan if stored_plan else None

    summary = build_summary(
        checkins, wearables, vitals, care_plan=care_plan, alerts=alert_list
    )
    pdf = build_report_pdf(
        patient,
        summary,
        checkins,
        wearables,
        profile=profile,
        alerts=alert_list,
        care_plan=care_plan,
    )

    filename = f"patient-{patient_id}-report-{date.today():%Y-%m-%d}.pdf"
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'inline; filename="{filename}"',
            # Always hand back a freshly built report; never a browser-cached copy.
            "Cache-Control": "no-store",
        },
    )
