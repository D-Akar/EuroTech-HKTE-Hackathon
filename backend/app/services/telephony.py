"""Places outbound AI check-in calls via the ElevenLabs Twilio integration.

The per-patient context (recent check-ins + wearables) and the practice's
questions are passed as ElevenLabs *dynamic variables*. The agent's prompt in
the ElevenLabs dashboard must reference them:
``{{patient_name}}``, ``{{patient_age}}``, ``{{recent_summary}}``, ``{{questions}}``,
``{{opening_question}}`` (fixed first question, from Prompts/opening_question.md), and
``{{privacy_response}}`` (verbatim data-privacy reply, from Prompts/privacy_response.md).
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime

import httpx

from . import question_gen
from .. import call_store, care_plan_store, checkin_store, conversation_store, data, fhir_source
from ..config import settings
from ..models import CallConfig, CallRecord, LiveVitalsInput, Patient

logger = logging.getLogger(__name__)

# How many recent check-ins to summarise into the call context.
_RECENT_CHECKINS = 3
# Cap procedures folded into the call context so it stays readable.
_RECENT_PROCEDURES = 5


def build_clinical_context(patient_id: int) -> list[str]:
    """Medication, recent procedures, and the care plan for the call context.

    Reads the real FHIR-backed profile (if any) and the uploaded care plan. The
    agent needs these to speak knowledgeably about the patient's treatment.
    """
    lines: list[str] = []

    profile = fhir_source.get_profile(patient_id)
    if profile and profile.active_medications:
        lines.append("Active medications:")
        for m in profile.active_medications:
            freq = f" ({m.frequency})" if m.frequency else ""
            lines.append(f"- {m.name}{freq}")
    if profile and profile.recent_procedures:
        lines.append("Recent procedures:")
        for p in profile.recent_procedures[:_RECENT_PROCEDURES]:
            when = f" on {p.date}" if p.date else ""
            lines.append(f"- {p.name}{when}")

    stored = care_plan_store.get(patient_id)
    if stored is not None:
        lines.append(stored.care_plan.rendered_text)

    return lines


def resolve_questions(patient_id: int, override: list[str] | None = None) -> list[str]:
    """Decide which questions the agent should be handed for this call.

    Priority: an explicit caller override (e.g. custom "Call now" questions) >
    the personalised questions generated for this patient (``question_gen``,
    cross-referenced against their recent check-ins and worsening-symptom guide,
    and surfaced on the dashboard) > the practice's editable default config.

    Order is preserved, so the agent leads with the first generated question.
    Best-effort: any failure to read the generated set falls back to the config.
    """
    if override:
        return override
    patient = data.get_patient(patient_id)
    if patient is not None:
        try:
            generated = question_gen.get_for_patient(patient)
            if generated.generated and generated.questions:
                texts = [q.text for q in generated.questions if q.text]
                if texts:
                    return texts
        except Exception:  # noqa: BLE001 - never let this block a call
            logger.warning(
                "resolve_questions: falling back to config for patient %s", patient_id,
                exc_info=True,
            )
    return call_store.get_config(patient_id).questions


def build_overrides(
    config: CallConfig,
    system_prompt: str | None = None,
    first_message: str | None = None,
) -> dict | None:
    """ElevenLabs ``conversation_config_override`` for the call.

    Explicit ``system_prompt``/``first_message`` (e.g. the nurse-alert persona for
    an escalation call) take precedence over the patient's editable config, so a
    call can speak as something other than the default patient check-in agent.
    Only includes fields that are set; requires the matching overrides to be
    enabled in the agent's Security tab. Returns None when nothing to override.
    """
    sp = (system_prompt or config.system_prompt or "").strip()
    fm = (first_message or config.greeting or "").strip()
    agent: dict = {}
    if sp:
        agent["prompt"] = {"prompt": sp}
    if fm:
        agent["first_message"] = fm
    return {"agent": agent} if agent else None


def _render_live_vitals(live: LiveVitalsInput | None) -> str | None:
    """One line describing a just-captured live wearable reading, or None."""
    if live is None or live.heart_rate is None:
        return None
    parts = [f"heart rate {live.heart_rate} bpm"]
    if live.spo2 is not None:
        parts.append(f"SpO2 {live.spo2}%")
    if live.steps is not None:
        parts.append(f"{live.steps} steps")
    src = f" (from the patient's {'connected watch' if live.source == 'ble' else 'wearable'})" if live.source else ""
    return f"LIVE wearable reading right now{src}: " + ", ".join(parts) + "."


async def build_recent_summary(
    patient_id: int, live_vitals: LiveVitalsInput | None = None
) -> str:
    """Human-readable summary of recent phone check-ins and latest wearables.

    Opens with the **live** wearable reading (if the call was placed with one
    attached, e.g. a connected Bluetooth watch) and a digest of the patient's most
    recent completed AI call, so the agent can speak to the patient's current state.
    """
    lines_live = _render_live_vitals(live_vitals)
    # Real call-derived check-ins dominate (newest first), synthetic seed backfills,
    # so the agent hears what the patient actually said on prior calls.
    checkins = checkin_store.merged_recent(patient_id, _RECENT_CHECKINS)
    wearables = sorted(
        data.get_wearables(patient_id), key=lambda w: w.timestamp, reverse=True
    )

    lines: list[str] = []
    if lines_live:
        lines.append(lines_live)
    prior_call = await conversation_store.latest_digest(patient_id)
    if prior_call:
        lines.append(prior_call)
    if checkins:
        lines.append("Recent phone check-ins:")
        for c in checkins:
            answered = "answered" if c.answered else "no answer"
            lines.append(
                f"- {c.date.isoformat()}: mood {c.mood}, pain {c.pain_level}/10 "
                f"({answered}). Notes: {c.notes}"
            )
    if wearables:
        w = wearables[0]
        lines.append(
            f"Latest wearable reading ({w.timestamp.date().isoformat()}): "
            f"heart rate {w.heart_rate} bpm, {w.steps} steps, "
            f"{w.sleep_hours}h sleep."
        )

    lines.extend(build_clinical_context(patient_id))

    if not lines:
        return "No recent check-in or wearable data available."
    return "\n".join(lines)


def _read_markdown_body(path: str) -> str:
    """Read an editable markdown file, returning just the spoken text.

    Convention (shared with Prompts/patient_questions_prompt.md): everything above the
    first ``---`` separator line is an editing note for humans and is ignored; the
    body below it is what the agent uses. Falls back to the whole file when there
    is no separator, and to an empty string if the file is missing. Read on demand
    (not cached) so edits take effect on the next call without a restart.
    """
    try:
        with open(path, encoding="utf-8") as fh:
            lines = fh.readlines()
    except OSError:
        return ""
    for i, line in enumerate(lines):
        if line.strip() == "---":
            return "".join(lines[i + 1:]).strip()
    return "".join(lines).strip()


async def build_dynamic_variables(
    patient: Patient, questions: list[str], live_vitals: LiveVitalsInput | None = None
) -> dict[str, str]:
    """Build the ElevenLabs dynamic-variable map injected into the call."""
    numbered = "\n".join(f"{i}. {q}" for i, q in enumerate(questions, start=1))
    return {
        # patient_id is opaque to the prompt but is the value the escalate_emergency
        # tool sends back to /integrations/elevenlabs/escalate to identify the patient.
        "patient_id": str(patient.id),
        "patient_name": patient.name,
        "patient_age": str(patient.age),
        "recent_summary": await build_recent_summary(patient.id, live_vitals),
        "questions": numbered,
        # Fixed opening question (asked first) and the verbatim privacy response,
        # both editable in their markdown files and read fresh on every call.
        "opening_question": _read_markdown_body(settings.opening_question_file),
        "privacy_response": _read_markdown_body(settings.privacy_response_file),
    }


async def build_call_payload(
    patient: Patient,
    to_number: str,
    questions: list[str],
    config: CallConfig,
    system_prompt: str | None = None,
    first_message: str | None = None,
    agent_id: str | None = None,
    live_vitals: LiveVitalsInput | None = None,
) -> dict:
    """Assemble the ElevenLabs outbound-call request body.

    ``agent_id`` selects which ElevenLabs agent answers; defaults to the check-in
    agent. A different agent (e.g. the cognitive-screening agent) dials out through
    the same registered phone number.
    """
    client_data: dict = {
        "dynamic_variables": await build_dynamic_variables(patient, questions, live_vitals),
    }
    overrides = build_overrides(config, system_prompt, first_message)
    if overrides:
        client_data["conversation_config_override"] = overrides
    return {
        "agent_id": agent_id or settings.elevenlabs_agent_id,
        "agent_phone_number_id": settings.elevenlabs_agent_phone_number_id,
        "to_number": to_number,
        "conversation_initiation_client_data": client_data,
    }


async def place_call(
    patient: Patient,
    to_number: str,
    questions: list[str],
    kind: str = "instant",
    system_prompt: str | None = None,
    first_message: str | None = None,
    agent_id: str | None = None,
    watch_for_emergency: bool = False,
    is_nurse_call: bool = False,
    live_vitals: LiveVitalsInput | None = None,
) -> CallRecord:
    """Place an outbound call and record the outcome in the call history.

    ``system_prompt``/``first_message`` override the agent persona for this one
    call (used to brief the nurse instead of speaking as the patient agent).
    ``agent_id`` selects a non-default agent (e.g. the cognitive-screening agent).

    ``watch_for_emergency`` spawns the server-side escalation safety net for this
    call (see ``app.escalation_watchdog``): set it ONLY for patient-facing calls,
    never for the nurse-alert call itself (that would loop). It guarantees the
    nurse is dialled if the patient reports an emergency even when the agent fails
    to invoke its ``escalate_emergency`` tool.

    ``is_nurse_call`` marks the outbound nurse-alert call (which dials the nurse and
    briefs them about the patient). Set it True there so we do NOT materialize that
    call as a patient check-in - its content is the nurse briefing, not the
    patient's own check-in. Every other (patient-facing) call materializes its
    check-in in the background as soon as the analysis is ready.
    """
    triggered_at = datetime.now()
    record_id = call_store.next_record_id()
    # Normalize to strict E.164 (strip spaces/dashes, ensure a leading +) before we
    # dial: ElevenLabs/Twilio reject anything that isn't bare E.164, so a number
    # entered as "+41 76 540 22 80" (nurse or patient) would otherwise fail at the
    # API. Done up front so the log, failure records, and payload all use the clean
    # value.
    to_number = data._normalize_phone(to_number)
    # One log line per placement makes "one click -> many calls" diagnosable: a
    # single user action must produce exactly one of these.
    logger.info(
        "place_call: id=%s patient=%s kind=%s to=%s",
        record_id, patient.id, kind, to_number,
    )

    def _failed(error: str) -> CallRecord:
        return call_store.add_call_record(
            CallRecord(
                id=record_id,
                patient_id=patient.id,
                triggered_at=triggered_at,
                kind=kind,
                to_number=to_number,
                status="failed",
                error=error,
            )
        )

    if not to_number:
        return _failed("No dialable phone number (empty after normalization).")
    if data.is_placeholder_phone(to_number):
        return _failed(
            f"Patient has no real phone number (placeholder {to_number}); refusing to dial."
        )
    if not settings.is_configured:
        return _failed("Telephony not configured. Set ELEVENLABS_* vars in backend/.env.")

    config = call_store.get_config(patient.id)
    payload = await build_call_payload(
        patient, to_number, questions, config, system_prompt, first_message, agent_id,
        live_vitals=live_vitals,
    )
    headers = {"xi-api-key": settings.elevenlabs_api_key}

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                settings.elevenlabs_outbound_url, json=payload, headers=headers
            )
        resp.raise_for_status()
        body = resp.json()
        if not body.get("success", False):
            raise RuntimeError(body.get("message") or "ElevenLabs reported failure")
        record = CallRecord(
            id=record_id,
            patient_id=patient.id,
            triggered_at=triggered_at,
            kind=kind,
            to_number=to_number,
            status="initiated",
            conversation_id=body.get("conversation_id"),
            call_sid=body.get("callSid"),
        )
    except Exception as exc:  # noqa: BLE001 - surface any failure to the record
        record = CallRecord(
            id=record_id,
            patient_id=patient.id,
            triggered_at=triggered_at,
            kind=kind,
            to_number=to_number,
            status="failed",
            error=str(exc),
        )

    saved = call_store.add_call_record(record)

    # Safety net: for a patient-facing call, watch the live transcript and dial the
    # nurse if an emergency surfaces - independent of the agent calling its tool.
    if watch_for_emergency and saved.status == "initiated" and saved.conversation_id:
        from .. import escalation_watchdog

        asyncio.create_task(
            escalation_watchdog.watch_conversation(patient, saved.conversation_id)
        )

    # Materialize this call's check-in in the background the moment ElevenLabs
    # finishes analysing it, so it lands in the patient's history (and feeds
    # question regeneration) without anyone opening the transcript first. Skip the
    # nurse-alert call - its content is the nurse briefing, not a patient check-in.
    if not is_nurse_call and saved.status == "initiated" and saved.conversation_id:
        from .. import conversation_store

        # Poll on a tight cadence so the check-in appears within seconds of the
        # call's analysis completing; attempts keep the ~10 min overall window.
        asyncio.create_task(
            conversation_store.ensure_materialized(
                saved.conversation_id, attempts=120, interval=5.0
            )
        )

    return saved
