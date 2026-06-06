"""Clinician-ready PDF report endpoint, nested under a patient."""

from datetime import date

from fastapi import APIRouter, HTTPException, Response

from .. import data
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
    summary = build_summary(checkins, wearables)
    pdf = build_report_pdf(patient, summary, checkins, wearables)

    filename = f"patient-{patient_id}-report-{date.today():%Y-%m-%d}.pdf"
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )
