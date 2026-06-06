"""In-memory store for uploaded patient care plans.

Behind a small functional interface (get/set/delete) so the internals can later
swap to MongoDB without touching callers. Resets on restart, like call_store.
"""

from __future__ import annotations

from datetime import datetime, timezone

from .fhir_careplan import extract_care_plan, locate_care_plan, parse_document
from .models import CarePlanContext, StoredCarePlan

# patient_id -> latest uploaded plan
_STORE: dict[int, StoredCarePlan] = {}


def parse_care_plan(raw: str) -> CarePlanContext:
    """Parse raw JSON/XML/text into a CarePlanContext (no storage)."""
    resource = parse_document(raw)
    care_plan, refs = locate_care_plan(resource)
    return extract_care_plan(care_plan, refs)


def get(patient_id: int) -> StoredCarePlan | None:
    return _STORE.get(patient_id)


def set(patient_id: int, raw: str, ctx: CarePlanContext) -> StoredCarePlan:
    stored = StoredCarePlan(care_plan=ctx, raw=raw, uploaded_at=datetime.now(timezone.utc))
    _STORE[patient_id] = stored
    return stored


def delete(patient_id: int) -> bool:
    return _STORE.pop(patient_id, None) is not None
