"""Outbound check-in call endpoints, nested under a patient."""

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import StreamingResponse

from .. import (
    call_store,
    checkin_agent,
    cognitive_demo,
    conversation_store,
    data,
    live_monitor,
    scheduler,
    screening,
)
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
from ..services import elevenlabs_conversations, telephony
from ..services import elevenlabs_monitor as monitor

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
    # Hand the agent the patient's personalised generated questions (falling back
    # to the practice config), unless the caller passed an explicit override.
    questions = telephony.resolve_questions(patient_id, override=body.questions)
    # Drive the call with the consent-gated check-in persona so the agent always
    # asks for consent first and speaks the privacy response verbatim, without
    # depending on the ElevenLabs dashboard prompt. A patient-specific custom
    # prompt/greeting in the call config still wins (place_call -> build_overrides).
    config = call_store.get_config(patient_id)
    system_prompt = None if config.system_prompt else checkin_agent.system_prompt(patient)
    first_message = None if config.greeting else checkin_agent.first_message(patient)
    return await telephony.place_call(
        patient,
        to_number,
        questions,
        kind="instant",
        system_prompt=system_prompt,
        first_message=first_message,
        watch_for_emergency=True,
    )


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
    # Drive the screening agent with our scripted, self-scoring protocol (3-word
    # recall + orientation, no animal-fluency task) so wrong answers actually
    # escalate to the nurse mid-call. Requires the screening agent to have prompt
    # overrides + the escalate_emergency tool enabled.
    return await telephony.place_call(
        patient,
        to_number,
        questions=[],
        kind="screening",
        agent_id=settings.elevenlabs_screening_agent_id,
        system_prompt=screening.system_prompt(patient),
        first_message=screening.first_message(patient),
        watch_for_emergency=True,
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
        watch_for_emergency=True,
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


@router.get("/{call_id}/audio")
async def get_call_audio(patient_id: int, call_id: int) -> Response:
    """Download the recorded call audio (mp3) for one call.

    Proxies the ElevenLabs recording so the dashboard can offer a download without
    exposing the API key. 409 while the recording isn't ready yet.
    """
    _require_patient(patient_id)
    record = call_store.get_call_record(patient_id, call_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Call not found")
    if not record.conversation_id:
        raise HTTPException(status_code=404, detail="No conversation for this call")
    audio = await elevenlabs_conversations.fetch_conversation_audio(record.conversation_id)
    if not audio:
        raise HTTPException(status_code=409, detail="Recording not available yet")
    filename = f"call-{patient_id}-{call_id}.mp3"
    return Response(
        content=audio,
        media_type="audio/mpeg",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/{call_id}/live")
async def live_call_transcript(patient_id: int, call_id: int, request: Request) -> StreamingResponse:
    """Stream a live call's transcript as it is spoken (Server-Sent Events).

    Proxies the ElevenLabs real-time monitor WebSocket (Enterprise-only) down to the
    browser as SSE: ``event: ready`` immediately, one ``event: turn`` per spoken
    turn, then a terminal ``event: end`` when the call finishes. Any failure (no
    Enterprise access, call already over, telephony unconfigured) ends the stream
    cleanly so the UI falls back to the post-call conversation view.
    """
    _require_patient(patient_id)
    record = call_store.get_call_record(patient_id, call_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Call not found")
    if not record.conversation_id:
        raise HTTPException(status_code=404, detail="No conversation for this call")
    conversation_id = record.conversation_id

    async def gen():
        yield "event: ready\ndata: {}\n\n"
        async for turn in monitor.stream_turns(conversation_id):
            if await request.is_disconnected():
                return  # client gone: closing the generator closes the upstream WS
            yield monitor.format_sse(turn)
        # Upstream closed on its own (call ended). Tell the client it's over so
        # EventSource stops reconnecting and the row flips to the post-call view.
        # (Not in a finally: a disconnect closes us via GeneratorExit, during which
        # yielding is illegal — and the cleanup we need lives in stream_turns.)
        yield "event: end\ndata: {}\n\n"

    headers = {
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",  # disable proxy buffering so turns flush immediately
    }
    return StreamingResponse(gen(), media_type="text/event-stream", headers=headers)


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
    questions = telephony.resolve_questions(patient_id)
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
