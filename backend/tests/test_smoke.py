"""Smoke tests: the app starts and core endpoints return seeded data."""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health():
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_list_patients():
    resp = client.get("/patients")
    assert resp.status_code == 200
    patients = resp.json()
    assert len(patients) == 30
    assert {"id", "name", "age", "status", "practice", "district"} <= patients[0].keys()
    # Every patient is placed in a Hong Kong district for the city twin.
    assert all(p["district"] for p in patients)


def test_patient_checkins_and_wearables():
    resp = client.get("/patients/1/checkins")
    assert resp.status_code == 200
    assert len(resp.json()) == 4

    resp = client.get("/patients/1/wearables")
    assert resp.status_code == 200
    assert len(resp.json()) == 4


def test_unknown_patient_404():
    assert client.get("/patients/999").status_code == 404
    assert client.get("/patients/999/checkins").status_code == 404
