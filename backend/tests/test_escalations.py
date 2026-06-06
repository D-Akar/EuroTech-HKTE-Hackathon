"""Tests for the real-time clinical escalation feature.

No real network: telephony falls back to a 'failed/not configured' record when
ELEVENLABS_* env vars are absent (as under CI/pytest), and no nurse number is
set, so the escalation runs end-to-end without placing a call. Patient status is
an in-memory mutation, so tests restore it to keep isolation.
"""

from fastapi.testclient import TestClient

from app import data
from app.main import app

client = TestClient(app)


def _find_stable_patient() -> int:
    """A seeded patient that starts non-urgent, so the flip is observable."""
    patient = next(p for p in data.get_patients() if p.status.value != "urgent")
    return patient.id


def test_escalate_flips_status_to_urgent():
    pid = _find_stable_patient()
    original = data.get_patient(pid).status
    try:
        resp = client.post(
            f"/patients/{pid}/escalate",
            json={"reason": "Collapsed at home, family on the phone now."},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["patient_id"] == pid
        assert body["status"] == "urgent"
        assert body["previous_status"] == original.value
        assert body["reason"].startswith("Collapsed")

        # The patient now reads as urgent everywhere.
        assert client.get(f"/patients/{pid}").json()["status"] == "urgent"

        # And the escalation is logged.
        log = client.get("/escalations").json()
        assert any(e["id"] == body["id"] for e in log)
    finally:
        data.get_patient(pid).status = original


def test_escalate_unknown_patient_404():
    resp = client.post("/patients/9999/escalate", json={"reason": "x"})
    assert resp.status_code == 404


def test_escalate_without_nurse_notification_skips_call():
    pid = _find_stable_patient()
    original = data.get_patient(pid).status
    try:
        resp = client.post(
            f"/patients/{pid}/escalate",
            json={"reason": "Test, no call.", "notify_nurse": False},
        )
        assert resp.status_code == 200
        assert resp.json()["nurse_call"] is None
    finally:
        data.get_patient(pid).status = original


def test_escalation_appears_in_openapi_schema():
    """Swagger/OpenAPI is generated from the routers, so the new path is present."""
    schema = client.get("/openapi.json").json()
    assert "/patients/{patient_id}/escalate" in schema["paths"]
    assert "/events" in schema["paths"]
