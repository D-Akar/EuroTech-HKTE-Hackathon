"""Pydantic schemas for the elderly-care platform wireframe.

These mirror the mock data shapes and are shared by the frontend via the
matching TypeScript definitions in ``frontend/src/types.ts``.
"""

from datetime import date, datetime
from enum import Enum
from typing import Literal

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
    greeting: str | None = None  # optional custom opening line


class ConfigUpdate(BaseModel):
    """Request body to update a patient's call config."""

    questions: list[str]
    greeting: str | None = None


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
