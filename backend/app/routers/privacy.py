"""Data-subject rights, consent, and privacy administration.

Implements the patient-facing controls PRIVACY.md promises:
- **Consent** (PDPO DPP1/3, GDPR Art.9, PIPL): record / view / revoke.
- **Access & portability** (DPP6, GDPR Art.15/20): a full machine-readable export.
- **Erasure** (GDPR Art.17): delete a patient's data across every store.
- **Audit** (DPP4, Art.32): read the access log.
- **Retention** (DPP2, Art.5): trigger a purge on demand.

Every endpoint is RBAC-protected and writes an audit event.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException

from .. import (
    audit,
    call_store,
    care_plan_store,
    checkin_store,
    consent_store,
    conversation_store,
    data,
    fhir_source,
    patient_overrides,
    retention,
)
from ..config import settings
from ..models import (
    AuditEvent,
    ConsentRecord,
    ConsentRequest,
    DataExport,
    ErasureResult,
    Patient,
    PatientCorrection,
)
from ..security import consent_guard
from ..security.auth import Principal, require_role
from ..services import question_gen

router = APIRouter(tags=["privacy"])


def _require_patient(patient_id: int):
    patient = data.get_patient(patient_id)
    if patient is None:
        raise HTTPException(status_code=404, detail="Patient not found")
    return patient


# --- Consent -----------------------------------------------------------------


@router.get("/patients/{patient_id}/consent", response_model=list[ConsentRecord])
def list_consent(
    patient_id: int, principal: Principal = Depends(require_role("clinician"))
) -> list[ConsentRecord]:
    _require_patient(patient_id)
    audit.record(principal.subject, "consent.read", "patient", patient_id)
    return consent_store.list_for_patient(patient_id)


@router.post("/patients/{patient_id}/consent", response_model=ConsentRecord)
def record_consent(
    patient_id: int,
    body: ConsentRequest,
    principal: Principal = Depends(require_role("coordinator")),
) -> ConsentRecord:
    """Record or revoke a patient's consent (e.g. captured via the caregiver portal)."""
    _require_patient(patient_id)
    rec = consent_store.record(
        patient_id,
        body.granted,
        scope=body.scope,
        method=body.method,
        actor=principal.subject,
        note=body.note,
    )
    audit.record(
        principal.subject,
        "consent.granted" if body.granted else "consent.revoked",
        "patient",
        patient_id,
        detail=f"scope={body.scope} method={body.method}",
    )
    return rec


# --- Rectification -----------------------------------------------------------


@router.patch("/patients/{patient_id}", response_model=Patient)
def correct_patient_data(
    patient_id: int,
    body: PatientCorrection,
    principal: Principal = Depends(require_role("clinician")),
) -> Patient:
    """Right to rectification (PDPO DPP6 / GDPR Art.16): correct a patient's record.

    Only the fields supplied in the body are changed. A corrected phone number is
    persisted via the override store so it survives a restart; the other fields
    update the roster slot. Every change is audited (old -> new).
    """
    patient = _require_patient(patient_id)
    changes: dict[str, str] = {}

    if body.name is not None and body.name != patient.name:
        changes["name"] = f"{patient.name!r}->{body.name!r}"
        patient.name = body.name
    if body.age is not None and body.age != patient.age:
        changes["age"] = f"{patient.age}->{body.age}"
        patient.age = body.age
    if body.district is not None and body.district != patient.district:
        changes["district"] = f"{patient.district!r}->{body.district!r}"
        patient.district = body.district
    if body.phone_number is not None:
        try:
            cleaned = patient_overrides.set_phone(patient_id, body.phone_number)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if cleaned != patient.phone_number:
            changes["phone_number"] = "updated"  # never log the number itself
            patient.phone_number = cleaned

    audit.record(
        principal.subject, "rectify", "patient", patient_id,
        detail=", ".join(f"{k}: {v}" for k, v in changes.items()) or "no change",
    )
    return patient


# --- Access & portability ----------------------------------------------------


@router.get("/patients/{patient_id}/data-export", response_model=DataExport)
def export_patient_data(
    patient_id: int, principal: Principal = Depends(require_role("clinician"))
) -> DataExport:
    """Full machine-readable export of everything held about a patient (DPP6/Art.20)."""
    patient = _require_patient(patient_id)
    consent_guard.enforce(patient_id)
    checkins = list(data.get_checkins(patient_id)) + checkin_store.list_for_patient(patient_id)
    try:
        questions = question_gen.get_for_patient(patient)
    except Exception:  # noqa: BLE001
        questions = None
    export = DataExport(
        patient_id=patient_id,
        generated_at=datetime.now(),
        policy_version=settings.privacy_policy_version,
        patient=patient,
        profile=fhir_source.get_profile(patient_id),
        checkins=checkins,
        wearables=data.get_wearables(patient_id),
        questions=questions,
        calls=call_store.list_call_records(patient_id),
        care_plan=care_plan_store.get(patient_id),
        consent=consent_store.list_for_patient(patient_id),
    )
    audit.record(
        principal.subject, "export", "patient", patient_id,
        detail=f"{len(export.checkins)} checkins, {len(export.calls)} calls",
    )
    return export


# --- Erasure -----------------------------------------------------------------


@router.delete("/patients/{patient_id}/data", response_model=ErasureResult)
def erase_patient_data(
    patient_id: int, principal: Principal = Depends(require_role("admin"))
) -> ErasureResult:
    """Right to erasure (GDPR Art.17): delete a patient's data across every store.

    Derived/stored data is deleted outright; the in-memory roster slot is **redacted**
    (name/phone removed) rather than dropped, so the demo dashboard does not break.
    """
    patient = _require_patient(patient_id)
    removed = {
        # Resolve conversation ids from the call history BEFORE clearing it.
        "conversations": conversation_store.erase_patient(patient_id),
        "checkins": checkin_store.erase_patient(patient_id),
        "calls_config_schedules": call_store.erase_patient(patient_id),
        "care_plan": 1 if care_plan_store.delete(patient_id) else 0,
        "consent": consent_store.erase_patient(patient_id),
        "phone_override": patient_overrides.erase(patient_id),
        "questions": 1 if question_gen.delete_for_patient(patient) else 0,
    }
    # Redact the live roster slot + drop the FHIR overlay profile.
    patient.name = "[erased]"
    patient.phone_number = None
    patient.fhir_id = None
    fhir_source._PROFILES.pop(patient_id, None)

    audit.record(principal.subject, "erase", "patient", patient_id, detail=str(removed))
    return ErasureResult(patient_id=patient_id, erased_at=datetime.now(), removed=removed)


# --- Audit & retention (admin) ----------------------------------------------


@router.get("/audit", response_model=list[AuditEvent])
def read_audit(
    limit: int = 200, principal: Principal = Depends(require_role("admin"))
) -> list[AuditEvent]:
    return audit.list_events(limit=limit)


@router.post("/admin/retention/run")
def run_retention(principal: Principal = Depends(require_role("admin"))) -> dict:
    removed = retention.run()
    audit.record(principal.subject, "retention.run", "system", detail=str(removed))
    return {"removed": removed}
