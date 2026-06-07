"""Minimal FHIR R4 read surface — the technical bridge to Hong Kong's eHRSS.

eHealth's stated direction is HL7 → FHIR ("Advancing from HL7 to FHIR", 2021), and
patient-generated / wearable data is the gap the Primary Healthcare Blueprint names.
This router makes CareLoop *accreditation-ready* by exposing its data as FHIR R4
resources with proper LOINC codes, so connecting to eHRSS is a conformance exercise
rather than a re-architecture. See PRIVACY.md §6 and docs/hk-ehealth-market.md.

> Honest scope: this is a **read** surface over our own data for interoperability /
> portability. It is **not** an eHRSS connection — no third party can connect today
> (gated behind government accreditation).

Resources: ``GET /fhir/metadata`` (CapabilityStatement), ``GET /fhir/Patient/{id}``,
``GET /fhir/Observation?patient={id}`` (LOINC-coded wearable vitals).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from .. import data
from ..config import settings
from ..security.auth import require_role

router = APIRouter(prefix="/fhir", tags=["fhir"])

# LOINC codes for the wearable vitals we emit as FHIR Observations.
_LOINC = {
    "heart_rate": ("8867-4", "Heart rate", "/min", "beats/minute"),
    "steps": ("55423-8", "Number of steps", "{steps}", "steps"),
    "sleep_hours": ("93832-4", "Sleep duration", "h", "hours"),
}


@router.get("/metadata")
def capability_statement() -> dict:
    """FHIR R4 CapabilityStatement describing what this server supports."""
    return {
        "resourceType": "CapabilityStatement",
        "status": "active",
        "fhirVersion": "4.0.1",
        "format": ["json"],
        "publisher": "CareLoop",
        "implementation": {"description": f"CareLoop FHIR R4 read surface ({settings.data_residency} residency)"},
        "rest": [
            {
                "mode": "server",
                "resource": [
                    {"type": "Patient", "interaction": [{"code": "read"}]},
                    {
                        "type": "Observation",
                        "interaction": [{"code": "search-type"}],
                        "searchParam": [{"name": "patient", "type": "reference"}],
                    },
                ],
            }
        ],
    }


def _patient_resource(p) -> dict:
    profile = None
    try:
        from .. import fhir_source

        profile = fhir_source.get_profile(p.id)
    except Exception:  # noqa: BLE001
        profile = None
    resource: dict = {
        "resourceType": "Patient",
        "id": str(p.id),
        "active": True,
        "name": [{"text": p.name}],
    }
    if p.fhir_id:
        resource["identifier"] = [{"system": "urn:careloop:fhir-id", "value": p.fhir_id}]
    if profile and profile.gender:
        resource["gender"] = profile.gender
    if profile and profile.birth_date:
        resource["birthDate"] = profile.birth_date
    if p.phone_number and not data.is_placeholder_phone(p.phone_number):
        resource["telecom"] = [{"system": "phone", "value": p.phone_number}]
    if p.district:
        resource["address"] = [{"district": p.district, "country": "HK"}]
    return resource


def _observation(reading, p, kind: str) -> dict:
    code, display, ucum, _human = _LOINC[kind]
    value = getattr(reading, kind)
    return {
        "resourceType": "Observation",
        "id": f"{kind}-{reading.id}",
        "status": "final",
        "category": [
            {
                "coding": [
                    {
                        "system": "http://terminology.hl7.org/CodeSystem/observation-category",
                        "code": "vital-signs",
                    }
                ]
            }
        ],
        "code": {"coding": [{"system": "http://loinc.org", "code": code, "display": display}]},
        "subject": {"reference": f"Patient/{p.id}"},
        "effectiveDateTime": reading.timestamp.isoformat(),
        "valueQuantity": {
            "value": value,
            "unit": ucum,
            "system": "http://unitsofmeasure.org",
            "code": ucum,
        },
    }


@router.get("/Patient/{patient_id}")
def read_patient(patient_id: int, _=Depends(require_role("clinician"))) -> dict:
    p = data.get_patient(patient_id)
    if p is None:
        raise HTTPException(status_code=404, detail="Patient not found")
    return _patient_resource(p)


@router.get("/Observation")
def search_observations(
    patient: int = Query(..., description="Patient id (FHIR reference)"),
    _=Depends(require_role("clinician")),
) -> dict:
    """Return a FHIR searchset Bundle of LOINC-coded wearable Observations."""
    p = data.get_patient(patient)
    if p is None:
        raise HTTPException(status_code=404, detail="Patient not found")
    readings = data.get_wearables(patient)
    entries = [
        {"resource": _observation(r, p, kind)}
        for r in readings
        for kind in _LOINC
    ]
    return {
        "resourceType": "Bundle",
        "type": "searchset",
        "total": len(entries),
        "entry": entries,
    }
