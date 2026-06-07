"""Tests for the ElevenLabs patient-context server tool endpoint."""

import os

import pytest
from fastapi.testclient import TestClient

from app.main import app

TOOL_KEY = "test-tool-key-12345"
ENDPOINT = "/integrations/elevenlabs/patient-context"


@pytest.fixture(autouse=True)
def tool_api_key(monkeypatch):
    monkeypatch.setenv("ELEVENLABS_TOOL_API_KEY", TOOL_KEY)
    # Settings is instantiated at import; reload the module value.
    from app.config import settings

    monkeypatch.setattr(settings, "elevenlabs_tool_api_key", TOOL_KEY)


@pytest.fixture
def client():
    return TestClient(app)


def test_missing_api_key_returns_401(client):
    resp = client.get(ENDPOINT, params={"phone_number": "+10000000001"})
    assert resp.status_code == 401


def test_wrong_api_key_returns_401(client):
    resp = client.get(
        ENDPOINT,
        params={"phone_number": "+10000000001"},
        headers={"X-API-Key": "wrong-key"},
    )
    assert resp.status_code == 401


def test_lookup_by_phone_returns_full_context(client):
    resp = client.get(
        ENDPOINT,
        params={"phone_number": "+10000000001"},
        headers={"X-API-Key": TOOL_KEY},
    )
    assert resp.status_code == 200
    body = resp.json()
    # Don't hardcode the name: when MongoDB is populated, the FHIR overlay
    # (app/fhir_source.py) can replace a seed patient's name with a real record.
    # The phone-number binding and the name<->summary consistency are what matter.
    name = body["patient"]["name"]
    assert name
    assert body["patient"]["phone_number"] == "+10000000001"
    assert len(body["checkins"]) > 0
    assert len(body["wearables"]) > 0
    assert "questions" in body["call_config"]
    assert name in body["context_summary"]


def test_lookup_without_plus_prefix(client):
    resp = client.get(
        ENDPOINT,
        params={"phone_number": "10000000001"},
        headers={"X-API-Key": TOOL_KEY},
    )
    assert resp.status_code == 200
    assert resp.json()["patient"]["id"] == 1


def test_unknown_phone_returns_404(client):
    resp = client.get(
        ENDPOINT,
        params={"phone_number": "+19999999999"},
        headers={"X-API-Key": TOOL_KEY},
    )
    assert resp.status_code == 404


def test_missing_phone_number_returns_422(client):
    resp = client.get(ENDPOINT, headers={"X-API-Key": TOOL_KEY})
    assert resp.status_code == 422


# --- escalate_emergency webhook (POST /integrations/elevenlabs/escalate) ---

ESCALATE_ENDPOINT = "/integrations/elevenlabs/escalate"


@pytest.fixture
def stub_nurse_call(monkeypatch):
    """Stub the outbound nurse call so escalate tests never place a real call.

    The bug under test is patient *resolution* in the webhook, which runs before
    any call is placed; stubbing telephony keeps the test fast and side-effect free.
    """
    import app.routers.escalations as escalations
    from datetime import datetime

    from app.models import CallRecord

    async def fake_place_call(patient, to_number, *args, **kwargs):
        return CallRecord(
            id=999,
            patient_id=patient.id,
            triggered_at=datetime.now(),
            kind="instant",
            to_number=to_number,
            status="initiated",
        )

    monkeypatch.setattr(escalations.telephony, "place_call", fake_place_call)


def test_escalate_by_patient_name_resolves(client, stub_nurse_call):
    # The ElevenLabs agent only knows {{patient_name}}, so it sends the patient's
    # NAME as patient_id. The webhook must resolve it, not reject it with 422.
    resp = client.post(
        ESCALATE_ENDPOINT,
        json={"patient_id": "Lavinia Heaney", "reason": "Reports sudden dizziness"},
        headers={"X-API-Key": TOOL_KEY},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["patient_name"] == "Lavinia Heaney"
    assert body["status"] == "urgent"
    assert body["nurse_call"] is not None


def test_escalate_by_numeric_id_still_works(client, stub_nurse_call):
    # The injected {{patient_id}} dynamic variable arrives as a numeric string.
    resp = client.post(
        ESCALATE_ENDPOINT,
        json={"patient_id": "3", "reason": "Chest pain"},
        headers={"X-API-Key": TOOL_KEY},
    )
    assert resp.status_code == 200
    assert resp.json()["patient_id"] == 3


def test_escalate_unknown_patient_returns_404(client, stub_nurse_call):
    resp = client.post(
        ESCALATE_ENDPOINT,
        json={"patient_id": "Nobody McGhost", "reason": "x"},
        headers={"X-API-Key": TOOL_KEY},
    )
    assert resp.status_code == 404
