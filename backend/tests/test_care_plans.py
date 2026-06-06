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
    assert "[in-progress] Weight management classes - three times a week" in text
    assert "Patient is motivated to lose weight." in text

    bare = _extract({"resourceType": "CarePlan", "title": "Minimal"})
    assert bare.rendered_text == 'Care plan: "Minimal".'


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


def _unique_named_patient():
    """A patient whose display name is unique in the current roster.

    Subject-matching is by display name, so the target must be unique to be
    deterministic. We read the *live* ``data.PATIENTS`` because the FHIR overlay
    mutates that global (renaming seed patients) whenever Mongo is reachable -
    so a hardcoded seed name like "Margaret Holloway" breaks locally with the
    Docker DB up while still passing on CI without it. Deriving the name keeps
    the test correct in both environments.
    """
    from app import data

    names = [p.name for p in data.PATIENTS]
    return next(p for p in data.PATIENTS if names.count(p.name) == 1)


def test_get_patient_by_subject():
    from app import data

    target = _unique_named_patient()
    p = data.get_patient_by_subject(target.name)
    assert p is not None and p.name == target.name

    assert data.get_patient_by_subject(target.name.lower()) is not None  # case-insensitive
    assert data.get_patient_by_subject("Definitely Nobody 9999") is None
    assert data.get_patient_by_subject("") is None


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
    # Build the subject from a real current patient so the auto-match lands
    # deterministically even when the FHIR overlay has renamed seed patients.
    target = _unique_named_patient()
    plan = dict(CAREPLAN_R4, subject={"reference": f"Patient/{target.id}", "display": target.name})
    r = client.post("/care-plans", content=json.dumps(plan))
    assert r.status_code == 200, r.text
    assert r.json()["patient_id"] == target.id  # matched by subject display name


def test_auto_match_no_subject_match_422(client):
    plan = dict(CAREPLAN_R4, subject={"display": "Unknown Person"})
    r = client.post("/care-plans", content=json.dumps(plan))
    assert r.status_code == 422
    assert "Unknown Person" in r.json()["detail"]


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


def test_report_pdf_includes_care_plan(client):
    body = json.dumps(CAREPLAN_R4)
    assert client.post("/patients/1/care-plan", content=body).status_code == 200

    r = client.get("/patients/1/report.pdf")
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert r.content[:4] == b"%PDF"
