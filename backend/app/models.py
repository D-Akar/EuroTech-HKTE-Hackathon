"""Pydantic schemas for the elderly-care platform wireframe.

These mirror the mock data shapes and are shared by the frontend via the
matching TypeScript definitions in ``frontend/src/types.ts``.
"""

from datetime import date, datetime
from enum import Enum

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
