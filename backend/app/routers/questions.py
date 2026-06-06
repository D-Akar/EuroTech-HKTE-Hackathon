"""Tailored check-in question endpoints, nested under a patient.

`GET` returns the stored, LLM-generated questions (empty set if none generated yet);
`POST /regenerate` re-runs the generation for that one patient using the same
pipeline as the offline batch (recent check-ins + FHIR conditions + worsening-symptom
guide), persists it, and returns the fresh set. Regeneration calls the LLM, so it is
a normal sync handler - FastAPI runs it in a threadpool and the call may take a few
seconds.
"""

from fastapi import APIRouter, HTTPException

from .. import data
from ..models import PatientQuestions
from ..services import question_gen

router = APIRouter(prefix="/patients/{patient_id}/questions", tags=["questions"])


@router.get("", response_model=PatientQuestions)
def get_questions(patient_id: int) -> PatientQuestions:
    patient = data.get_patient(patient_id)
    if patient is None:
        raise HTTPException(status_code=404, detail="Patient not found")
    return question_gen.get_for_patient(patient)


@router.post("/regenerate", response_model=PatientQuestions)
def regenerate_questions(patient_id: int) -> PatientQuestions:
    patient = data.get_patient(patient_id)
    if patient is None:
        raise HTTPException(status_code=404, detail="Patient not found")
    try:
        return question_gen.generate_for_patient(patient)
    except RuntimeError as e:
        # LLM backend not usable (no key / openai missing) - a configuration issue.
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:  # noqa: BLE001 - surface a clean error to the dashboard
        raise HTTPException(status_code=502, detail=f"Question generation failed: {e}")
