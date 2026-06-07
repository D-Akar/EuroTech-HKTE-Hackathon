"""The consent-gated check-in prompt must force a real escalate_emergency tool call.

This prompt is sent as a per-call ``system_prompt`` override, which REPLACES the
ElevenLabs dashboard prompt - so the forceful "actually call the tool, do not just
say it" guardrail has to live here too. Without it the agent narrates an
escalation ("a nurse has been alerted") without ever invoking the tool, and no
nurse call is placed.
"""

from app import checkin_agent
from app.models import Patient, PatientStatus


def _patient() -> Patient:
    return Patient(
        id=3,
        name="Dorothy Williams",
        age=82,
        status=PatientStatus.stable,
        practice="Test Practice",
        district="Test",
        phone_number="+10000000003",
    )


def test_checkin_prompt_names_the_escalation_tool():
    prompt = checkin_agent.system_prompt(_patient())
    assert "escalate_emergency" in prompt


def test_checkin_prompt_forbids_claiming_escalation_without_calling_the_tool():
    # The exact failure we saw: the agent said "the nurse has been alerted" but
    # never called the tool. The prompt must explicitly forbid that.
    prompt = checkin_agent.system_prompt(_patient()).lower()
    assert "critical failure" in prompt
    assert "without actually calling" in prompt


def test_checkin_prompt_orders_tool_call_before_reassurance():
    prompt = checkin_agent.system_prompt(_patient()).lower()
    assert "first" in prompt
    # "dizzy" is the canonical demo trigger; the prompt should treat it as urgent.
    assert "dizz" in prompt or "severe, sudden" in prompt
