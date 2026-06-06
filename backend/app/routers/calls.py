"""Outbound check-in call endpoints, nested under a patient."""

from fastapi import APIRouter, HTTPException

from .. import call_store, cognitive_demo, conversation_store, data, live_monitor, scheduler
from ..config import settings
from ..models import (
    CallConfig,
    CallRecord,
    ConfigUpdate,
    ConversationDetail,
    EmergencyCallRequest,
    ScheduledCall,
    ScheduleRequest,
    TriggerRequest,
)
from ..services import telephony

router = APIRouter(prefix="/patients/{patient_id}/calls", tags=["calls"])


def _require_patient(patient_id: int):
    patient = data.get_patient(patient_id)
    if patient is None:
        raise HTTPException(status_code=404, detail="Patient not found")
    return patient


@router.post("/trigger", response_model=CallRecord)
async def trigger_call(patient_id: int, body: TriggerRequest) -> CallRecord:
    """Place an instant 'Call now' to the patient."""
    patient = _require_patient(patient_id)
    to_number = body.to_number or patient.phone_number
    if not to_number:
        raise HTTPException(status_code=400, detail="No phone number for this patient")
    questions = body.questions or call_store.get_config(patient_id).questions
    return await telephony.place_call(patient, to_number, questions, kind="instant")


@router.post("/screening", response_model=CallRecord)
async def screening_call(patient_id: int, body: TriggerRequest) -> CallRecord:
    """Place a cognitive-screening call using the dedicated screening agent.

    A separate ElevenLabs agent runs the scripted dementia voice-biomarker protocol
    (Mini-Cog recall, orientation, verbal fluency); its Data Collection and
    Evaluation Criteria surface the markers in the call detail.
    """
    patient = _require_patient(patient_id)
    if not settings.elevenlabs_screening_agent_id:
        raise HTTPException(
            status_code=400,
            detail="No screening agent configured. Set ELEVENLABS_SCREENING_AGENT_ID.",
        )
    to_number = body.to_number or patient.phone_number
    if not to_number:
        raise HTTPException(status_code=400, detail="No phone number for this patient")
    # The screening agent runs a fixed protocol, so no per-call questions are sent.
    return await telephony.place_call(
        patient,
        to_number,
        questions=[],
        kind="screening",
        agent_id=settings.elevenlabs_screening_agent_id,
    )


@router.post("/dementia-demo", response_model=CallRecord)
async def dementia_demo_call(patient_id: int, body: TriggerRequest) -> CallRecord:
    """Live demo: call the patient with the orientation-probe + high-HR script.

    The agent asks what day it is, mentions the high heart rate, then re-asks; if the
    patient can't answer, it escalates to the nurse mid-call via its escalate tool.
    Rides the default outbound agent (which has the escalate tool) with a per-call
    prompt override, so no separate agent is needed.
    """
    patient = _require_patient(patient_id)
    to_number = body.to_number or patient.phone_number
    if not to_number:
        raise HTTPException(status_code=400, detail="No phone number for this patient")
    return await telephony.place_call(
        patient,
        to_number,
        questions=[],
        kind="instant",
        system_prompt=cognitive_demo.system_prompt(patient),
        first_message=cognitive_demo.first_message(patient),
    )


@router.post("/emergency", response_model=CallRecord | None)
async def emergency_call(patient_id: int, body: EmergencyCallRequest) -> CallRecord | None:
    """Wearable-triggered emergency call: dial the patient, and if they don't
    answer, route the emergency to the on-call nurse. Used by the frontend BLE/demo
    path; the Garmin /live path calls the same ``live_monitor.emergency_call``."""
    patient = _require_patient(patient_id)
    reason = body.reason or "Live vitals out of range"
    return await live_monitor.emergency_call(patient, reason)


@router.get("", response_model=list[CallRecord])
def list_calls(patient_id: int) -> list[CallRecord]:
    _require_patient(patient_id)
    return call_store.list_call_records(patient_id)


@router.get("/{call_id}/conversation", response_model=ConversationDetail)
async def get_call_conversation(patient_id: int, call_id: int) -> ConversationDetail:
    """Pull the transcript + extracted check-in data for one completed call.

    Fetched on demand from ElevenLabs. Returns ``status: processing`` (200) while
    ElevenLabs is still analysing the call, so the UI can show a "check back" state.
    """
    _require_patient(patient_id)
    record = call_store.get_call_record(patient_id, call_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Call not found")
    if not record.conversation_id:
        raise HTTPException(status_code=404, detail="No conversation for this call")
    detail = await conversation_store.get_detail(record.conversation_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="Conversation data unavailable")
    return detail


@router.get("/config", response_model=CallConfig)
def get_config(patient_id: int) -> CallConfig:
    _require_patient(patient_id)
    return call_store.get_config(patient_id)


@router.put("/config", response_model=CallConfig)
def update_config(patient_id: int, body: ConfigUpdate) -> CallConfig:
    _require_patient(patient_id)
    return call_store.set_config(
        patient_id, body.questions, body.greeting, body.system_prompt
    )


@router.post("/schedules", response_model=ScheduledCall)
def create_schedule(patient_id: int, body: ScheduleRequest) -> ScheduledCall:
    _require_patient(patient_id)
    questions = call_store.get_config(patient_id).questions
    schedule = call_store.add_schedule(
        patient_id, body.scheduled_at, body.recurring, questions
    )
    scheduler.schedule_call(schedule)
    return schedule


@router.get("/schedules", response_model=list[ScheduledCall])
def list_schedules(patient_id: int) -> list[ScheduledCall]:
    _require_patient(patient_id)
    return call_store.list_schedules(patient_id)


@router.delete("/schedules/{schedule_id}", response_model=ScheduledCall)
def cancel_schedule(patient_id: int, schedule_id: int) -> ScheduledCall:
    _require_patient(patient_id)
    schedule = call_store.get_schedule(schedule_id)
    if schedule is None or schedule.patient_id != patient_id:
        raise HTTPException(status_code=404, detail="Schedule not found")
    scheduler.unschedule_call(schedule_id)
    return call_store.cancel_schedule(schedule_id)
