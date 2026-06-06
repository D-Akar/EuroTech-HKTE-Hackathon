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
    # Set when this dashboard slot is backed by a real FHIR record in MongoDB
    # (see app/fhir_source.py). None for mock patients.
    fhir_id: str | None = None


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


class MedicalProfile(BaseModel):
    """The clinical record pulled from a patient's FHIR document in MongoDB."""

    patient_id: int  # dashboard slot id
    fhir_id: str  # MongoDB _id (patient UUID)
    gender: str | None = None
    birth_date: str | None = None
    preferred_language: str | None = None
    chronic_conditions: list[Condition] = []
    allergies: list[Allergy] = []
    active_medications: list[Medication] = []


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
