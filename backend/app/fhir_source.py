"""Bind real FHIR patient records (MongoDB) onto dashboard patient slots.

A markdown file (``FEATURED_PATIENTS_FILE``, default ``<repo>/featured_patients.md``)
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
# random age in this range — many Synthea records are far younger than the elderly
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

    Tolerant of bullets, headings, and blank lines — we just scan each non-heading
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


def _display_name(raw: str) -> str:
    """Strip Synthea's numeric suffixes, e.g. 'Josefina523 Deckow585' -> 'Josefina Deckow'."""
    parts = [re.sub(r"\d+$", "", token) for token in raw.split()]
    cleaned = " ".join(p for p in parts if p)
    return cleaned or raw


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
    slot — skipping ``featured_id`` (the live Garmin patient) — gets the real name,
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
    for fhir_id in ids:
        doc = docs.get(fhir_id)
        if doc is None:
            continue  # listed but not in Mongo — leave that slot mock
        if bound >= len(slots):
            break  # more ids than slots; ignore the overflow
        slot = slots[bound]
        bound += 1

        demo = doc.get("demographics") or {}
        if demo.get("name"):
            slot.name = _display_name(demo["name"])
        # Always assign a random elderly age (>= 65); the synthetic birth dates
        # often make these patients far too young for an elderly-care dashboard.
        age = _elderly_age(fhir_id)
        slot.age = age
        if demo.get("phone_number"):
            slot.phone_number = demo["phone_number"]
        slot.fhir_id = fhir_id
        _PROFILES[slot.id] = _build_profile(slot.id, fhir_id, doc, age)

    return bound


def get_profile(patient_id: int) -> MedicalProfile | None:
    """The real clinical record for an FHIR-backed slot, or None if it's mock."""
    return _PROFILES.get(patient_id)
