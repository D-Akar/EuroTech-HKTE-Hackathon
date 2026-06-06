"""Tests for the Garmin wearable integration (featured patient + summary/alerts/live)."""

from fastapi.testclient import TestClient

from app import wearable_source
from app.main import app

client = TestClient(app)
FEATURED = wearable_source.REAL_PATIENT_ID


def test_featured_patient_has_real_trends():
    readings = client.get(f"/patients/{FEATURED}/wearables").json()
    # Real export spans many days, unlike the 4-day seeded mock patients.
    assert len(readings) > 4
    assert {"heart_rate", "steps", "sleep_hours", "timestamp"} <= readings[0].keys()


def test_non_featured_patient_stays_seeded():
    readings = client.get("/patients/1/wearables").json()
    assert len(readings) == 4


def test_summary_endpoint_returns_stats():
    s = client.get(f"/patients/{FEATURED}/summary").json()
    assert s["days"] > 0
    assert s["heart_rate"] and {"min", "max", "avg"} <= s["heart_rate"].keys()


def test_alerts_endpoint_returns_list():
    a = client.get(f"/patients/{FEATURED}/alerts").json()
    assert isinstance(a, list)


def test_live_endpoint_returns_snapshot():
    live = client.get(f"/patients/{FEATURED}/live").json()
    # "live" when a cached token works, otherwise a safe "export-fallback".
    assert live["source"] in {"live", "export-fallback"}


def test_vitals_endpoint_returns_rich_samples():
    v = client.get(f"/patients/{FEATURED}/vitals", params={"kind": "spo2", "limit": 1}).json()
    assert isinstance(v, list)
