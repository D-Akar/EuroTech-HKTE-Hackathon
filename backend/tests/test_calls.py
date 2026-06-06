"""Tests for the outbound check-in call feature.

No real network: telephony falls back to a 'failed/not configured' record when
ELEVENLABS_* env vars are absent (as they are under CI/pytest), so the trigger
endpoint is exercised end-to-end without placing a call. The scheduler is never
started here (TestClient is used without its lifespan), so no timers fire.
"""

from fastapi.testclient import TestClient

from app import data
from app.main import app
from app.services import telephony

client = TestClient(app)


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
    variables = telephony.build_dynamic_variables(patient, ["How are you?"])
    assert variables["patient_name"] == patient.name
    assert variables["patient_age"] == str(patient.age)
    assert "1. How are you?" in variables["questions"]
    assert "check-in" in variables["recent_summary"].lower()
