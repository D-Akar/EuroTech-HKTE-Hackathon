"""The server-side safety net escalates when the agent narrates but never calls the tool."""

import asyncio
from types import SimpleNamespace

import pytest

from app import escalation_watchdog as wd
from app.models import ConversationTurn, Patient, PatientStatus


@pytest.fixture(autouse=True)
def _isolation(monkeypatch):
    wd.reset()
    import app.routers.escalations as escalations

    monkeypatch.setattr(escalations, "ESCALATIONS", [])
    calls = []

    async def fake_perform_escalation(patient, reason, source="phone_call", **kw):
        calls.append({"patient": patient, "reason": reason, "source": source})
        return SimpleNamespace(patient_id=patient.id, reason=reason)

    monkeypatch.setattr(escalations, "perform_escalation", fake_perform_escalation)
    return calls


def _patient():
    return Patient(id=7, name="Eleanor Pang", age=80, status=PatientStatus.stable, practice="X")


def _detail(turns, status="in-progress"):
    return SimpleNamespace(
        transcript=[ConversationTurn(role=r, message=m) for r, m in turns],
        status=status,
    )


# --- pure detection ---

@pytest.mark.parametrize("text", ["I feel very dizzy", "Can you call my nurse?", "I have chest pain", "I think I fell"])
def test_patient_emergency_phrases_detected(text):
    assert wd.is_patient_emergency(text)


@pytest.mark.parametrize("text", ["I slept badly", "My knee aches a little", "I'm feeling okay"])
def test_mild_patient_phrases_not_emergencies(text):
    assert not wd.is_patient_emergency(text)


def test_agent_escalation_narration_detected():
    assert wd.is_agent_escalation_narration("I am escalating this to a nurse right now")
    assert wd.is_agent_escalation_narration("A nurse has been alerted and will follow up")
    assert not wd.is_agent_escalation_narration("How are you feeling today?")


def test_should_escalate_routes_by_role():
    # A mild user line is not an emergency, but the agent announcing escalation is.
    assert not wd.should_escalate("user", "I'm a little tired")
    assert wd.should_escalate("agent", "I am escalating this now")
    assert wd.should_escalate("user", "I feel very dizzy")


# --- watch loop ---

def _source_for(detail):
    async def source(_cid):
        return detail

    return source


def test_watch_escalates_on_patient_emergency(_isolation):
    detail = _detail([("agent", "How are you?"), ("user", "Very, very dizzy")], status="done")
    escalated = asyncio.run(
        wd.watch_conversation(_patient(), "conv_1", detail_source=_source_for(detail), poll_secs=0, max_secs=0)
    )
    assert escalated is True
    assert len(_isolation) == 1
    assert "dizzy" in _isolation[0]["reason"].lower()
    assert _isolation[0]["source"] == "ai_phone_call_safety_net"


def test_watch_escalates_on_agent_narration_even_if_patient_vague(_isolation):
    detail = _detail([("user", "uh, elevated"), ("agent", "I am escalating this to a nurse")], status="done")
    escalated = asyncio.run(
        wd.watch_conversation(_patient(), "conv_2", detail_source=_source_for(detail), poll_secs=0, max_secs=0)
    )
    assert escalated is True
    assert len(_isolation) == 1


def test_watch_does_not_escalate_when_no_emergency(_isolation):
    detail = _detail([("agent", "How are you?"), ("user", "I'm fine, thanks")], status="done")
    escalated = asyncio.run(
        wd.watch_conversation(_patient(), "conv_3", detail_source=_source_for(detail), poll_secs=0, max_secs=0)
    )
    assert escalated is False
    assert _isolation == []


def test_watch_escalates_at_most_once_per_conversation(_isolation):
    detail = _detail([("user", "I feel very dizzy")], status="done")
    source = _source_for(detail)
    p = _patient()
    asyncio.run(wd.watch_conversation(p, "conv_4", detail_source=source, poll_secs=0, max_secs=0))
    asyncio.run(wd.watch_conversation(p, "conv_4", detail_source=source, poll_secs=0, max_secs=0))
    assert len(_isolation) == 1
