"""Auto-escalation from live wearable vitals (app/live_monitor.py).

Verifies that an out-of-range live reading flips the patient to urgent, places one
ElevenLabs emergency call per episode, and routes to the on-call nurse when the
patient does not answer.
"""

import asyncio
import datetime

import pytest

from app import conversation_store, data, live_monitor, wearable_source
from app.config import settings
from app.models import CallRecord, ConversationDetail, ConversationTurn, PatientStatus
from app.services import telephony

# Capture the real follow-up before the autouse fixture stubs it, so the dedicated
# nurse-routing tests can drive it directly.
_REAL_FOLLOWUP = live_monitor._route_to_nurse_if_unanswered

URGENT = {
    "status": "urgent",
    "alerts": [
        {"kind": "high_heart_rate", "severity": "critical",
         "message": "Heart rate 130 bpm is critically high"},
    ],
}
STABLE = {"status": "stable", "alerts": []}
NURSE = "+41999000111"


def _call(conversation_id="conv-1", status="initiated", to="+85290000000"):
    return CallRecord(id=1, patient_id=7, triggered_at=datetime.datetime.now(),
                      kind="auto", to_number=to, status=status,
                      conversation_id=conversation_id)


@pytest.fixture
def patient_id():
    return wearable_source.REAL_PATIENT_ID


@pytest.fixture(autouse=True)
def _isolate(monkeypatch, patient_id):
    live_monitor.reset()
    p = data.get_patient(patient_id)
    monkeypatch.setattr(p, "phone_number", "+85290000000", raising=False)
    p.status = PatientStatus.stable
    monkeypatch.setattr(settings, "nurse_phone_number", NURSE)
    # Default off for the behavioural tests; the cooldown test opts back in.
    monkeypatch.setattr(live_monitor, "_EMERGENCY_COOLDOWN_SECS", 0.0)

    calls: list[tuple[str, str]] = []  # (to_number, kind)

    async def fake_place_call(patient, to_number, questions, kind="instant", **kwargs):
        calls.append((to_number, kind))
        return _call(to=to_number, status="initiated")

    monkeypatch.setattr(telephony, "place_call", fake_place_call)

    # Stub the background nurse follow-up for the latch/endpoint tests so they don't
    # spawn real timers; the dedicated tests below exercise the real follow-up.
    async def noop_followup(*a, **k):
        return None

    monkeypatch.setattr(live_monitor, "_route_to_nurse_if_unanswered", noop_followup)
    return calls


def test_urgent_flips_status_and_calls_once(patient_id, _isolate):
    calls = _isolate
    rec = asyncio.run(live_monitor.maybe_autocall(patient_id, URGENT))
    assert rec is not None and rec.status == "initiated"
    assert data.get_patient(patient_id).status == PatientStatus.urgent
    assert len(calls) == 1 and calls[0][1] == "auto"  # one patient call

    assert asyncio.run(live_monitor.maybe_autocall(patient_id, URGENT)) is None
    assert len(calls) == 1


def test_rearms_after_recovery(patient_id, _isolate):
    calls = _isolate
    asyncio.run(live_monitor.maybe_autocall(patient_id, URGENT))
    assert len(calls) == 1
    assert asyncio.run(live_monitor.maybe_autocall(patient_id, STABLE)) is None
    asyncio.run(live_monitor.maybe_autocall(patient_id, URGENT))
    assert len(calls) == 2


def test_emergency_cooldown_suppresses_repeat(monkeypatch, patient_id, _isolate):
    """A second emergency for the same patient inside the cooldown is suppressed,
    so a bouncing watch HR / second tab / reload can't spam the patient + nurse."""
    calls = _isolate
    monkeypatch.setattr(live_monitor, "_EMERGENCY_COOLDOWN_SECS", 180.0)
    patient = data.get_patient(patient_id)

    rec1 = asyncio.run(live_monitor.emergency_call(patient, "Heart rate critically high"))
    rec2 = asyncio.run(live_monitor.emergency_call(patient, "Heart rate critically high"))

    assert rec1 is not None  # first escalation goes out
    assert rec2 is None  # second within cooldown is suppressed
    assert sum(1 for (_to, kind) in calls if kind == "auto") == 1  # one patient dial only


def test_stable_never_calls(patient_id, _isolate):
    calls = _isolate
    assert asyncio.run(live_monitor.maybe_autocall(patient_id, STABLE)) is None
    assert len(calls) == 0
    assert data.get_patient(patient_id).status == PatientStatus.stable


def test_live_endpoint_autocalls_on_urgent(monkeypatch, patient_id, _isolate):
    """End-to-end: GET /live with an out-of-range reading flips the patient to
    urgent and places exactly one emergency call (the running-on-stage demo)."""
    from fastapi.testclient import TestClient

    from app import live_source
    from app.main import app

    calls = _isolate
    monkeypatch.setattr(live_source, "live_vitals", lambda: {
        "source": "live",
        "heart_rate": {"value": 134, "unit": "bpm", "at": "2024-06-08T14:35:00+08:00"},
        "spo2": {"value": 97, "unit": "%", "at": "2024-06-08T14:35:00+08:00"},
        "stress": None,
        "steps": {"value": 5200, "unit": "steps", "at": "2024-06-08T14:35:00+08:00"},
    })

    client = TestClient(app)
    body = client.get(f"/patients/{patient_id}/live").json()
    assert body["status"] == "urgent"
    assert len(calls) == 1
    assert data.get_patient(patient_id).status == PatientStatus.urgent

    client.get(f"/patients/{patient_id}/live")
    assert len(calls) == 1  # no redial within the same episode


# --- No-answer -> nurse routing ---------------------------------------------

def test_patient_answered_detection():
    answered = ConversationDetail(
        conversation_id="c", status="done", ready=True, call_duration_secs=42,
        transcript=[ConversationTurn(role="user", message="hello, I'm fine")],
    )
    no_turns_short = ConversationDetail(
        conversation_id="c", status="done", ready=True, call_duration_secs=2, transcript=[],
    )
    assert live_monitor._patient_answered(answered) is True
    assert live_monitor._patient_answered(no_turns_short) is False
    assert live_monitor._patient_answered(None) is False  # unknown -> fail safe


def test_unanswered_routes_to_nurse(monkeypatch, _isolate):
    calls = _isolate
    patient = data.get_patient(wearable_source.REAL_PATIENT_ID)

    async def no_pickup(_cid):
        return ConversationDetail(conversation_id=_cid, status="failed", ready=True,
                                  call_duration_secs=0, transcript=[])

    monkeypatch.setattr(conversation_store, "get_detail", no_pickup)
    asyncio.run(_REAL_FOLLOWUP(patient, _call(), "Heart rate critically high", 0))

    assert (NURSE, "instant") in calls  # nurse was dialed


def test_answered_skips_nurse(monkeypatch, _isolate):
    calls = _isolate
    patient = data.get_patient(wearable_source.REAL_PATIENT_ID)

    async def picked_up(_cid):
        return ConversationDetail(
            conversation_id=_cid, status="done", ready=True, call_duration_secs=40,
            transcript=[ConversationTurn(role="user", message="I'm okay")],
        )

    monkeypatch.setattr(conversation_store, "get_detail", picked_up)
    asyncio.run(_REAL_FOLLOWUP(patient, _call(), "Heart rate critically high", 0))

    assert all(to != NURSE for (to, _) in calls)  # nurse NOT dialed
