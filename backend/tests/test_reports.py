"""Tests for the clinician PDF report: summary logic, renderer, and endpoint."""

from datetime import date, datetime

from fastapi.testclient import TestClient

from app.main import app
from app.models import CheckIn, Patient, PatientStatus, WearableReading
from app.report_pdf import build_report_pdf
from app.report_summary import build_summary

client = TestClient(app)


def _checkin(day: int, pain: int, answered: bool = True) -> CheckIn:
    return CheckIn(
        id=day,
        patient_id=1,
        date=date(2026, 6, 6),
        mood="content",
        pain_level=pain,
        answered=answered,
        notes="ok",
    )


def _wearable(day: int, hr: int, sleep: float, steps: int) -> WearableReading:
    return WearableReading(
        id=day,
        patient_id=1,
        timestamp=datetime(2026, 6, 6, 9),
        heart_rate=hr,
        steps=steps,
        sleep_hours=sleep,
    )


# --- build_summary (the testable mock brain), input is newest-first -----------


def test_rising_pain_is_worsening():
    # newest-first: pain rose from 2 (oldest) to 8 (newest)
    checkins = [_checkin(0, 8), _checkin(1, 6), _checkin(2, 3), _checkin(3, 2)]
    summary = build_summary(checkins, [])
    pain = next(t for t in summary.trends if t.label == "Pain level")
    assert pain.direction == "worsening"
    assert pain.arrow == "↑"
    assert pain.current == 8
    assert pain.series == [2, 3, 6, 8]  # oldest→newest


def test_rising_sleep_is_improving():
    wearables = [
        _wearable(0, 70, 8.5, 3000),
        _wearable(1, 70, 7.5, 3000),
        _wearable(2, 70, 5.5, 3000),
        _wearable(3, 70, 5.0, 3000),
    ]
    summary = build_summary([], wearables)
    sleep = next(t for t in summary.trends if t.label == "Sleep")
    assert sleep.direction == "improving"
    assert sleep.arrow == "↑"


def test_flat_metric_is_stable():
    wearables = [_wearable(d, 70, 7.0, 3000) for d in range(4)]
    summary = build_summary([], wearables)
    hr = next(t for t in summary.trends if t.label == "Heart rate")
    assert hr.direction == "stable"
    assert hr.arrow == "→"


def test_checkins_narrative_counts_answered():
    checkins = [_checkin(0, 3), _checkin(1, 3, answered=False), _checkin(2, 3), _checkin(3, 3)]
    summary = build_summary(checkins, [])
    assert "Answered 3 of the last 4" in summary.checkins_narrative


def test_empty_history_is_handled():
    summary = build_summary([], [])
    assert summary.trends == []
    assert "No check-in" in summary.checkins_narrative


# --- build_report_pdf renderer ------------------------------------------------


def test_build_report_pdf_returns_pdf_bytes():
    patient = Patient(
        id=1, name="Test Patient", age=80, status=PatientStatus.attention,
        practice="Test Clinic", district="Central",
    )
    checkins = [_checkin(0, 5), _checkin(1, 4), _checkin(2, 3), _checkin(3, 2)]
    wearables = [_wearable(d, 80, 6.0, 1200) for d in range(4)]
    summary = build_summary(checkins, wearables)
    pdf = build_report_pdf(patient, summary, checkins, wearables)
    assert isinstance(pdf, bytes)
    assert pdf.startswith(b"%PDF")
    assert len(pdf) > 1000


# --- endpoint -----------------------------------------------------------------


def test_report_endpoint_returns_pdf():
    resp = client.get("/patients/1/report.pdf")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert resp.content.startswith(b"%PDF")
    assert "filename=" in resp.headers.get("content-disposition", "")


def test_report_endpoint_unknown_patient_404():
    assert client.get("/patients/999/report.pdf").status_code == 404
