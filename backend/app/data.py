"""In-memory dataset: patients, daily check-ins, and seeded wearables.

Patients, phone check-ins, and wearable readings are seeded deterministically so the
dashboard shows stable, believable history at city scale. ONE featured patient
(wearable_source.REAL_PATIENT_ID) is backed by the real Garmin device instead of the seed,
and its status is derived from real alerts.
"""

import random
from datetime import date, datetime, timedelta

from . import alerts, fhir_source, wearable_source
from .models import CheckIn, Patient, PatientStatus, WearableReading

_TODAY = date(2026, 6, 6)

# (name, age, status, practice, district) seed roster. Districts are real Hong Kong
# neighbourhoods; the frontend maps them onto the city twin.
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

# Synthetic seed numbers all share this prefix. They are NOT dialable - a real
# call must never be placed to one (see telephony.place_call guard).
PLACEHOLDER_PHONE_PREFIX = "+1000000"

PATIENTS: list[Patient] = [
    Patient(
        id=i + 1,
        name=name,
        age=age,
        status=status,
        practice=practice,
        district=district,
        phone_number=f"{PLACEHOLDER_PHONE_PREFIX}{i + 1:04d}",
    )
    for i, (name, age, status, practice, district) in enumerate(_SEED)
]


def is_placeholder_phone(number: str | None) -> bool:
    """True if the number is one of the synthetic seed numbers (not dialable)."""
    return bool(number) and _normalize_phone(number).startswith(PLACEHOLDER_PHONE_PREFIX)


# Mood / pain / wearable ranges keyed by status, so seeded numbers match the patient flag.
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
                    notes=rng.choice(prof["notes"]) if answered else "No answer - left voicemail.",
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


def _apply_featured_status() -> None:
    """Drive the featured patient's status flag from its real alerts."""
    fid = wearable_source.REAL_PATIENT_ID
    readings = wearable_source.daily_readings(fid)
    if not readings:
        return
    severity = alerts.worst_severity(alerts.alerts_for(fid, readings, wearable_source.raw_samples()))
    mapping = {"critical": PatientStatus.urgent, "warning": PatientStatus.attention}
    new_status = mapping.get(severity)
    if new_status is None:
        return
    for p in PATIENTS:
        if p.id == fid:
            p.status = new_status
            break


_apply_featured_status()

# Overlay real FHIR records (MongoDB) onto the slots listed in Prompts/featured_patients.md.
# Best-effort: a no-op if Mongo is unreachable or the file is empty, so the dashboard
# still shows the full mock roster. The live Garmin patient keeps its own data.
fhir_source.apply_overlays(PATIENTS, wearable_source.REAL_PATIENT_ID)


def _apply_real_patient_phone() -> None:
    """Point the featured (real-watch) patient at the configured demo phone, so the
    operator can be the patient and receive the live escalation call themselves.
    Applied after the FHIR overlay so it always wins for the demo."""
    from .config import settings

    number = settings.garmin_patient_phone.strip()
    if not number:
        return
    for p in PATIENTS:
        if p.id == wearable_source.REAL_PATIENT_ID:
            p.phone_number = number
            break


_apply_real_patient_phone()


def get_patients() -> list[Patient]:
    return PATIENTS


def get_patient(patient_id: int) -> Patient | None:
    return next((p for p in PATIENTS if p.id == patient_id), None)


def _normalize_phone(phone_number: str) -> str:
    """Normalize to E.164 for comparison (strip formatting, ensure leading +)."""
    stripped = "".join(c for c in phone_number.strip() if c.isdigit() or c == "+")
    if stripped.startswith("+"):
        return "+" + "".join(c for c in stripped[1:] if c.isdigit())
    digits = "".join(c for c in stripped if c.isdigit())
    return f"+{digits}" if digits else ""


def get_patient_by_phone(phone_number: str) -> Patient | None:
    normalized = _normalize_phone(phone_number)
    if not normalized:
        return None
    return next(
        (p for p in PATIENTS if _normalize_phone(p.phone_number) == normalized),
        None,
    )


def get_patient_by_subject(display: str) -> Patient | None:
    """Match a FHIR CarePlan.subject.display against a patient name."""
    if not display:
        return None
    target = display.strip().casefold()
    return next((p for p in PATIENTS if p.name.strip().casefold() == target), None)


def resolve_patient(identifier: int | str) -> Patient | None:
    """Resolve a patient by integer slot id, numeric string id, or exact name.

    The ElevenLabs ``escalate_emergency`` tool is meant to send the injected
    ``{{patient_id}}`` dynamic variable (a numeric slot id), but in practice the
    agent often fills it with the only identifier it knows from its prompt - the
    patient's name (``{{patient_name}}``). Accept both so a mid-call escalation is
    never lost to a type mismatch.
    """
    if isinstance(identifier, int):
        return get_patient(identifier)
    text = str(identifier).strip()
    if text.isdigit():
        return get_patient(int(text))
    return get_patient_by_subject(text)


def get_checkins(patient_id: int) -> list[CheckIn]:
    return [c for c in CHECKINS if c.patient_id == patient_id]


def get_wearables(patient_id: int) -> list[WearableReading]:
    # Featured patient -> real Garmin trends; everyone else -> seeded data.
    if patient_id == wearable_source.REAL_PATIENT_ID:
        real = wearable_source.daily_readings(patient_id)
        if real:
            return real
    return [w for w in WEARABLES if w.patient_id == patient_id]
