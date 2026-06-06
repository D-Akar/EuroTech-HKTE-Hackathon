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
    assert body["patient"]["name"] == "Margaret Holloway"
    assert body["patient"]["phone_number"] == "+10000000001"
    assert len(body["checkins"]) > 0
    assert len(body["wearables"]) > 0
    assert "questions" in body["call_config"]
    assert "Margaret Holloway" in body["context_summary"]


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
