"""Pydantic schemas for the elderly-care platform wireframe.

These mirror the mock data shapes and are shared by the frontend via the
matching TypeScript definitions in ``frontend/src/types.ts``.
"""

from datetime import date, datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel


class PatientStatus(str, Enum):
    """Overall health flag a practice sees at a glance."""

    stable = "stable"
    attention = "attention"
    urgent = "urgent"


class Patient(BaseModel):
    id: int
    name: str
    age: int
    status: PatientStatus
    practice: str
    district: str = ""  # Hong Kong district the patient lives in (for the city twin)
    phone_number: str = ""  # E.164 number the check-in call is placed to
    # Set when this dashboard slot is backed by a real FHIR record in MongoDB
    # (see app/fhir_source.py). None for mock patients.
    fhir_id: str | None = None


class PhoneUpdate(BaseModel):
    """Request body to change a patient's check-in phone number."""

    phone_number: str


# --- Real FHIR medical profile (MongoDB-backed patients) ---------------------


class Condition(BaseModel):
    name: str
    onset_date: str | None = None


class Medication(BaseModel):
    name: str
    frequency: str | None = None
    prescribed_date: str | None = None


class Allergy(BaseModel):
    substance: str
    type: str | None = None
    criticality: str | None = None


class Procedure(BaseModel):
    name: str
    date: str | None = None


class MedicalProfile(BaseModel):
    """The clinical record pulled from a patient's FHIR document in MongoDB."""

    patient_id: int  # dashboard slot id
    fhir_id: str  # MongoDB _id (patient UUID)
    gender: str | None = None
    birth_date: str | None = None
    preferred_language: str | None = None
    phone_number: str | None = None
    chronic_conditions: list[Condition] = []
    allergies: list[Allergy] = []
    active_medications: list[Medication] = []
    past_medications: list[Medication] = []
    recent_procedures: list[Procedure] = []


class CheckIn(BaseModel):
    """A daily phone-call health check-in."""

    id: int
    patient_id: int
    date: date
    mood: str
    pain_level: int  # 0-10 self-reported
    answered: bool  # did the patient pick up the call?
    notes: str


class WearableReading(BaseModel):
    """A point-in-time reading from a patient's wearable device."""

    id: int
    patient_id: int
    timestamp: datetime
    heart_rate: int  # bpm
    steps: int  # steps so far that day
    sleep_hours: float  # previous night


# --- Outbound check-in calls (ElevenLabs + Twilio) ---------------------------


class CallConfig(BaseModel):
    """Per-patient configuration for the AI check-in call."""

    patient_id: int
    questions: list[str]  # the practice's questions for the agent to ask
    greeting: str | None = None  # optional custom opening line (first_message override)
    system_prompt: str | None = None  # optional agent system-prompt override


class ConfigUpdate(BaseModel):
    """Request body to update a patient's call config."""

    questions: list[str]
    greeting: str | None = None
    system_prompt: str | None = None


class TriggerRequest(BaseModel):
    """Request body for an instant 'Call now'."""

    to_number: str | None = None  # overrides the patient's stored number
    questions: list[str] | None = None  # overrides the stored config


class ScheduleRequest(BaseModel):
    """Request body to schedule a call."""

    scheduled_at: datetime
    recurring: bool = False  # True == repeat daily at scheduled_at's time


class ScheduledCall(BaseModel):
    id: int
    patient_id: int
    scheduled_at: datetime
    recurring: bool  # daily when True
    status: Literal["pending", "cancelled"]
    questions: list[str]


class CallRecord(BaseModel):
    """A historical record of one placed (or attempted) call."""

    id: int
    patient_id: int
    triggered_at: datetime
    kind: Literal["instant", "scheduled"]
    to_number: str
    status: Literal["initiated", "failed"]
    conversation_id: str | None = None
    call_sid: str | None = None
    error: str | None = None


# --- Real-time clinical escalation -------------------------------------------


class EscalationRequest(BaseModel):
    """Trigger body: urgent information surfaced (e.g. during a phone call)."""

    reason: str  # what was learned that makes this urgent
    source: str = "phone_call"  # where the urgent info came from
    notify_nurse: bool = True  # place an outbound alert call to a nurse
    nurse_number: str | None = None  # overrides the configured nurse line


class EscalationRecord(BaseModel):
    """The outcome of an escalation: status flip + the nurse alert call."""

    id: int
    patient_id: int
    patient_name: str
    reason: str
    source: str
    previous_status: PatientStatus
    status: PatientStatus  # always ``urgent`` after escalation
    triggered_at: datetime
    nurse_call: CallRecord | None = None  # None when notify_nurse is False / no line


# --- Conversation detail (post-call data pulled back from ElevenLabs) ---------


class ConversationTurn(BaseModel):
    """One turn in the call transcript."""

    role: Literal["user", "agent"]
    message: str | None = None
    time_in_call_secs: int | None = None


class ConversationDataPoint(BaseModel):
    """One structured value extracted from the call by the agent's data collection."""

    id: str  # the data_collection identifier, e.g. "pain_level"
    value: Any = None  # str | int | bool | None, as returned by ElevenLabs
    rationale: str | None = None


class ConversationDetail(BaseModel):
    """What happened in one outbound call, fetched from the ElevenLabs API."""

    conversation_id: str
    status: str  # initiated | in-progress | processing | done | failed
    ready: bool  # True once status == "done"
    transcript_summary: str | None = None
    call_successful: str | None = None  # success | failure | unknown
    call_duration_secs: int | None = None
    started_at: datetime | None = None
    transcript: list[ConversationTurn] = []
    data_collection: list[ConversationDataPoint] = []


# --- ElevenLabs server-tool integration --------------------------------------


class PatientContextResponse(BaseModel):
    """Full patient health context returned to the ElevenLabs agent."""

    patient: Patient
    checkins: list[CheckIn]
    wearables: list[WearableReading]
    alerts: list[dict]
    summary: dict
    vitals: list[dict]
    call_config: CallConfig
    context_summary: str
    care_plan: "CarePlanContext | None" = None


# --- FHIR care plans ---------------------------------------------------------


class CarePlanGoal(BaseModel):
    description: str
    target: str | None = None


class CarePlanActivity(BaseModel):
    description: str
    status: str | None = None
    scheduled: str | None = None


class CarePlanContext(BaseModel):
    """Human-relevant fields extracted from a FHIR CarePlan."""

    title: str | None = None
    status: str | None = None
    intent: str | None = None
    description: str | None = None
    categories: list[str] = []
    subject_display: str | None = None  # used to auto-match a patient
    period_start: str | None = None
    period_end: str | None = None
    addresses: list[str] = []  # conditions the plan targets
    goals: list[CarePlanGoal] = []
    activities: list[CarePlanActivity] = []
    notes: list[str] = []
    rendered_text: str  # deterministic prose for the agent


class StoredCarePlan(BaseModel):
    care_plan: CarePlanContext
    raw: str  # original uploaded document
    uploaded_at: datetime


# Resolve forward reference in PatientContextResponse now that CarePlanContext is defined.
PatientContextResponse.model_rebuild()
