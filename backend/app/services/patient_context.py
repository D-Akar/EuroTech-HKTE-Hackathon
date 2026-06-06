"""Assemble full patient health context for the ElevenLabs server tool."""

from __future__ import annotations

from .. import alerts, call_store, care_plan_store, data, summary, wearable_source
from ..models import CarePlanContext, Patient, PatientContextResponse


def build_context_summary(
    patient: Patient,
    checkins: list,
    wearables: list,
    alert_list: list[dict],
    call_config,
    care_plan: CarePlanContext | None = None,
) -> str:
    """Human-readable summary the agent can use during the call."""
    lines = [
        f"Patient: {patient.name}, age {patient.age}.",
        f"Care status: {patient.status.value}. Practice: {patient.practice}.",
        f"District: {patient.district or 'unknown'}.",
    ]

    if alert_list:
        lines.append("Active health alerts:")
        for a in alert_list:
            lines.append(f"- [{a['severity']}] {a['message']}")

    if checkins:
        lines.append("Phone check-in history (newest first):")
        for c in sorted(checkins, key=lambda x: x.date, reverse=True):
            answered = "answered" if c.answered else "no answer"
            lines.append(
                f"- {c.date.isoformat()}: mood {c.mood}, pain {c.pain_level}/10 "
                f"({answered}). Notes: {c.notes}"
            )

    if wearables:
        lines.append("Wearable readings (newest first):")
        for w in sorted(wearables, key=lambda x: x.timestamp, reverse=True):
            lines.append(
                f"- {w.timestamp.date().isoformat()}: heart rate {w.heart_rate} bpm, "
                f"{w.steps} steps, {w.sleep_hours}h sleep."
            )

    if call_config.questions:
        numbered = "; ".join(
            f"{i}. {q}" for i, q in enumerate(call_config.questions, start=1)
        )
        lines.append(f"Configured check-in questions: {numbered}")

    if call_config.greeting:
        lines.append(f"Custom greeting: {call_config.greeting}")

    if care_plan is not None:
        lines.append("")
        lines.append(care_plan.rendered_text)

    return "\n".join(lines)


def build_patient_context(patient: Patient) -> PatientContextResponse:
    """Collect all patient data from the mock layer into one response."""
    patient_id = patient.id
    checkins = data.get_checkins(patient_id)
    wearables = data.get_wearables(patient_id)
    vitals = (
        wearable_source.raw_samples()
        if patient_id == wearable_source.REAL_PATIENT_ID
        else []
    )
    alert_list = alerts.alerts_for(patient_id, wearables, vitals)
    summary_stats = summary.compute_summary(wearables, vitals)
    call_config = call_store.get_config(patient_id)
    stored_plan = care_plan_store.get(patient_id)
    care_plan = stored_plan.care_plan if stored_plan else None

    return PatientContextResponse(
        patient=patient,
        checkins=checkins,
        wearables=wearables,
        alerts=alert_list,
        summary=summary_stats,
        vitals=vitals,
        call_config=call_config,
        care_plan=care_plan,
        context_summary=build_context_summary(
            patient, checkins, wearables, alert_list, call_config, care_plan
        ),
    )
