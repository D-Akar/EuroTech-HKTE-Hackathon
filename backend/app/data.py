"""In-memory mock dataset.

Seeded at import time so the API has realistic-looking data without a database.
Resets on every restart. Replace with a real datastore later.
"""

from datetime import date, datetime, timedelta

from .models import CheckIn, Patient, PatientStatus, WearableReading

PATIENTS: list[Patient] = [
    Patient(id=1, name="Margaret Holloway", age=82, status=PatientStatus.stable,
            practice="Riverside Geriatric Care", phone_number="+10000000001"),
    Patient(id=2, name="Arthur Chen", age=77, status=PatientStatus.attention,
            practice="Riverside Geriatric Care", phone_number="+10000000002"),
    Patient(id=3, name="Dorothy Williams", age=89, status=PatientStatus.urgent,
            practice="Oakwood Outpatient Clinic", phone_number="+10000000003"),
    Patient(id=4, name="Giuseppe Romano", age=74, status=PatientStatus.stable,
            practice="Oakwood Outpatient Clinic", phone_number="+10000000004"),
]

_TODAY = date(2026, 6, 6)


def _checkins_for(patient_id: int, days: list[tuple[int, str, int, bool, str]],
                  start_id: int) -> list[CheckIn]:
    out: list[CheckIn] = []
    for offset, (cid_offset, mood, pain, answered, notes) in enumerate(_index(days)):
        out.append(CheckIn(
            id=start_id + cid_offset,
            patient_id=patient_id,
            date=_TODAY - timedelta(days=offset),
            mood=mood,
            pain_level=pain,
            answered=answered,
            notes=notes,
        ))
    return out


def _index(rows):
    """Yield (running_index, row) pairs for the check-in rows below."""
    for i, row in enumerate(rows):
        yield (i, *row)


# (mood, pain_level, answered, notes) — most-recent first
CHECKINS: list[CheckIn] = [
    *_checkins_for(1, [
        ("cheerful", 1, True, "Feeling good, went for a short walk."),
        ("content", 2, True, "Slept well, no complaints."),
        ("tired", 3, True, "A bit tired but managing."),
    ], start_id=100),
    *_checkins_for(2, [
        ("anxious", 5, True, "Reports dizziness when standing."),
        ("low", 4, False, "No answer — left voicemail."),
        ("okay", 3, True, "Mild headache, took paracetamol."),
    ], start_id=200),
    *_checkins_for(3, [
        ("distressed", 8, True, "Severe chest discomfort reported."),
        ("low", 7, True, "Pain worsening, struggling to sleep."),
        ("low", 6, True, "Increasing back pain."),
    ], start_id=300),
    *_checkins_for(4, [
        ("upbeat", 0, True, "Great spirits, cooking again."),
        ("content", 1, True, "Enjoyed family visit."),
        ("content", 1, False, "No answer — will retry."),
    ], start_id=400),
]


def _wearables_for(patient_id: int, rows: list[tuple[int, int, float]],
                   start_id: int) -> list[WearableReading]:
    out: list[WearableReading] = []
    for i, (hr, steps, sleep) in enumerate(rows):
        out.append(WearableReading(
            id=start_id + i,
            patient_id=patient_id,
            timestamp=datetime.combine(_TODAY - timedelta(days=i),
                                       datetime.min.time()).replace(hour=9),
            heart_rate=hr,
            steps=steps,
            sleep_hours=sleep,
        ))
    return out


# (heart_rate, steps, sleep_hours) — most-recent first
WEARABLES: list[WearableReading] = [
    *_wearables_for(1, [(72, 2400, 7.5), (70, 2100, 7.8), (74, 1800, 6.9)], start_id=1000),
    *_wearables_for(2, [(91, 600, 5.2), (88, 750, 5.8), (84, 900, 6.1)], start_id=2000),
    *_wearables_for(3, [(108, 120, 3.9), (102, 200, 4.4), (99, 300, 4.8)], start_id=3000),
    *_wearables_for(4, [(68, 3500, 8.1), (69, 3200, 7.9), (71, 3000, 8.0)], start_id=4000),
]


def get_patients() -> list[Patient]:
    return PATIENTS


def get_patient(patient_id: int) -> Patient | None:
    return next((p for p in PATIENTS if p.id == patient_id), None)


def get_checkins(patient_id: int) -> list[CheckIn]:
    return [c for c in CHECKINS if c.patient_id == patient_id]


def get_wearables(patient_id: int) -> list[WearableReading]:
    return [w for w in WEARABLES if w.patient_id == patient_id]
