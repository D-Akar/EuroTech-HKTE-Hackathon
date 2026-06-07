"""Bind real FHIR patient records (MongoDB) onto dashboard patient slots.

A markdown file (``FEATURED_PATIENTS_FILE``, default ``<repo>/Prompts/featured_patients.md``)
lists MongoDB patient ``_id``s. Each listed id is bound, in listing order, to a
dashboard patient slot (skipping the live Garmin patient), so that slot shows the
real person's demographics + medical profile pulled from Mongo. Everything not
listed stays mock.

All Mongo access is **best-effort**: if the database is unreachable or an id is
missing, the slot simply keeps its mock identity. The app never fails to boot just
because Mongo is down or the file is empty.
"""

from __future__ import annotations

import random
import re

from .config import settings
from .models import Allergy, Condition, MedicalProfile, Medication, Patient, Procedure

# Cap the long historical lists so the /profile payload stays small; we keep the
# most recent entries (FHIR records can carry hundreds of procedures).
_MAX_PAST_MEDICATIONS = 15
_MAX_RECENT_PROCEDURES = 20

# Featured patients are shown as an elderly-care cohort, so every bound slot gets a
# random age in this range - many Synthea records are far younger than the elderly
# outpatients this platform serves.
_MIN_AGE = 65
_MAX_AGE = 92
# The app runs against a fixed "today" (see data.py); birth years are derived from
# the assigned age relative to this so the profile's birth date matches the age.
_REFERENCE_YEAR = 2026

# Standard 8-4-4-4-12 hex UUID, as used for the FHIR _id / filename stem.
_UUID_RE = re.compile(
    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
)

# patient slot id -> the real clinical record, populated by apply_overlays().
_PROFILES: dict[int, MedicalProfile] = {}


def read_featured_ids() -> list[str]:
    """Parse the markdown file into an ordered, de-duplicated list of UUIDs.

    Tolerant of bullets, headings, and blank lines - we just scan each non-heading
    line for the first UUID-shaped token.
    """
    path = settings.featured_patients_file
    try:
        with open(path, encoding="utf-8") as fh:
            lines = fh.readlines()
    except OSError:
        return []

    ids: list[str] = []
    seen: set[str] = set()
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        match = _UUID_RE.search(stripped)
        if match:
            uuid = match.group(0).lower()
            if uuid not in seen:
                seen.add(uuid)
                ids.append(uuid)
    return ids


def _fetch(ids: list[str]) -> dict[str, dict]:
    """Fetch the FHIR documents for ``ids`` from Mongo, keyed by _id.

    Returns {} on any connection/query failure so callers degrade to mock data.
    """
    if not ids:
        return {}
    try:
        from pymongo import MongoClient
        from pymongo.errors import PyMongoError
    except ImportError:
        return {}

    try:
        # Short timeout: don't stall app boot if Mongo isn't running.
        client = MongoClient(settings.mongodb_uri, serverSelectionTimeoutMS=1500)
        col = client[settings.mongodb_db][settings.fhir_collection]
        docs = {doc["_id"]: doc for doc in col.find({"_id": {"$in": ids}})}
        client.close()
        return docs
    except PyMongoError:
        return {}
    except Exception:
        # Any unexpected driver/network error -> fall back to mock silently.
        return {}


# The featured FHIR records are synthetic (Synthea) and carry Western names. For the
# Hong Kong elderly-care demo we overlay authentic local names instead, written
# surname-first in the usual romanised-Cantonese style. Names are picked by the
# record's gender (so name and gender stay consistent) and assigned in stable bind
# order, so each slot keeps the same name across restarts.
_HK_NAMES_FEMALE = [
    "Wong Mei-ling", "Chan Lai-kuen", "Lee Yuk-ying", "Cheung Pui-shan",
    "Lam Wai-han", "Ng Siu-fong", "Ho Suk-yee", "Tang Wai-fong",
    "Leung Kit-ying", "Lau Lai-chu", "Yip Foon-yee", "Tsang Po-chu",
    "Fung Sau-lan", "Cheng Mei-fong", "Mak Yuet-wah", "Choi Lan-ying",
    "Yeung Oi-lin", "Hui Wai-chu", "Lo Yim-fong", "Sin Muk-lan",
]
_HK_NAMES_MALE = [
    "Chan Kwok-wah", "Wong Tin-yau", "Leung Ka-ho", "Lee Chi-keung",
    "Tang Shun-kei", "Cheung Wing-chi", "Ho Kwok-keung", "Lam Chi-ming",
    "Ng Wai-keung", "Lau Ho-yin", "Yip Kam-fai", "Kwok Siu-ming",
    "Tsang Yiu-fai", "Tam Cheuk-man", "Yuen Chun-kit", "So Man-tat",
    "Au Yiu-cheung", "Pang Chun-wah", "Lai Kwok-on", "Tse Wing-hong",
]


def _hk_name(gender: str | None, female_idx: int, male_idx: int) -> str:
    """An authentic Hong Kong demo name matching the record's gender."""
    if (gender or "").strip().lower().startswith("f"):
        return _HK_NAMES_FEMALE[female_idx % len(_HK_NAMES_FEMALE)]
    return _HK_NAMES_MALE[male_idx % len(_HK_NAMES_MALE)]


def _elderly_age(seed: str) -> int:
    """A stable random age >= 65 for a featured patient, seeded by their FHIR id.

    Seeding by id keeps each patient's displayed age the same across restarts
    instead of changing on every boot.
    """
    return random.Random(seed).randint(_MIN_AGE, _MAX_AGE)


def _birth_date_for_age(age: int, original: str | None) -> str:
    """A birth_date string consistent with the assigned age.

    Keeps the real month/day from the FHIR record when available (so it still looks
    natural) but sets the year so the patient is ``age`` as of the reference date.
    """
    md = "01-01"
    if original:
        parts = original.split("-")
        if len(parts) >= 3 and parts[1] and parts[2]:
            md = f"{parts[1]}-{parts[2]}"
    return f"{_REFERENCE_YEAR - age:04d}-{md}"


def _build_profile(patient_id: int, fhir_id: str, doc: dict, age: int) -> MedicalProfile:
    demo = doc.get("demographics") or {}
    past_meds = sorted(
        (m for m in doc.get("past_medications", []) if m.get("name")),
        key=lambda m: m.get("prescribed_date") or "",
        reverse=True,
    )
    procedures = sorted(
        (p for p in doc.get("recent_procedures", []) if p.get("name")),
        key=lambda p: p.get("date") or "",
        reverse=True,
    )
    return MedicalProfile(
        patient_id=patient_id,
        fhir_id=fhir_id,
        gender=demo.get("gender"),
        birth_date=_birth_date_for_age(age, demo.get("birth_date")),
        preferred_language=demo.get("preferred_language"),
        phone_number=demo.get("phone_number"),
        chronic_conditions=[
            Condition(name=c["name"], onset_date=c.get("onset_date"))
            for c in doc.get("chronic_conditions", [])
            if c.get("name")
        ],
        allergies=[
            Allergy(
                substance=a["substance"],
                type=a.get("type"),
                criticality=a.get("criticality"),
            )
            for a in doc.get("allergies", [])
            if a.get("substance")
        ],
        active_medications=[
            Medication(name=m["name"], frequency=m.get("frequency"))
            for m in doc.get("active_medications", [])
            if m.get("name")
        ],
        past_medications=[
            Medication(name=m["name"], prescribed_date=m.get("prescribed_date"))
            for m in past_meds[:_MAX_PAST_MEDICATIONS]
        ],
        recent_procedures=[
            Procedure(name=p["name"], date=p.get("date"))
            for p in procedures[:_MAX_RECENT_PROCEDURES]
        ],
    )


def apply_overlays(patients: list[Patient], featured_id: int | None = None) -> int:
    """Overlay real FHIR data onto dashboard slots, in place.

    For each UUID listed in the markdown file (in order), the next available patient
    slot - skipping ``featured_id`` (the live Garmin patient) - gets the real name,
    age, and a medical profile. Returns the number of slots bound.
    """
    _PROFILES.clear()
    ids = read_featured_ids()
    docs = _fetch(ids)
    if not docs:
        return 0

    # Stable slot order by id, excluding the live Garmin patient.
    slots = [p for p in sorted(patients, key=lambda p: p.id) if p.id != featured_id]

    bound = 0
    female_idx = 0
    male_idx = 0
    for fhir_id in ids:
        doc = docs.get(fhir_id)
        if doc is None:
            continue  # listed but not in Mongo - leave that slot mock
        if bound >= len(slots):
            break  # more ids than slots; ignore the overflow
        slot = slots[bound]
        bound += 1

        demo = doc.get("demographics") or {}
        gender = demo.get("gender")
        slot.name = _hk_name(gender, female_idx, male_idx)
        if (gender or "").strip().lower().startswith("f"):
            female_idx += 1
        else:
            male_idx += 1
        # Always assign a random elderly age (>= 65); the synthetic birth dates
        # often make these patients far too young for an elderly-care dashboard.
        age = _elderly_age(fhir_id)
        slot.age = age
        if demo.get("phone_number"):
            slot.phone_number = demo["phone_number"]
        slot.fhir_id = fhir_id
        _PROFILES[slot.id] = _build_profile(slot.id, fhir_id, doc, age)

    # Right-to-erasure: keep tombstoned slots redacted across restarts, even though
    # the overlay above just re-bound them from the read-only FHIR source.
    from . import erasure_store  # local import avoids an import cycle

    for slot in slots:
        if erasure_store.is_erased(slot.id):
            slot.name = "[erased]"
            slot.phone_number = ""
            slot.fhir_id = None
            _PROFILES.pop(slot.id, None)

    return bound


# Synthetic clinical record for the live-Garmin / demo patient (Pang Wai-kuen),
# who is skipped by the MongoDB overlay but should still read like a full FHIR-backed
# patient on the dashboard. Conditions are drawn from the worsening-symptom guide so
# the tailored-question generator has real material to cross-reference.
_FEATURED_FHIR_ID = "live-garmin-pang-wai-kuen"


def apply_featured_profile(patients: list[Patient], featured_id: int) -> None:
    """Give the featured (live-Garmin) patient a believable medical profile so it
    matches the other patients (medical tab + FHIR tag + condition-tailored questions),
    even though it is skipped by the MongoDB overlay. Best-effort, in place."""
    from . import erasure_store  # local import avoids an import cycle

    if erasure_store.is_erased(featured_id):
        return
    slot = next((p for p in patients if p.id == featured_id), None)
    if slot is None:
        return

    profile = MedicalProfile(
        patient_id=featured_id,
        fhir_id=_FEATURED_FHIR_ID,
        gender="male",
        birth_date=_birth_date_for_age(slot.age, "1940-03-12"),
        preferred_language="Cantonese",
        chronic_conditions=[
            Condition(name="Essential hypertension", onset_date="2014-06-18"),
            Condition(name="Type 2 diabetes mellitus", onset_date="2017-03-09"),
            Condition(name="Osteoarthritis", onset_date="2019-11-22"),
        ],
        allergies=[
            Allergy(substance="Penicillin", type="medication", criticality="high"),
        ],
        active_medications=[
            Medication(name="Amlodipine 5mg", frequency="Once daily"),
            Medication(name="Metformin 500mg", frequency="Twice daily"),
            Medication(name="Paracetamol 500mg", frequency="As needed for pain"),
        ],
        past_medications=[
            Medication(name="Lisinopril 10mg", prescribed_date="2012-05-01"),
            Medication(name="Ibuprofen 400mg", prescribed_date="2018-08-14"),
        ],
        recent_procedures=[
            Procedure(name="Cataract surgery (right eye)", date="2024-02-15"),
            Procedure(name="Influenza vaccination", date="2025-10-03"),
        ],
    )
    slot.fhir_id = _FEATURED_FHIR_ID
    _PROFILES[featured_id] = profile


def get_profile(patient_id: int) -> MedicalProfile | None:
    """The real clinical record for an FHIR-backed slot, or None if it's mock."""
    return _PROFILES.get(patient_id)
