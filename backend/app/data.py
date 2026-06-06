"""In-memory mock dataset.

Seeded at import time so the API has realistic-looking data without a database.
Resets on every restart. Replace with a real datastore later.

The roster is sized and spread across Hong Kong districts so the dashboard's city
"digital twin" reads as genuinely city-scale. Per-patient check-ins and wearable
readings are generated deterministically from the patient id, so every patient a
coordinator clicks into shows believable history (and the same history every restart).
"""

import random
from datetime import date, datetime, timedelta

from .models import CheckIn, Patient, PatientStatus, WearableReading

_TODAY = date(2026, 6, 6)

# (name, age, status, practice, district) — the seed roster.
# Districts are real Hong Kong neighbourhoods; the frontend maps them onto the twin.
_SEED: list[tuple[str, int, PatientStatus, str, str]] = [
    ("Margaret Holloway", 82, PatientStatus.stable, "Riverside Geriatric Care", "Central"),
    ("Arthur Chen", 77, PatientStatus.attention, "Riverside Geriatric Care", "Wan Chai"),
    ("Dorothy Williams", 89, PatientStatus.urgent, "Oakwood Outpatient Clinic", "Mong Kok"),
    ("Giuseppe Romano", 74, PatientStatus.stable, "Oakwood Outpatient Clinic", "Tsim Sha Tsui"),
    ("Wong Mei-ling", 84, PatientStatus.stable, "Harbour Care Collective", "Sheung Wan"),
    ("Chan Kwok-wah", 79, PatientStatus.attention, "Harbour Care Collective", "Causeway Bay"),
    ("Eleanor Pang", 86, PatientStatus.stable, "Riverside Geriatric Care", "North Point"),
    ("Henry Fitzgerald", 81, PatientStatus.stable, "Oakwood Outpatient Clinic", "Quarry Bay"),
    ("Lau Siu-fong", 88, PatientStatus.urgent, "Harbour Care Collective", "Sham Shui Po"),
    ("Beatrice Okonkwo", 76, PatientStatus.stable, "Riverside Geriatric Care", "Yau Ma Tei"),
    ("Tomoko Ishida", 83, PatientStatus.attention, "Oakwood Outpatient Clinic", "Kowloon City"),
    ("Walter Brennan", 90, PatientStatus.stable, "Harbour Care Collective", "Aberdeen"),
    ("Ng Pui-shan", 78, PatientStatus.stable, "Riverside Geriatric Care", "Stanley"),
    ("Raymond Carter", 80, PatientStatus.attention, "Oakwood Outpatient Clinic", "The Peak"),
    ("Cheung Wai-man", 85, PatientStatus.stable, "Harbour Care Collective", "Central"),
    ("Agnes Murphy", 87, PatientStatus.stable, "Riverside Geriatric Care", "Wan Chai"),
    ("Ko Tin-yau", 73, PatientStatus.stable, "Oakwood Outpatient Clinic", "Causeway Bay"),
    ("Frances Adeyemi", 82, PatientStatus.urgent, "Harbour Care Collective", "Tsim Sha Tsui"),
    ("Leung Ka-ho", 79, PatientStatus.stable, "Riverside Geriatric Care", "North Point"),
    ("Ingrid Larsson", 84, PatientStatus.attention, "Oakwood Outpatient Clinic", "Sheung Wan"),
    ("Yip Lai-kuen", 91, PatientStatus.stable, "Harbour Care Collective", "Mong Kok"),
    ("Charles Dube", 75, PatientStatus.stable, "Riverside Geriatric Care", "Sham Shui Po"),
    ("Tang Shun-kei", 86, PatientStatus.stable, "Oakwood Outpatient Clinic", "Kowloon City"),
    ("Rosa Iglesias", 88, PatientStatus.attention, "Harbour Care Collective", "Quarry Bay"),
    ("Fung Yuk-ying", 80, PatientStatus.stable, "Riverside Geriatric Care", "Yau Ma Tei"),
    ("Patrick O'Sullivan", 83, PatientStatus.stable, "Oakwood Outpatient Clinic", "Aberdeen"),
    ("Sit Wing-chi", 77, PatientStatus.stable, "Harbour Care Collective", "Stanley"),
    ("Helga Brandt", 89, PatientStatus.urgent, "Riverside Geriatric Care", "Causeway Bay"),
    ("Mo Chi-keung", 81, PatientStatus.stable, "Oakwood Outpatient Clinic", "Central"),
    ("Vera Stankovic", 85, PatientStatus.attention, "Harbour Care Collective", "Wan Chai"),
]

PATIENTS: list[Patient] = [
    Patient(
        id=i + 1,
        name=name,
        age=age,
        status=status,
        practice=practice,
        district=district,
        phone_number=f"+1000000{i + 1:04d}",
    )
    for i, (name, age, status, practice, district) in enumerate(_SEED)
]


# --- Procedural per-patient history -----------------------------------------
#
# Mood / pain / wearable ranges keyed by status, so the numbers a coordinator
# sees line up with the patient's flag. Seeded by patient id for stability.

_PROFILE = {
    PatientStatus.stable: {
        "moods": ["cheerful", "content", "upbeat", "calm", "content"],
        "pain": (0, 2),
        "hr": (64, 78),
        "steps": (2000, 4200),
        "sleep": (7.0, 8.6),
        "answer_rate": 0.92,
        "notes": [
            "Feeling good, went for a short walk.",
            "Slept well, no complaints.",
            "Enjoyed a visit from family.",
            "Cooking again, in good spirits.",
            "Steady day, no concerns.",
        ],
    },
    PatientStatus.attention: {
        "moods": ["anxious", "low", "okay", "tired", "unsettled"],
        "pain": (3, 5),
        "hr": (82, 96),
        "steps": (500, 1500),
        "sleep": (5.0, 6.6),
        "answer_rate": 0.7,
        "notes": [
            "Reports dizziness when standing.",
            "Mild headache, took paracetamol.",
            "A bit tired but managing.",
            "Slightly short of breath this morning.",
            "Appetite lower than usual.",
        ],
    },
    PatientStatus.urgent: {
        "moods": ["distressed", "low", "in pain", "weak", "low"],
        "pain": (6, 9),
        "hr": (98, 116),
        "steps": (80, 480),
        "sleep": (3.4, 5.0),
        "answer_rate": 0.85,
        "notes": [
            "Severe chest discomfort reported.",
            "Pain worsening, struggling to sleep.",
            "Increasing back pain, low mobility.",
            "Confused and unsteady on the call.",
            "Has not eaten since yesterday.",
        ],
    },
}

_HISTORY_DAYS = 4


def _build_history() -> tuple[list[CheckIn], list[WearableReading]]:
    checkins: list[CheckIn] = []
    wearables: list[WearableReading] = []
    for p in PATIENTS:
        rng = random.Random(p.id)
        prof = _PROFILE[p.status]
        for day in range(_HISTORY_DAYS):
            d = _TODAY - timedelta(days=day)
            answered = rng.random() < prof["answer_rate"]
            checkins.append(
                CheckIn(
                    id=p.id * 100 + day,
                    patient_id=p.id,
                    date=d,
                    mood=rng.choice(prof["moods"]),
                    pain_level=rng.randint(*prof["pain"]),
                    answered=answered,
                    notes=(
                        rng.choice(prof["notes"])
                        if answered
                        else "No answer — left voicemail."
                    ),
                )
            )
            wearables.append(
                WearableReading(
                    id=p.id * 1000 + day,
                    patient_id=p.id,
                    timestamp=datetime.combine(d, datetime.min.time()).replace(hour=9),
                    heart_rate=rng.randint(*prof["hr"]),
                    steps=rng.randint(*prof["steps"]),
                    sleep_hours=round(rng.uniform(*prof["sleep"]), 1),
                )
            )
    return checkins, wearables


CHECKINS, WEARABLES = _build_history()


def get_patients() -> list[Patient]:
    return PATIENTS


def get_patient(patient_id: int) -> Patient | None:
    return next((p for p in PATIENTS if p.id == patient_id), None)


def get_checkins(patient_id: int) -> list[CheckIn]:
    return [c for c in CHECKINS if c.patient_id == patient_id]


def get_wearables(patient_id: int) -> list[WearableReading]:
    return [w for w in WEARABLES if w.patient_id == patient_id]
