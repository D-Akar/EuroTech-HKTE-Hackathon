"""Tests for the outbound check-in call feature.

No real network: telephony falls back to a 'failed/not configured' record when
ELEVENLABS_* env vars are absent (as they are under CI/pytest), so the trigger
endpoint is exercised end-to-end without placing a call. The scheduler is never
started here (TestClient is used without its lifespan), so no timers fire.
"""

import asyncio

import pytest
from fastapi.testclient import TestClient

from app import conversation_store, data
from app.main import app
from app.services import telephony

client = TestClient(app)


@pytest.fixture(autouse=True)
def _no_real_calls(monkeypatch):
    """Never place a real outbound call during tests, even when .env is configured.

    Forces telephony into its 'not configured' branch so place_call records a
    failed attempt instead of dialing ElevenLabs/Twilio.
    """
    monkeypatch.setattr(telephony.settings, "elevenlabs_api_key", "")


def test_patient_has_phone_number():
    resp = client.get("/patients/1")
    assert resp.status_code == 200
    assert resp.json()["phone_number"]  # non-empty seeded number


def test_trigger_records_call():
    resp = client.post("/patients/1/calls/trigger", json={})
    assert resp.status_code == 200
    record = resp.json()
    assert record["patient_id"] == 1
    assert record["kind"] == "instant"
    assert record["status"] in {"initiated", "failed"}

    # The call now appears in history.
    hist = client.get("/patients/1/calls").json()
    assert any(r["id"] == record["id"] for r in hist)


def test_trigger_unknown_patient_404():
    assert client.post("/patients/999/calls/trigger", json={}).status_code == 404


def test_config_roundtrip():
    # Defaults exist on first read.
    resp = client.get("/patients/4/calls/config")
    assert resp.status_code == 200
    assert len(resp.json()["questions"]) > 0

    # Update and read back.
    new_questions = ["Did you eat today?", "Any falls?"]
    put = client.put(
        "/patients/4/calls/config",
        json={"questions": new_questions, "greeting": None},
    )
    assert put.status_code == 200
    assert put.json()["questions"] == new_questions
    assert client.get("/patients/4/calls/config").json()["questions"] == new_questions


def test_schedule_create_list_cancel():
    created = client.post(
        "/patients/2/calls/schedules",
        json={"scheduled_at": "2030-01-01T09:00:00", "recurring": False},
    )
    assert created.status_code == 200
    schedule_id = created.json()["id"]

    listed = client.get("/patients/2/calls/schedules").json()
    assert any(s["id"] == schedule_id for s in listed)

    cancelled = client.delete(f"/patients/2/calls/schedules/{schedule_id}")
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"

    listed_after = client.get("/patients/2/calls/schedules").json()
    assert all(s["id"] != schedule_id for s in listed_after)


def test_cancel_unknown_schedule_404():
    assert client.delete("/patients/2/calls/schedules/999999").status_code == 404


def test_build_dynamic_variables():
    patient = data.get_patient(1)
    variables = asyncio.run(telephony.build_dynamic_variables(patient, ["How are you?"]))
    assert variables["patient_name"] == patient.name
    assert variables["patient_age"] == str(patient.age)
    assert "1. How are you?" in variables["questions"]
    assert "check-in" in variables["recent_summary"].lower()


def test_recent_summary_prepends_prior_call_digest(monkeypatch):
    async def fake_digest(patient_id):
        return 'Previous check-in (2026-06-05): mood "tired"; pain 6/10.'

    monkeypatch.setattr(conversation_store, "latest_digest", fake_digest)
    summary = asyncio.run(telephony.build_recent_summary(1))
    assert summary.startswith("Previous check-in (2026-06-05):")
    assert 'mood "tired"' in summary


def test_recent_summary_unchanged_without_prior_digest(monkeypatch):
    async def no_digest(patient_id):
        return None

    monkeypatch.setattr(conversation_store, "latest_digest", no_digest)
    summary = asyncio.run(telephony.build_recent_summary(1))
    assert "Previous check-in" not in summary
    assert "check-in" in summary.lower()  # still has the existing content


# --- Issue 2: guard against dialing placeholder (mock) numbers ---------------


def test_is_placeholder_phone():
    assert data.is_placeholder_phone("+10000000001") is True
    # Use the prefix constant, not PATIENTS[1]: when MongoDB is populated the FHIR
    # overlay replaces featured slots' phones with real ones.
    assert data.is_placeholder_phone(data.PLACEHOLDER_PHONE_PREFIX + "0099") is True
    assert data.is_placeholder_phone("+85291234567") is False
    assert data.is_placeholder_phone("") is False


def test_place_call_blocks_placeholder_number():
    patient = data.get_patient(1)
    record = asyncio.run(telephony.place_call(patient, "+10000000001", ["How are you?"]))
    assert record.status == "failed"
    assert "real phone number" in record.error.lower()
    assert record.to_number == "+10000000001"


def test_place_call_real_number_passes_guard_then_hits_config(monkeypatch):
    # A real number is not blocked by the guard. Force telephony "unconfigured"
    # so the test never attempts a real outbound call regardless of local .env.
    monkeypatch.setattr(telephony.settings, "elevenlabs_api_key", "")
    patient = data.get_patient(1)
    record = asyncio.run(telephony.place_call(patient, "+85291234567", ["Q?"]))
    assert record.status == "failed"
    assert "not configured" in record.error.lower()


# --- Issue 3a: clinical data folded into the call context --------------------


def test_recent_summary_includes_medications_procedures_care_plan(monkeypatch):
    import json

    from app import care_plan_store, conversation_store, fhir_source
    from app.models import MedicalProfile, Medication, Procedure

    pid = 1
    profile = MedicalProfile(
        patient_id=pid,
        fhir_id="x",
        active_medications=[Medication(name="Lisinopril", frequency="once daily")],
        recent_procedures=[Procedure(name="Knee replacement", date="2025-02-01")],
    )
    monkeypatch.setattr(fhir_source, "get_profile", lambda p: profile if p == pid else None)

    async def no_digest(p):
        return None

    monkeypatch.setattr(conversation_store, "latest_digest", no_digest)

    ctx = care_plan_store.parse_care_plan(
        json.dumps({"resourceType": "CarePlan", "status": "active", "title": "Mobility plan"})
    )
    care_plan_store.set(pid, "{}", ctx)
    try:
        summary = asyncio.run(telephony.build_recent_summary(pid))
        assert "Lisinopril" in summary
        assert "Knee replacement" in summary
        assert "Mobility plan" in summary
    finally:
        care_plan_store._STORE.clear()


# --- Issue 3b: editable agent system prompt (overrides) ----------------------


def test_build_overrides_system_prompt():
    from app.models import CallConfig

    cfg = CallConfig(patient_id=1, questions=[], system_prompt="Be very gentle.")
    assert telephony.build_overrides(cfg) == {
        "agent": {"prompt": {"prompt": "Be very gentle."}}
    }


def test_build_overrides_greeting_as_first_message():
    from app.models import CallConfig

    cfg = CallConfig(patient_id=1, questions=[], greeting="Hello dear.")
    assert telephony.build_overrides(cfg) == {"agent": {"first_message": "Hello dear."}}


def test_build_overrides_none_when_empty():
    from app.models import CallConfig

    cfg = CallConfig(patient_id=1, questions=[])
    assert telephony.build_overrides(cfg) is None


def test_build_call_payload_includes_override(monkeypatch):
    from app.models import CallConfig

    async def no_digest(p):
        return None

    monkeypatch.setattr(conversation_store, "latest_digest", no_digest)
    cfg = CallConfig(patient_id=1, questions=["Q?"], system_prompt="Gentle.")
    payload = asyncio.run(
        telephony.build_call_payload(data.get_patient(1), "+85291234567", ["Q?"], cfg)
    )
    cc = payload["conversation_initiation_client_data"]
    assert cc["conversation_config_override"] == {"agent": {"prompt": {"prompt": "Gentle."}}}
    assert "dynamic_variables" in cc


def test_config_roundtrip_system_prompt():
    put = client.put(
        "/patients/5/calls/config",
        json={"questions": ["Q?"], "greeting": None, "system_prompt": "Speak slowly."},
    )
    assert put.status_code == 200
    assert put.json()["system_prompt"] == "Speak slowly."
    assert client.get("/patients/5/calls/config").json()["system_prompt"] == "Speak slowly."


# --- Editable patient phone number -------------------------------------------


def test_update_phone_persists_to_patient():
    # Use the last slot so we don't perturb patients other tests rely on.
    pid = len(data.PATIENTS)
    resp = client.put(f"/patients/{pid}/phone", json={"phone_number": "+852 9123 4567"})
    assert resp.status_code == 200
    # Returned normalized to E.164 (formatting stripped).
    assert resp.json()["phone_number"] == "+85291234567"
    # And the live patient now reflects it, so future calls dial the new number.
    assert client.get(f"/patients/{pid}").json()["phone_number"] == "+85291234567"


def test_update_phone_rejects_empty():
    pid = len(data.PATIENTS)
    resp = client.put(f"/patients/{pid}/phone", json={"phone_number": "  --  "})
    assert resp.status_code == 400


def test_update_phone_unknown_patient_404():
    resp = client.put("/patients/999/phone", json={"phone_number": "+85291234567"})
    assert resp.status_code == 404
