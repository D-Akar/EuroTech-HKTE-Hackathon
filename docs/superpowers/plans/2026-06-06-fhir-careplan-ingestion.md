# FHIR Care Plan Ingestion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a practice upload a FHIR CarePlan (JSON, XML, Bundle, or pasted text) and turn it into human-readable context the ElevenLabs check-in agent reads during calls, plus a clinician-PDF section and a GET API.

**Architecture:** A pure parsing/extraction module (`fhir_careplan.py`) normalizes any input form into a JSON-shaped dict, then extracts ~10 human-relevant fields into a `CarePlanContext` model and renders deterministic prose. An in-memory store (`care_plan_store.py`) behind a get/set/delete interface holds the latest plan per patient (Mongo-ready). New endpoints upload/retrieve/delete; `patient_context`, the PDF report, and a small frontend panel consume the stored plan.

**Tech Stack:** Python 3.14, FastAPI, Pydantic v2, stdlib `xml.etree.ElementTree`, pytest + `TestClient`; React + TypeScript + Vite frontend; reportlab for the PDF.

**Conventions reminder (PowerShell 5.1):** no `&&` chaining — run commands on separate lines or use `;`. Backend commands assume the venv is active: `cd backend; .venv\Scripts\activate`. Do NOT auto-commit or push — the user commits themselves; the "Commit" steps below are for the user to run when ready.

---

## File Structure

**Backend — create:**
- `backend/app/fhir_careplan.py` — pure parse + extract + render (no I/O).
- `backend/app/care_plan_store.py` — in-memory store + `parse_care_plan` convenience.
- `backend/app/routers/care_plans.py` — upload/get/delete + auto-match endpoints.
- `backend/tests/test_care_plans.py` — all backend tests, with inline fixtures.

**Backend — modify:**
- `backend/app/models.py` — add `CarePlanGoal`, `CarePlanActivity`, `CarePlanContext`, `StoredCarePlan`; extend `PatientContextResponse`.
- `backend/app/data.py` — add `get_patient_by_subject`.
- `backend/app/services/patient_context.py` — look up + fold plan into context.
- `backend/app/main.py` — register the new router.
- `backend/app/report_pdf.py` — add a care-plan PDF section.
- `backend/app/routers/reports.py` — pass the stored plan to the renderer.

**Frontend — modify/create:**
- `frontend/src/types.ts` — add care-plan types.
- `frontend/src/api/client.ts` — add upload/get/delete methods.
- `frontend/src/components/CarePlanPanel.tsx` — create the upload control.
- `frontend/src/components/PatientDetail.tsx` — render the panel.

---

## Task 1: Care-plan models

**Files:**
- Modify: `backend/app/models.py`
- Test: `backend/tests/test_care_plans.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_care_plans.py` with:

```python
"""Tests for FHIR care plan ingestion."""

import json

import pytest
from fastapi.testclient import TestClient

from app.main import app


def test_models_construct():
    from app.models import (
        CarePlanActivity,
        CarePlanContext,
        CarePlanGoal,
        StoredCarePlan,
    )
    from datetime import datetime, timezone

    ctx = CarePlanContext(
        title="Weight plan",
        status="active",
        goals=[CarePlanGoal(description="Lose weight", target="BMI < 25")],
        activities=[
            CarePlanActivity(description="Walk", status="in-progress", scheduled="daily")
        ],
        rendered_text="text",
    )
    assert ctx.title == "Weight plan"
    assert ctx.goals[0].target == "BMI < 25"
    assert ctx.categories == []  # default empty

    stored = StoredCarePlan(care_plan=ctx, raw="{}", uploaded_at=datetime.now(timezone.utc))
    assert stored.care_plan.status == "active"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend; .venv\Scripts\activate; pytest tests/test_care_plans.py::test_models_construct -v`
Expected: FAIL — `ImportError: cannot import name 'CarePlanContext'`.

- [ ] **Step 3: Add the models**

In `backend/app/models.py`, the imports already include `from datetime import date, datetime`. Append at the end of the file:

```python
# --- FHIR care plans ---------------------------------------------------------


class CarePlanGoal(BaseModel):
    description: str
    target: str | None = None


class CarePlanActivity(BaseModel):
    description: str
    status: str | None = None
    scheduled: str | None = None


class CarePlanContext(BaseModel):
    """Human-relevant fields extracted from a FHIR CarePlan."""

    title: str | None = None
    status: str | None = None
    intent: str | None = None
    description: str | None = None
    categories: list[str] = []
    subject_display: str | None = None  # used to auto-match a patient
    period_start: str | None = None
    period_end: str | None = None
    addresses: list[str] = []  # conditions the plan targets
    goals: list[CarePlanGoal] = []
    activities: list[CarePlanActivity] = []
    notes: list[str] = []
    rendered_text: str  # deterministic prose for the agent


class StoredCarePlan(BaseModel):
    care_plan: CarePlanContext
    raw: str  # original uploaded document
    uploaded_at: datetime
```

Then extend `PatientContextResponse` — add this field after `context_summary: str`:

```python
    care_plan: CarePlanContext | None = None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_care_plans.py::test_models_construct -v`
Expected: PASS.

- [ ] **Step 5: Commit (user runs when ready)**

```bash
git add backend/app/models.py backend/tests/test_care_plans.py
git commit -m "feat: add care plan models"
```

---

## Task 2: Parse JSON/XML into a dict

**Files:**
- Create: `backend/app/fhir_careplan.py`
- Test: `backend/tests/test_care_plans.py`

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_care_plans.py`:

```python
def test_parse_document_json():
    from app.fhir_careplan import parse_document

    d = parse_document('{"resourceType": "CarePlan", "status": "active"}')
    assert d["resourceType"] == "CarePlan"
    assert d["status"] == "active"


def test_parse_document_xml_normalizes_value_attrs():
    from app.fhir_careplan import parse_document

    xml = (
        '<CarePlan xmlns="http://hl7.org/fhir">'
        '<status value="active"/>'
        '<period><start value="2026-02-01"/><end value="2026-08-01"/></period>'
        "</CarePlan>"
    )
    d = parse_document(xml)
    assert d["resourceType"] == "CarePlan"
    assert d["status"] == "active"
    assert d["period"] == {"start": "2026-02-01", "end": "2026-08-01"}


def test_parse_document_errors():
    from app.fhir_careplan import CarePlanParseError, parse_document

    with pytest.raises(CarePlanParseError):
        parse_document("")
    with pytest.raises(CarePlanParseError):
        parse_document("{not json}")
    with pytest.raises(CarePlanParseError):
        parse_document("just some words")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_care_plans.py -k parse_document -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.fhir_careplan'`.

- [ ] **Step 3: Create `backend/app/fhir_careplan.py`**

```python
"""Parse FHIR CarePlan documents (JSON or XML) into human-readable context.

Pure functions, no I/O. Tolerant of FHIR R4 and R5 shapes and of slightly-off
real-world exports — we only extract the handful of fields a care agent needs,
never validate the whole resource.
"""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET

from .models import CarePlanActivity, CarePlanContext, CarePlanGoal


class CarePlanParseError(ValueError):
    """Raised when a document can't be parsed as a FHIR CarePlan."""


# --- Parsing: raw text -> JSON-shaped dict ----------------------------------


def parse_document(raw: str) -> dict:
    """Parse raw FHIR JSON or XML text into a JSON-shaped dict."""
    text = raw.strip()
    if not text:
        raise CarePlanParseError("Empty document.")
    if text[0] in "{[":
        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            raise CarePlanParseError(f"Invalid JSON: {e}") from e
    if text[0] == "<":
        try:
            root = ET.fromstring(text)
        except ET.ParseError as e:
            raise CarePlanParseError(f"Invalid XML: {e}") from e
        return _xml_to_dict(root)
    raise CarePlanParseError("Unrecognized format — expected FHIR JSON or XML.")


def _strip_ns(tag: str) -> str:
    return tag.split("}", 1)[1] if "}" in tag else tag


def _xml_to_dict(elem: ET.Element) -> dict:
    """Convert a FHIR XML resource element to its JSON representation."""
    node = _xml_element_to_value(elem)
    if not isinstance(node, dict):
        node = {}
    node["resourceType"] = _strip_ns(elem.tag)
    return node


def _xml_element_to_value(elem: ET.Element):
    """FHIR XML: primitives are ``<x value="..."/>``; repeats become arrays."""
    children = list(elem)
    value_attr = elem.get("value")
    if not children:
        return value_attr  # primitive (or None for empty elements)

    result: dict = {}
    if value_attr is not None:
        result["value"] = value_attr
    for child in children:
        key = _strip_ns(child.tag)
        child_value = _xml_element_to_value(child)
        if key in result:
            existing = result[key]
            if isinstance(existing, list):
                existing.append(child_value)
            else:
                result[key] = [existing, child_value]
        else:
            result[key] = child_value
    return result
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_care_plans.py -k parse_document -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit (user runs when ready)**

```bash
git add backend/app/fhir_careplan.py backend/tests/test_care_plans.py
git commit -m "feat: parse FHIR JSON and XML into a dict"
```

---

## Task 3: Locate the CarePlan + build a reference lookup

**Files:**
- Modify: `backend/app/fhir_careplan.py`
- Test: `backend/tests/test_care_plans.py`

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_care_plans.py`:

```python
def test_locate_care_plan_bare():
    from app.fhir_careplan import locate_care_plan

    cp, refs = locate_care_plan({"resourceType": "CarePlan", "status": "active"})
    assert cp["status"] == "active"
    assert refs == {}


def test_locate_care_plan_indexes_contained():
    from app.fhir_careplan import locate_care_plan

    cp, refs = locate_care_plan(
        {
            "resourceType": "CarePlan",
            "contained": [
                {"resourceType": "Condition", "id": "p1", "code": {"text": "obesity"}}
            ],
        }
    )
    assert refs["#p1"]["code"]["text"] == "obesity"


def test_locate_care_plan_in_bundle():
    from app.fhir_careplan import locate_care_plan

    bundle = {
        "resourceType": "Bundle",
        "entry": [
            {"resource": {"resourceType": "Goal", "id": "g1",
                          "description": {"text": "Lose weight"}}},
            {"resource": {"resourceType": "CarePlan", "status": "active",
                          "goal": [{"reference": "Goal/g1"}]}},
        ],
    }
    cp, refs = locate_care_plan(bundle)
    assert cp["status"] == "active"
    assert refs["Goal/g1"]["description"]["text"] == "Lose weight"


def test_locate_care_plan_missing_raises():
    from app.fhir_careplan import CarePlanParseError, locate_care_plan

    with pytest.raises(CarePlanParseError):
        locate_care_plan({"resourceType": "Bundle", "entry": []})
    with pytest.raises(CarePlanParseError):
        locate_care_plan({"resourceType": "Patient"})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_care_plans.py -k locate_care_plan -v`
Expected: FAIL — `ImportError: cannot import name 'locate_care_plan'`.

- [ ] **Step 3: Add the functions**

Append to `backend/app/fhir_careplan.py`:

```python
# --- Locating the CarePlan + reference lookup -------------------------------


def _as_list(value) -> list:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def _index(res: dict, refs: dict) -> None:
    rid = res.get("id")
    rtype = res.get("resourceType")
    if rid and rtype:
        refs[f"{rtype}/{rid}"] = res


def locate_care_plan(resource: dict) -> tuple[dict, dict]:
    """Return ``(care_plan, refs)``.

    Accepts a bare CarePlan or a Bundle containing one. ``refs`` maps both
    ``'ResourceType/id'`` and contained ``'#id'`` keys to their resource dicts
    so goals/conditions/activities can be dereferenced during extraction.
    """
    refs: dict[str, dict] = {}
    care_plan: dict | None = None

    rtype = resource.get("resourceType")
    if rtype == "Bundle":
        for entry in _as_list(resource.get("entry")):
            res = entry.get("resource") if isinstance(entry, dict) else None
            if not isinstance(res, dict):
                continue
            _index(res, refs)
            if res.get("resourceType") == "CarePlan" and care_plan is None:
                care_plan = res
    elif rtype == "CarePlan":
        care_plan = resource
    else:
        raise CarePlanParseError(
            f"Expected a CarePlan or Bundle, got {rtype or 'unknown resource'}."
        )

    if care_plan is None:
        raise CarePlanParseError("No CarePlan found in the document.")

    for contained in _as_list(care_plan.get("contained")):
        if isinstance(contained, dict) and contained.get("id"):
            cid = contained["id"]
            refs[f"#{cid}"] = contained
            _index(contained, refs)
    return care_plan, refs
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_care_plans.py -k locate_care_plan -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit (user runs when ready)**

```bash
git add backend/app/fhir_careplan.py backend/tests/test_care_plans.py
git commit -m "feat: locate CarePlan in bundles and index references"
```

---

## Task 4: Extract fields + render prose

**Files:**
- Modify: `backend/app/fhir_careplan.py`
- Test: `backend/tests/test_care_plans.py`

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_care_plans.py` — first the shared fixtures, then the tests:

```python
# --- Shared fixtures (FHIR CarePlan documents) ------------------------------

CAREPLAN_R4 = {
    "resourceType": "CarePlan",
    "id": "cp1",
    "status": "active",
    "intent": "plan",
    "title": "Weight management plan",
    "description": "Manage obesity and weight loss",
    "subject": {"reference": "Patient/1", "display": "Margaret Holloway"},
    "period": {"start": "2026-01-01", "end": "2026-06-01"},
    "category": [{"text": "Weight management"}],
    "contained": [
        {"resourceType": "Condition", "id": "p1", "code": {"text": "obesity"}}
    ],
    "addresses": [{"reference": "#p1", "display": "obesity"}],
    "goal": [{"reference": "Goal/g1"}],  # resolved only in the bundle variant
    "activity": [
        {"detail": {"code": {"text": "Weight management classes"},
                    "status": "in-progress", "scheduledString": "three times a week"}},
        {"detail": {"code": {"text": "Dietary consultation"}, "status": "scheduled"}},
    ],
    "note": [{"text": "Patient is motivated to lose weight."}],
}

CAREPLAN_BUNDLE = {
    "resourceType": "Bundle",
    "type": "collection",
    "entry": [
        {"resource": CAREPLAN_R4},
        {"resource": {
            "resourceType": "Goal",
            "id": "g1",
            "description": {"text": "Achieve target BMI"},
            "target": [{"measure": {"text": "BMI"}, "detailString": "< 25"}],
        }},
    ],
}

CAREPLAN_XML = (
    '<CarePlan xmlns="http://hl7.org/fhir">'
    '<status value="active"/>'
    '<intent value="plan"/>'
    '<title value="Hypertension management"/>'
    '<subject><display value="Arthur Chen"/></subject>'
    '<period><start value="2026-02-01"/><end value="2026-08-01"/></period>'
    '<activity><detail>'
    '<code><text value="Daily blood pressure check"/></code>'
    '<status value="in-progress"/>'
    '</detail></activity>'
    "</CarePlan>"
)


def _extract(resource):
    from app.fhir_careplan import extract_care_plan, locate_care_plan

    cp, refs = locate_care_plan(resource)
    return extract_care_plan(cp, refs)


def test_extract_basic_fields():
    ctx = _extract(CAREPLAN_R4)
    assert ctx.title == "Weight management plan"
    assert ctx.status == "active"
    assert ctx.intent == "plan"
    assert ctx.subject_display == "Margaret Holloway"
    assert ctx.period_start == "2026-01-01"
    assert ctx.period_end == "2026-06-01"
    assert ctx.categories == ["Weight management"]
    assert ctx.addresses == ["obesity"]  # resolved via contained Condition
    assert ctx.notes == ["Patient is motivated to lose weight."]


def test_extract_activities():
    ctx = _extract(CAREPLAN_R4)
    assert len(ctx.activities) == 2
    first = ctx.activities[0]
    assert first.description == "Weight management classes"
    assert first.status == "in-progress"
    assert first.scheduled == "three times a week"


def test_extract_goals_from_bundle():
    ctx = _extract(CAREPLAN_BUNDLE)
    assert len(ctx.goals) == 1
    assert ctx.goals[0].description == "Achieve target BMI"
    assert ctx.goals[0].target == "BMI: < 25"


def test_extract_bare_careplan_has_no_unresolved_goals():
    ctx = _extract(CAREPLAN_R4)  # Goal/g1 not present -> skipped
    assert ctx.goals == []


def test_extract_from_xml():
    from app.fhir_careplan import parse_document

    ctx = _extract(parse_document(CAREPLAN_XML))
    assert ctx.title == "Hypertension management"
    assert ctx.status == "active"
    assert ctx.subject_display == "Arthur Chen"
    assert ctx.period_start == "2026-02-01"
    assert ctx.activities[0].description == "Daily blood pressure check"


def test_render_text_includes_sections_and_omits_absent():
    ctx = _extract(CAREPLAN_BUNDLE)
    text = ctx.rendered_text
    assert 'Care plan: "Weight management plan"' in text
    assert "status: active" in text
    assert "Addresses: obesity." in text
    assert "Achieve target BMI (target: BMI: < 25)" in text
    assert "[in-progress] Weight management classes — three times a week" in text
    assert "Patient is motivated to lose weight." in text

    bare = _extract({"resourceType": "CarePlan", "title": "Minimal"})
    assert bare.rendered_text == 'Care plan: "Minimal".'
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_care_plans.py -k "extract or render" -v`
Expected: FAIL — `ImportError: cannot import name 'extract_care_plan'`.

- [ ] **Step 3: Add extraction + rendering**

Append to `backend/app/fhir_careplan.py`:

```python
# --- Field extraction -------------------------------------------------------


def _codeable_text(cc) -> str | None:
    """Best human label from a CodeableConcept."""
    if not isinstance(cc, dict):
        return None
    if cc.get("text"):
        return cc["text"]
    for coding in _as_list(cc.get("coding")):
        if isinstance(coding, dict) and coding.get("display"):
            return coding["display"]
    return None


def _resolve(ref, refs: dict) -> dict | None:
    return refs.get(ref) if isinstance(ref, str) else None


def _reference_label(node: dict, refs: dict) -> str | None:
    """Resolve a Reference / R5 CodeableReference to a human label."""
    ref = node.get("reference")
    if isinstance(ref, dict):  # R5 CodeableReference
        target = _resolve(ref.get("reference"), refs)
        return _codeable_text((target or {}).get("code")) or ref.get("display")
    if isinstance(ref, str):  # R4 Reference
        target = _resolve(ref, refs)
        return _codeable_text((target or {}).get("code")) or node.get("display")
    return node.get("display")


def _period_text(period) -> tuple[str | None, str | None]:
    if not isinstance(period, dict):
        return None, None
    return period.get("start"), period.get("end")


def _addresses(care_plan: dict, refs: dict) -> list[str]:
    out: list[str] = []
    for addr in _as_list(care_plan.get("addresses")):
        if not isinstance(addr, dict):
            continue
        label = _reference_label(addr, refs) or _codeable_text(addr.get("concept"))
        if label:
            out.append(label)
    return out


def _goal_target(goal: dict) -> str | None:
    for t in _as_list(goal.get("target")):
        if not isinstance(t, dict):
            continue
        measure = _codeable_text(t.get("measure"))
        detail = t.get("detailString") or _codeable_text(t.get("detailCodeableConcept"))
        quantity = t.get("detailQuantity")
        if isinstance(quantity, dict) and quantity.get("value") is not None:
            unit = quantity.get("unit") or quantity.get("code") or ""
            detail = f"{quantity['value']} {unit}".strip()
        if measure and detail:
            return f"{measure}: {detail}"
        return detail or measure
    return None


def _goals(care_plan: dict, refs: dict) -> list[CarePlanGoal]:
    out: list[CarePlanGoal] = []
    for g in _as_list(care_plan.get("goal")):
        if not isinstance(g, dict):
            continue
        target = _resolve(g.get("reference"), refs)
        if isinstance(target, dict):
            desc = _codeable_text(target.get("description")) or g.get("display")
            tgt = _goal_target(target)
        else:
            desc, tgt = g.get("display"), None
        if desc:
            out.append(CarePlanGoal(description=desc, target=tgt))
    return out


def _scheduled_text(detail: dict) -> str | None:
    if detail.get("scheduledString"):
        return detail["scheduledString"]
    period = detail.get("scheduledPeriod")
    if isinstance(period, dict) and (period.get("start") or period.get("end")):
        return f"{period.get('start') or '?'} to {period.get('end') or '?'}"
    timing = detail.get("scheduledTiming")
    if isinstance(timing, dict):
        repeat = timing.get("repeat")
        if isinstance(repeat, dict):
            freq, per, unit = (
                repeat.get("frequency"),
                repeat.get("period"),
                repeat.get("periodUnit"),
            )
            if freq and per and unit:
                return f"{freq}x per {per} {unit}"
        return _codeable_text(timing.get("code"))
    return None


def _activity_ref_label(a: dict, refs: dict) -> str | None:
    planned = a.get("plannedActivityReference")
    if isinstance(planned, dict):
        target = _resolve(planned.get("reference"), refs)
        label = _codeable_text((target or {}).get("code")) or planned.get("display")
        if label:
            return label
    for perf in _as_list(a.get("performedActivity")):
        if isinstance(perf, dict):
            label = _codeable_text(perf.get("concept"))
            if label:
                return label
    return None


def _activities(care_plan: dict, refs: dict) -> list[CarePlanActivity]:
    out: list[CarePlanActivity] = []
    for a in _as_list(care_plan.get("activity")):
        if not isinstance(a, dict):
            continue
        detail = a.get("detail")
        if isinstance(detail, dict):  # R4
            desc = _codeable_text(detail.get("code")) or detail.get("description")
            status = detail.get("status")
            scheduled = _scheduled_text(detail)
        else:  # R5 planned/performed
            desc, status, scheduled = _activity_ref_label(a, refs), None, None
        if desc:
            out.append(
                CarePlanActivity(description=desc, status=status, scheduled=scheduled)
            )
    return out


def extract_care_plan(care_plan: dict, refs: dict) -> CarePlanContext:
    """Pull human-relevant fields and render prose."""
    categories = [c for c in (_codeable_text(c) for c in _as_list(care_plan.get("category"))) if c]
    title = care_plan.get("title") or (categories[0] if categories else None)
    start, end = _period_text(care_plan.get("period"))
    subject = care_plan.get("subject")
    subject_display = subject.get("display") if isinstance(subject, dict) else None
    notes = [
        n["text"]
        for n in _as_list(care_plan.get("note"))
        if isinstance(n, dict) and n.get("text")
    ]

    ctx = CarePlanContext(
        title=title,
        status=care_plan.get("status"),
        intent=care_plan.get("intent"),
        description=care_plan.get("description"),
        categories=categories,
        subject_display=subject_display,
        period_start=start,
        period_end=end,
        addresses=_addresses(care_plan, refs),
        goals=_goals(care_plan, refs),
        activities=_activities(care_plan, refs),
        notes=notes,
        rendered_text="",
    )
    ctx.rendered_text = render_care_plan_text(ctx)
    return ctx


def render_care_plan_text(ctx: CarePlanContext) -> str:
    """Deterministic prose block for the agent; omits absent sections."""
    lines: list[str] = []
    meta = []
    if ctx.status:
        meta.append(f"status: {ctx.status}")
    if ctx.intent:
        meta.append(f"intent: {ctx.intent}")
    suffix = f" ({', '.join(meta)})" if meta else ""
    lines.append(f'Care plan: "{ctx.title or "Care plan"}"{suffix}.')

    if ctx.description:
        lines.append(ctx.description)
    if ctx.period_start or ctx.period_end:
        lines.append(f"Covers {ctx.period_start or 'unknown'} to {ctx.period_end or 'ongoing'}.")
    if ctx.categories:
        lines.append(f"Category: {', '.join(ctx.categories)}.")
    if ctx.addresses:
        lines.append(f"Addresses: {', '.join(ctx.addresses)}.")
    if ctx.goals:
        lines.append("Goals:")
        for g in ctx.goals:
            target = f" (target: {g.target})" if g.target else ""
            lines.append(f"- {g.description}{target}")
    if ctx.activities:
        lines.append("Planned activities:")
        for a in ctx.activities:
            status = f"[{a.status}] " if a.status else ""
            sched = f" — {a.scheduled}" if a.scheduled else ""
            lines.append(f"- {status}{a.description}{sched}")
    if ctx.notes:
        lines.append("Notes: " + " ".join(ctx.notes))
    return "\n".join(lines)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_care_plans.py -k "extract or render" -v`
Expected: PASS (6 tests).

- [ ] **Step 5: Commit (user runs when ready)**

```bash
git add backend/app/fhir_careplan.py backend/tests/test_care_plans.py
git commit -m "feat: extract care plan fields and render prose"
```

---

## Task 5: In-memory care plan store

**Files:**
- Create: `backend/app/care_plan_store.py`
- Test: `backend/tests/test_care_plans.py`

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_care_plans.py`:

```python
def test_care_plan_store_roundtrip():
    from app import care_plan_store

    ctx = care_plan_store.parse_care_plan(json.dumps(CAREPLAN_R4))
    assert ctx.title == "Weight management plan"

    care_plan_store.delete(999)  # clean slate
    assert care_plan_store.get(999) is None

    stored = care_plan_store.set(999, json.dumps(CAREPLAN_R4), ctx)
    assert stored.care_plan.title == "Weight management plan"
    assert care_plan_store.get(999).raw  # raw retained

    assert care_plan_store.delete(999) is True
    assert care_plan_store.get(999) is None
    assert care_plan_store.delete(999) is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_care_plans.py::test_care_plan_store_roundtrip -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.care_plan_store'`.

- [ ] **Step 3: Create `backend/app/care_plan_store.py`**

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_care_plans.py::test_care_plan_store_roundtrip -v`
Expected: PASS.

- [ ] **Step 5: Commit (user runs when ready)**

```bash
git add backend/app/care_plan_store.py backend/tests/test_care_plans.py
git commit -m "feat: in-memory care plan store"
```

---

## Task 6: Match a patient by FHIR subject

**Files:**
- Modify: `backend/app/data.py`
- Test: `backend/tests/test_care_plans.py`

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_care_plans.py`:

```python
def test_get_patient_by_subject():
    from app import data

    p = data.get_patient_by_subject("Margaret Holloway")
    assert p is not None and p.name == "Margaret Holloway"

    assert data.get_patient_by_subject("margaret holloway") is not None  # case-insensitive
    assert data.get_patient_by_subject("Nobody Here") is None
    assert data.get_patient_by_subject("") is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_care_plans.py::test_get_patient_by_subject -v`
Expected: FAIL — `AttributeError: module 'app.data' has no attribute 'get_patient_by_subject'`.

- [ ] **Step 3: Add the helper**

In `backend/app/data.py`, add after `get_patient_by_phone` (around line 198):

```python
def get_patient_by_subject(display: str) -> Patient | None:
    """Match a FHIR CarePlan.subject.display against a patient name."""
    if not display:
        return None
    target = display.strip().casefold()
    return next((p for p in PATIENTS if p.name.strip().casefold() == target), None)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_care_plans.py::test_get_patient_by_subject -v`
Expected: PASS.

- [ ] **Step 5: Commit (user runs when ready)**

```bash
git add backend/app/data.py backend/tests/test_care_plans.py
git commit -m "feat: match patient by FHIR subject display"
```

---

## Task 7: Upload / get / delete endpoints

**Files:**
- Create: `backend/app/routers/care_plans.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_care_plans.py`

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_care_plans.py`:

```python
@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture(autouse=True)
def _clear_store():
    from app import care_plan_store

    care_plan_store._STORE.clear()
    yield
    care_plan_store._STORE.clear()


def test_upload_get_delete_json(client):
    body = json.dumps(CAREPLAN_R4)
    r = client.post("/patients/1/care-plan", content=body,
                    headers={"Content-Type": "application/json"})
    assert r.status_code == 200, r.text
    assert r.json()["title"] == "Weight management plan"

    g = client.get("/patients/1/care-plan")
    assert g.status_code == 200
    assert "Weight management classes" in g.json()["rendered_text"]

    d = client.delete("/patients/1/care-plan")
    assert d.status_code == 204
    assert client.get("/patients/1/care-plan").status_code == 404


def test_upload_xml(client):
    r = client.post("/patients/2/care-plan", content=CAREPLAN_XML,
                    headers={"Content-Type": "application/xml"})
    assert r.status_code == 200, r.text
    assert r.json()["title"] == "Hypertension management"


def test_upload_unknown_patient_404(client):
    r = client.post("/patients/99999/care-plan", content=json.dumps(CAREPLAN_R4))
    assert r.status_code == 404


def test_upload_bad_document_422(client):
    r = client.post("/patients/1/care-plan", content="not a care plan")
    assert r.status_code == 422


def test_auto_match_endpoint(client):
    r = client.post("/care-plans", content=json.dumps(CAREPLAN_R4))
    assert r.status_code == 200, r.text
    assert r.json()["patient_id"] == 1  # "Margaret Holloway" is patient 1


def test_auto_match_no_subject_match_422(client):
    plan = dict(CAREPLAN_R4, subject={"display": "Unknown Person"})
    r = client.post("/care-plans", content=json.dumps(plan))
    assert r.status_code == 422
    assert "Unknown Person" in r.json()["detail"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_care_plans.py -k "upload or auto_match or delete" -v`
Expected: FAIL — 404/405 because the routes don't exist yet.

- [ ] **Step 3: Create the router**

Create `backend/app/routers/care_plans.py`:

```python
"""Upload, retrieve, and delete FHIR care plans for patients."""

from fastapi import APIRouter, HTTPException, Request, Response

from .. import care_plan_store, data
from ..fhir_careplan import CarePlanParseError
from ..models import CarePlanContext

router = APIRouter(tags=["care-plans"])


async def _read_body(request: Request) -> str:
    raw = (await request.body()).decode("utf-8", errors="replace")
    if not raw.strip():
        raise HTTPException(status_code=422, detail="Empty request body.")
    return raw


def _parse(raw: str) -> CarePlanContext:
    try:
        return care_plan_store.parse_care_plan(raw)
    except CarePlanParseError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e


@router.post("/patients/{patient_id}/care-plan", response_model=CarePlanContext)
async def upload_care_plan(patient_id: int, request: Request) -> CarePlanContext:
    if data.get_patient(patient_id) is None:
        raise HTTPException(status_code=404, detail="Patient not found")
    raw = await _read_body(request)
    ctx = _parse(raw)
    care_plan_store.set(patient_id, raw, ctx)
    return ctx


@router.get("/patients/{patient_id}/care-plan", response_model=CarePlanContext)
def get_care_plan(patient_id: int) -> CarePlanContext:
    stored = care_plan_store.get(patient_id)
    if stored is None:
        raise HTTPException(status_code=404, detail="No care plan for this patient")
    return stored.care_plan


@router.delete("/patients/{patient_id}/care-plan", status_code=204)
def delete_care_plan(patient_id: int) -> Response:
    if not care_plan_store.delete(patient_id):
        raise HTTPException(status_code=404, detail="No care plan for this patient")
    return Response(status_code=204)


@router.post("/care-plans")
async def upload_care_plan_auto(request: Request) -> dict:
    raw = await _read_body(request)
    ctx = _parse(raw)
    patient = data.get_patient_by_subject(ctx.subject_display or "")
    if patient is None:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Could not match care plan subject "
                f"'{ctx.subject_display or 'unknown'}' to a patient. "
                "Upload it against a specific patient instead."
            ),
        )
    care_plan_store.set(patient.id, raw, ctx)
    return {"patient_id": patient.id, "care_plan": ctx.model_dump()}
```

- [ ] **Step 4: Register the router**

In `backend/app/main.py`, add `care_plans` to the router import block (after `calls,`):

```python
from .routers import (
    alerts,
    calls,
    care_plans,
    checkins,
    integrations,
    live,
    meta,
    patients,
    reports,
    summary,
    vitals,
    wearables,
)
```

And add after `app.include_router(reports.router)`:

```python
app.include_router(care_plans.router)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/test_care_plans.py -k "upload or auto_match or delete" -v`
Expected: PASS (6 tests).

- [ ] **Step 6: Commit (user runs when ready)**

```bash
git add backend/app/routers/care_plans.py backend/app/main.py backend/tests/test_care_plans.py
git commit -m "feat: care plan upload/get/delete endpoints"
```

---

## Task 8: Fold the care plan into agent context

**Files:**
- Modify: `backend/app/services/patient_context.py`
- Test: `backend/tests/test_care_plans.py`

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_care_plans.py`:

```python
def test_patient_context_includes_care_plan():
    from app import care_plan_store, data
    from app.services.patient_context import build_patient_context

    patient = data.get_patient(1)
    ctx = care_plan_store.parse_care_plan(json.dumps(CAREPLAN_R4))
    care_plan_store.set(1, json.dumps(CAREPLAN_R4), ctx)

    resp = build_patient_context(patient)
    assert resp.care_plan is not None
    assert resp.care_plan.title == "Weight management plan"
    assert "Care plan:" in resp.context_summary
    assert "Weight management classes" in resp.context_summary


def test_patient_context_without_care_plan():
    from app import data
    from app.services.patient_context import build_patient_context

    resp = build_patient_context(data.get_patient(2))
    assert resp.care_plan is None
    assert "Care plan:" not in resp.context_summary
```

(The `_clear_store` autouse fixture from Task 7 keeps these isolated.)

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_care_plans.py -k patient_context -v`
Expected: FAIL — `TypeError`/`AttributeError` because `build_context_summary` doesn't accept a care plan and the response field isn't populated.

- [ ] **Step 3: Wire it in**

In `backend/app/services/patient_context.py`:

Update the import line to add `care_plan_store`:

```python
from .. import alerts, call_store, care_plan_store, data, summary, wearable_source
from ..models import CarePlanContext, Patient, PatientContextResponse
```

Change the `build_context_summary` signature to accept the plan and append it. Replace the function's signature line and add the block just before `return "\n".join(lines)`:

```python
def build_context_summary(
    patient: Patient,
    checkins: list,
    wearables: list,
    alert_list: list[dict],
    call_config,
    care_plan: CarePlanContext | None = None,
) -> str:
```

```python
    if care_plan is not None:
        lines.append("")
        lines.append(care_plan.rendered_text)

    return "\n".join(lines)
```

In `build_patient_context`, look up the stored plan and pass it through. After `call_config = call_store.get_config(patient_id)` add:

```python
    stored_plan = care_plan_store.get(patient_id)
    care_plan = stored_plan.care_plan if stored_plan else None
```

And update the `return PatientContextResponse(...)` to add `care_plan=care_plan,` and pass `care_plan` into the summary call:

```python
    return PatientContextResponse(
        patient=patient,
        checkins=checkins,
        wearables=wearables,
        alerts=alert_list,
        summary=summary_stats,
        vitals=vitals,
        call_config=call_config,
        care_plan=care_plan,
        context_summary=build_context_summary(
            patient, checkins, wearables, alert_list, call_config, care_plan
        ),
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_care_plans.py -k patient_context -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Run the full backend suite (no regressions)**

Run: `pytest -q`
Expected: PASS — existing `test_integrations.py` (which builds patient context) still passes.

- [ ] **Step 6: Commit (user runs when ready)**

```bash
git add backend/app/services/patient_context.py backend/tests/test_care_plans.py
git commit -m "feat: include care plan in agent context summary"
```

---

## Task 9: Care plan section in the clinician PDF

**Files:**
- Modify: `backend/app/report_pdf.py`, `backend/app/routers/reports.py`
- Test: `backend/tests/test_care_plans.py`

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_care_plans.py`:

```python
def test_report_pdf_includes_care_plan(client):
    body = json.dumps(CAREPLAN_R4)
    assert client.post("/patients/1/care-plan", content=body).status_code == 200

    r = client.get("/patients/1/report.pdf")
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert r.content[:4] == b"%PDF"  # plan is looked up + rendered without error
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_care_plans.py::test_report_pdf_includes_care_plan -v`
Expected: At this point the report endpoint ignores the plan; the test passes for the PDF bytes but the section isn't rendered. To make this a true failing test first, assert the renderer signature. Instead, drive the change from the renderer unit test below.

Add this unit test too:

```python
def test_build_report_pdf_accepts_care_plan():
    from app import care_plan_store, data
    from app.report_pdf import build_report_pdf
    from app.report_summary import build_summary

    patient = data.get_patient(1)
    checkins = data.get_checkins(1)
    wearables = data.get_wearables(1)
    summary = build_summary(checkins, wearables)
    ctx = care_plan_store.parse_care_plan(json.dumps(CAREPLAN_R4))

    pdf = build_report_pdf(patient, summary, checkins, wearables, care_plan=ctx)
    assert pdf[:4] == b"%PDF"
```

Run: `pytest tests/test_care_plans.py::test_build_report_pdf_accepts_care_plan -v`
Expected: FAIL — `TypeError: build_report_pdf() got an unexpected keyword argument 'care_plan'`.

- [ ] **Step 3: Add the PDF section**

In `backend/app/report_pdf.py`:

Update the model import to include the care plan type:

```python
from .models import CarePlanContext, CheckIn, Patient, WearableReading
```

Add a section builder above `build_report_pdf`:

```python
def _care_plan_section(
    care_plan: CarePlanContext, styles: dict[str, ParagraphStyle]
) -> list:
    flow: list = [Paragraph("Care plan", styles["section"])]
    meta = []
    if care_plan.status:
        meta.append(f"status {care_plan.status}")
    if care_plan.intent:
        meta.append(f"intent {care_plan.intent}")
    title = care_plan.title or "Care plan"
    heading = f"<b>{title}</b>" + (f" ({', '.join(meta)})" if meta else "")
    flow.append(Paragraph(heading, styles["body"]))
    if care_plan.description:
        flow.append(Paragraph(care_plan.description, styles["body"]))
    if care_plan.period_start or care_plan.period_end:
        flow.append(Paragraph(
            f"Covers {care_plan.period_start or 'unknown'} to "
            f"{care_plan.period_end or 'ongoing'}.", styles["body"]))
    if care_plan.addresses:
        flow.append(Paragraph("Addresses: " + ", ".join(care_plan.addresses), styles["body"]))
    if care_plan.goals:
        flow.append(Paragraph("<b>Goals</b>", styles["body"]))
        for g in care_plan.goals:
            target = f" (target: {g.target})" if g.target else ""
            flow.append(Paragraph(f"• {g.description}{target}", styles["cell"]))
    if care_plan.activities:
        flow.append(Paragraph("<b>Planned activities</b>", styles["body"]))
        for a in care_plan.activities:
            status = f"[{a.status}] " if a.status else ""
            sched = f" — {a.scheduled}" if a.scheduled else ""
            flow.append(Paragraph(f"• {status}{a.description}{sched}", styles["cell"]))
    if care_plan.notes:
        flow.append(Paragraph("Notes: " + " ".join(care_plan.notes), styles["body"]))
    return flow
```

Change the `build_report_pdf` signature to accept the optional plan:

```python
def build_report_pdf(
    patient: Patient,
    summary: ReportSummary,
    checkins: list[CheckIn],
    wearables: list[WearableReading],
    care_plan: CarePlanContext | None = None,
) -> bytes:
```

Insert the section into the flow — after the "At-a-glance vitals" block (`flow.append(_vitals_row(wearables, styles))`) and before the footer `Spacer`:

```python
    if care_plan is not None:
        flow.append(_care_plan_section(care_plan, styles))
```

Note: `_care_plan_section` returns a list; append it via `flow += _care_plan_section(...)` instead:

```python
    if care_plan is not None:
        flow += _care_plan_section(care_plan, styles)
```

- [ ] **Step 4: Pass the stored plan from the reports endpoint**

In `backend/app/routers/reports.py`, add the import and look up the plan:

```python
from .. import care_plan_store, data
```

In `patient_report_pdf`, replace the `pdf = build_report_pdf(...)` line with:

```python
    stored_plan = care_plan_store.get(patient_id)
    care_plan = stored_plan.care_plan if stored_plan else None
    pdf = build_report_pdf(patient, summary, checkins, wearables, care_plan=care_plan)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_care_plans.py -k "report" -v`
Expected: PASS (2 tests).

- [ ] **Step 6: Full suite**

Run: `pytest -q`
Expected: PASS — `test_reports.py` still passes (the new arg is optional).

- [ ] **Step 7: Commit (user runs when ready)**

```bash
git add backend/app/report_pdf.py backend/app/routers/reports.py backend/tests/test_care_plans.py
git commit -m "feat: render care plan section in clinician PDF"
```

---

## Task 10: Frontend types + API client

**Files:**
- Modify: `frontend/src/types.ts`, `frontend/src/api/client.ts`

- [ ] **Step 1: Add the types**

Append to `frontend/src/types.ts`:

```typescript
export interface CarePlanGoal {
  description: string;
  target: string | null;
}

export interface CarePlanActivity {
  description: string;
  status: string | null;
  scheduled: string | null;
}

export interface CarePlanContext {
  title: string | null;
  status: string | null;
  intent: string | null;
  description: string | null;
  categories: string[];
  subject_display: string | null;
  period_start: string | null;
  period_end: string | null;
  addresses: string[];
  goals: CarePlanGoal[];
  activities: CarePlanActivity[];
  notes: string[];
  rendered_text: string;
}
```

- [ ] **Step 2: Add the API methods**

In `frontend/src/api/client.ts`:

Add `CarePlanContext` to the type import block at the top:

```typescript
import type {
  Alert,
  CallConfig,
  CallRecord,
  CarePlanContext,
  CheckIn,
  LiveVitals,
  Meta,
  Patient,
  ScheduledCall,
  Summary,
  WearableReading,
} from "../types";
```

Add a raw-text sender near `sendJSON` (after the `sendJSON` function, before `export const api`):

```typescript
async function sendText<T>(path: string, text: string): Promise<T> {
  const resp = await fetch(`${BASE_URL}${path}`, {
    method: "POST",
    headers: { "Content-Type": "text/plain" },
    body: text,
  });
  if (!resp.ok) {
    let detail = `${resp.status} ${resp.statusText}`;
    try {
      const data = await resp.json();
      if (data?.detail) detail = data.detail;
    } catch {
      /* keep status text */
    }
    throw new Error(detail);
  }
  return resp.json() as Promise<T>;
}
```

Add these methods inside the `api` object (e.g. after the calls block, before the closing `}`):

```typescript
  // --- Care plans ---
  uploadCarePlan: (patientId: number, document: string) =>
    sendText<CarePlanContext>(`/patients/${patientId}/care-plan`, document),
  getCarePlan: (patientId: number) =>
    getJSON<CarePlanContext>(`/patients/${patientId}/care-plan`),
  deleteCarePlan: (patientId: number) =>
    fetch(`${BASE_URL}/patients/${patientId}/care-plan`, { method: "DELETE" }).then(
      (r) => {
        if (!r.ok && r.status !== 404) throw new Error(`${r.status} ${r.statusText}`);
      },
    ),
```

- [ ] **Step 3: Typecheck**

Run: `cd frontend; npm run build`
Expected: build succeeds (no TS errors). If `npm run build` is too slow, run `npx tsc --noEmit`.

- [ ] **Step 4: Commit (user runs when ready)**

```bash
git add frontend/src/types.ts frontend/src/api/client.ts
git commit -m "feat: frontend care plan types and API client"
```

---

## Task 11: Care plan upload panel

**Files:**
- Create: `frontend/src/components/CarePlanPanel.tsx`
- Modify: `frontend/src/components/PatientDetail.tsx`

- [ ] **Step 1: Create the component**

Create `frontend/src/components/CarePlanPanel.tsx`:

```tsx
import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { CarePlanContext, Patient } from "../types";

export function CarePlanPanel({ patient }: { patient: Patient }) {
  const [plan, setPlan] = useState<CarePlanContext | null>(null);
  const [pasted, setPasted] = useState("");
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setPlan(null);
    setStatus(null);
    setError(null);
    setPasted("");
    api
      .getCarePlan(patient.id)
      .then((p) => !cancelled && setPlan(p))
      .catch(() => {
        /* 404 = no plan yet */
      });
    return () => {
      cancelled = true;
    };
  }, [patient.id]);

  async function upload(document: string) {
    if (!document.trim()) {
      setError("Paste or choose a FHIR care plan first.");
      return;
    }
    setBusy(true);
    setStatus(null);
    setError(null);
    try {
      const ctx = await api.uploadCarePlan(patient.id, document);
      setPlan(ctx);
      setPasted("");
      setStatus("Care plan uploaded.");
    } catch (e) {
      setError(String(e instanceof Error ? e.message : e));
    } finally {
      setBusy(false);
    }
  }

  async function handleFile(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    const text = await file.text();
    await upload(text);
    e.target.value = ""; // allow re-uploading the same file
  }

  async function handleRemove() {
    setBusy(true);
    setError(null);
    try {
      await api.deleteCarePlan(patient.id);
      setPlan(null);
      setStatus("Care plan removed.");
    } catch (e) {
      setError(String(e instanceof Error ? e.message : e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="care-plan-panel">
      <div className="section-label">Care plan</div>

      {status && <p className="call-status">{status}</p>}
      {error && <p className="call-error">{error}</p>}

      {plan ? (
        <div className="care-plan-current">
          <p>
            <strong>Attached:</strong> {plan.title ?? "Care plan"}
            {plan.status ? ` (${plan.status})` : ""}
          </p>
          {plan.goals.length > 0 && (
            <p className="muted" style={{ fontSize: 13.5 }}>
              {plan.goals.length} goal{plan.goals.length === 1 ? "" : "s"},{" "}
              {plan.activities.length} activit
              {plan.activities.length === 1 ? "y" : "ies"}
            </p>
          )}
          <button className="btn btn-ghost" onClick={handleRemove} disabled={busy}>
            Remove
          </button>
        </div>
      ) : (
        <p className="muted" style={{ fontSize: 13.5 }}>
          No care plan attached.
        </p>
      )}

      <div className="call-block">
        <label className="field">
          <span className="field-label">Upload FHIR file (.json / .xml)</span>
          <input type="file" accept=".json,.xml,application/json,text/xml"
                 onChange={handleFile} disabled={busy} />
        </label>
        <span className="field-label" style={{ marginTop: 8 }}>
          …or paste FHIR JSON / XML
        </span>
        <textarea
          className="input"
          rows={4}
          value={pasted}
          onChange={(e) => setPasted(e.target.value)}
          placeholder='{"resourceType": "CarePlan", ...}'
        />
        <button className="btn" onClick={() => upload(pasted)} disabled={busy}
                style={{ marginTop: 6 }}>
          Upload pasted plan
        </button>
      </div>
    </section>
  );
}
```

- [ ] **Step 2: Render it in PatientDetail**

In `frontend/src/components/PatientDetail.tsx`:

Add the import next to the other component imports:

```typescript
import { CarePlanPanel } from "./CarePlanPanel";
```

Render it right after `<CallPanel patient={patient} />`:

```tsx
        <CallPanel patient={patient} />

        <CarePlanPanel patient={patient} />
```

- [ ] **Step 3: Typecheck**

Run: `cd frontend; npm run build`
Expected: build succeeds with no TS errors.

- [ ] **Step 4: Manual verification**

With both servers running (`uvicorn app.main:app --reload` and `npm run dev`):
1. Open http://localhost:5173, select **Margaret Holloway**.
2. In the Care plan panel, paste the `CAREPLAN_R4` JSON (from the test file) and click "Upload pasted plan".
3. Confirm it shows "Attached: Weight management plan (active)".
4. Open the clinician report PDF — confirm a "Care plan" section appears.
5. Reload the patient — confirm the attached plan still shows (served from the store).
6. Click "Remove" — confirm it returns to "No care plan attached."

- [ ] **Step 5: Commit (user runs when ready)**

```bash
git add frontend/src/components/CarePlanPanel.tsx frontend/src/components/PatientDetail.tsx
git commit -m "feat: care plan upload panel in patient detail"
```

---

## Final verification

- [ ] **Backend suite green:** `cd backend; .venv\Scripts\activate; pytest -q` — all tests pass, including the existing `test_integrations.py` and `test_reports.py`.
- [ ] **Frontend builds:** `cd frontend; npm run build` — no TypeScript errors.
- [ ] **End-to-end:** upload a plan via the dashboard, confirm it appears in the agent context endpoint (`GET /integrations/elevenlabs/patient-context?phone_number=+10000000001` with the `X-API-Key` header) — `care_plan` is populated and `context_summary` contains the `Care plan:` block.

---

## Notes / deviations from spec

- **Fixtures inline in the test module** rather than saved under `app/sample_data/`. Inlining keeps each TDD task self-contained and lets tests assert on specific field values; no functional difference.
- **Extractor is R4/R5-tolerant.** The HL7 build example uses R5 shapes (`plannedActivityReference`, `performedActivity`, `addresses[].reference` as a nested object); the primary fixtures use the more common R4 `activity.detail` shape. Both paths are covered by `_activities`, `_reference_label`, and `_goals`.
- **Latest-upload-wins:** a new upload replaces the previous plan for that patient (no versioning — explicitly out of scope).
