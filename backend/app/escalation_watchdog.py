"""Server-side safety net: escalate even when the agent forgets the tool.

The ElevenLabs check-in agent reliably DETECTS an emergency - it announces "I am
escalating this to a nurse" - but does not reliably invoke its ``escalate_emergency``
tool, so the nurse is never actually dialled (observed: 3/3 demo calls, zero tool
calls). This watchdog makes escalation deterministic and independent of the LLM:
it watches a live call's transcript and triggers the normal escalation path the
moment the patient describes an emergency, or the agent narrates one.

Design choices:
- **Polls the conversations API** (``conversation_store.get_detail``) rather than the
  live monitor WebSocket, so it works without the ElevenLabs Enterprise monitor
  capability - the same read path the post-call summary already uses.
- **Idempotent**: at most one escalation per conversation, and it skips if the
  patient was already escalated very recently (e.g. the agent's tool call did fire).
- **Best-effort**: any failure ends the watch quietly; it never raises into the
  call path that spawned it.
"""

from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime, timedelta

from .models import Patient

log = logging.getLogger(__name__)

# Patient utterances that warrant dialling the nurse. Kept specific to avoid
# false alarms on mild mentions ("a bit tired"); when in doubt the agent's own
# escalation narration (below) is the second trigger.
_PATIENT_EMERGENCY = re.compile(
    r"chest pain|chest is tight|chest tightness|crushing|"
    r"can'?t breathe|cannot breathe|short of breath|shortness of breath|"
    r"dizzy|light[- ]?headed|faint|passing out|pass out|black(ing)? out|"
    r"call (my|the|a) nurse|contact (my|the|a) nurse|need a nurse|get(ting)? a nurse|"
    r"emergency|i fell|i'?ve fallen|i have fallen|fell down|fallen down|"
    r"bleeding|having a stroke|seizure",
    re.IGNORECASE,
)

# Agent narration that it is escalating / alerting the nurse. The agent reliably
# says this; treating it as a trigger turns its otherwise-empty words into a real
# escalation.
_AGENT_ESCALATION = re.compile(
    r"escalat|"
    r"nurse (has been|is being|will be|is) (alerted|notified|contacted|aware|on)|"
    r"alert(ing)? (a|the|your) nurse|notify(ing)? (a|the|your) nurse|"
    r"contacting (a|the|your) nurse|getting you (a|the) nurse|"
    r"nurse is on (their|the) way",
    re.IGNORECASE,
)

# Don't double-dial the nurse if an escalation for this patient just happened
# (e.g. the agent's tool call DID fire, or a wearable alert escalated).
_RECENT_ESCALATION_WINDOW = timedelta(seconds=120)

# Conversations already escalated by the watchdog - dedup within a single call.
_escalated_conversations: set[str] = set()


def reset() -> None:
    """Clear dedup state (used by tests for isolation)."""
    _escalated_conversations.clear()


def is_patient_emergency(text: str | None) -> bool:
    return bool(text and _PATIENT_EMERGENCY.search(text))


def is_agent_escalation_narration(text: str | None) -> bool:
    return bool(text and _AGENT_ESCALATION.search(text))


def should_escalate(role: str, text: str | None) -> bool:
    """True if this transcript turn means we should dial the nurse."""
    if role == "user":
        return is_patient_emergency(text)
    if role == "agent":
        return is_agent_escalation_narration(text)
    return False


def _reason(last_patient_text: str | None) -> str:
    if last_patient_text and last_patient_text.strip():
        return f'Patient said during the check-in call: "{last_patient_text.strip()}"'
    return "Possible emergency detected during the check-in call."


def _recently_escalated(patient_id: int, now: datetime) -> bool:
    """True if an escalation for this patient was recorded within the dedup window."""
    from .routers import escalations  # late import: avoids an import cycle

    cutoff = now - _RECENT_ESCALATION_WINDOW
    return any(
        rec.patient_id == patient_id and rec.triggered_at >= cutoff
        for rec in escalations.ESCALATIONS
    )


async def _do_escalate(patient: Patient, conversation_id: str, reason: str) -> bool:
    if conversation_id in _escalated_conversations:
        return False
    if _recently_escalated(patient.id, datetime.now()):
        _escalated_conversations.add(conversation_id)
        log.info(
            "Safety net: patient %s already escalated recently; skipping duplicate for %s.",
            patient.id, conversation_id,
        )
        return False
    _escalated_conversations.add(conversation_id)
    from .routers import escalations  # late import: avoids telephony<->escalations cycle

    log.info(
        "Safety net escalating patient %s from call %s (agent did not call the tool). %s",
        patient.id, conversation_id, reason,
    )
    await escalations.perform_escalation(
        patient, reason=reason, source="ai_phone_call_safety_net"
    )
    return True


def _scan(detail) -> tuple[bool, str | None]:
    """Scan a transcript for an emergency turn. Returns (should_escalate, reason)."""
    last_patient_text: str | None = None
    for turn in (getattr(detail, "transcript", None) or []):
        if turn.role == "user" and (turn.message or "").strip():
            last_patient_text = turn.message
        if should_escalate(turn.role, turn.message):
            return True, _reason(last_patient_text)
    return False, None


async def watch_conversation(
    patient: Patient,
    conversation_id: str,
    *,
    detail_source=None,
    poll_secs: float = 4.0,
    max_secs: float = 240.0,
) -> bool:
    """Poll a live call's transcript and escalate on the first emergency turn.

    Returns True if it escalated. Best-effort: never raises. ``detail_source`` is
    an async ``(conversation_id) -> ConversationDetail | None`` callable, injectable
    for tests; defaults to ``conversation_store.get_detail``.
    """
    if detail_source is None:
        from . import conversation_store

        detail_source = conversation_store.get_detail

    waited = 0.0
    try:
        while waited <= max_secs:
            detail = await detail_source(conversation_id)
            if detail is not None:
                hit, reason = _scan(detail)
                if hit:
                    return await _do_escalate(patient, conversation_id, reason)
                if getattr(detail, "status", None) in ("done", "failed"):
                    break  # call ended, final transcript scanned, no emergency
            await asyncio.sleep(poll_secs)
            waited += poll_secs
    except Exception:  # noqa: BLE001 - a watchdog must never crash the call path
        log.exception("Safety-net watch failed for %s", conversation_id)
    return False
