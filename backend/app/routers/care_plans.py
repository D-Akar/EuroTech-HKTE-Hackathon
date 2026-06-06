"""Upload, retrieve, and delete FHIR care plans for patients."""

from fastapi import APIRouter, HTTPException, Request, Response

from .. import care_plan_store, data
from ..fhir_careplan import CarePlanParseError
from ..models import CarePlanContext

router = APIRouter(tags=["care-plans"])


async def _read_body(request: Request) -> str:
    raw = (await request.body()).decode("utf-8", errors="replace")
    if not raw.strip():
        raise HTTPException(status_code=422, detail="Empty request body.")
    return raw


def _parse(raw: str) -> CarePlanContext:
    try:
        return care_plan_store.parse_care_plan(raw)
    except CarePlanParseError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e


@router.post("/patients/{patient_id}/care-plan", response_model=CarePlanContext)
async def upload_care_plan(patient_id: int, request: Request) -> CarePlanContext:
    if data.get_patient(patient_id) is None:
        raise HTTPException(status_code=404, detail="Patient not found")
    raw = await _read_body(request)
    ctx = _parse(raw)
    care_plan_store.set(patient_id, raw, ctx)
    return ctx


@router.get("/patients/{patient_id}/care-plan", response_model=CarePlanContext)
def get_care_plan(patient_id: int) -> CarePlanContext:
    stored = care_plan_store.get(patient_id)
    if stored is None:
        raise HTTPException(status_code=404, detail="No care plan for this patient")
    return stored.care_plan


@router.delete("/patients/{patient_id}/care-plan", status_code=204)
def delete_care_plan(patient_id: int) -> Response:
    if not care_plan_store.delete(patient_id):
        raise HTTPException(status_code=404, detail="No care plan for this patient")
    return Response(status_code=204)


@router.post("/care-plans")
async def upload_care_plan_auto(request: Request) -> dict:
    raw = await _read_body(request)
    ctx = _parse(raw)
    patient = data.get_patient_by_subject(ctx.subject_display or "")
    if patient is None:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Could not match care plan subject "
                f"'{ctx.subject_display or 'unknown'}' to a patient. "
                "Upload it against a specific patient instead."
            ),
        )
    care_plan_store.set(patient.id, raw, ctx)
    return {"patient_id": patient.id, "care_plan": ctx.model_dump()}
