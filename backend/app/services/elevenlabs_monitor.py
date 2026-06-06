"""Stream a *live* conversation's transcript from the ElevenLabs monitor socket.

``parse_monitor_event`` and ``format_sse`` are pure (no I/O) so they can be tested
against captured event bodies. ``stream_turns`` wraps them with the upstream
WebSocket and is the only network seam; it is tolerant of every failure mode
(not-configured, connect rejected, socket dropped) — any of which simply ends the
stream so the caller falls back to the post-call view.

Real-time monitoring is an ElevenLabs **Enterprise** capability: the API key needs
``Agents Write`` scope + ``EDITOR`` workspace access, and the conversation must be
active. When that isn't the case the upstream connect fails and the stream ends.
"""

from __future__ import annotations

import json
import logging
from typing import AsyncIterator

import websockets

from ..config import settings
from ..models import ConversationTurn

logger = logging.getLogger(__name__)

# Monitor socket base; {id} is filled per conversation. Same EU residency host the
# rest of the ElevenLabs integration uses, but over wss.
_MONITOR_BASE = "wss://api.eu.residency.elevenlabs.io/v1/convai/conversations"

# Monitor client events that carry transcript text, mapped to a turn role and the
# field(s) the spoken text may live under (flat or nested in a ``*_event`` object).
_TRANSCRIPT_EVENTS: dict[str, tuple[str, tuple[str, ...]]] = {
    "user_transcript": ("user", ("user_transcript",)),
    "agent_response": ("agent", ("agent_response",)),
    "agent_response_correction": ("agent", ("corrected_agent_response", "agent_response")),
}


def monitor_url(conversation_id: str) -> str:
    """The monitor WebSocket URL for one conversation."""
    return f"{_MONITOR_BASE}/{conversation_id}/monitor"


def _text(event: dict, raw: dict, fields: tuple[str, ...]) -> str | None:
    """Pull the first non-empty text field, trying the nested event then the raw body."""
    for source in (event, raw):
        for field in fields:
            value = source.get(field)
            if isinstance(value, str) and value.strip():
                return value
    return None


def parse_monitor_event(raw: object) -> ConversationTurn | None:
    """Map one monitor event to a ConversationTurn, or None if it isn't a turn.

    Tolerant of both the flat (``{"user_transcript": ...}``) and the nested
    (``{"user_transcript_event": {"user_transcript": ...}}``) shapes, since the
    exact framing isn't pinned in the docs. Non-transcript events (audio, ping,
    vad_score, tool calls) and empty-text events return None.
    """
    if not isinstance(raw, dict):
        return None
    mapping = _TRANSCRIPT_EVENTS.get(raw.get("type"))
    if mapping is None:
        return None
    role, fields = mapping
    event = raw.get(f"{raw['type']}_event")
    event = event if isinstance(event, dict) else {}
    message = _text(event, raw, fields)
    if message is None:
        return None
    return ConversationTurn(role=role, message=message)


def format_sse(turn: ConversationTurn) -> str:
    """Frame one turn as a Server-Sent Event (``event: turn``)."""
    payload = json.dumps({"role": turn.role, "message": turn.message})
    return f"event: turn\ndata: {payload}\n\n"


async def stream_turns(conversation_id: str) -> AsyncIterator[ConversationTurn]:
    """Yield transcript turns from the live monitor socket until the call ends.

    The upstream socket is closed automatically when the consumer stops iterating
    (``async with`` — closes on tab disconnect / call end / break), so no upstream
    connection is leaked. Any failure (not configured, connect rejected, drop) just
    ends the iterator.
    """
    if not settings.elevenlabs_api_key:
        return
    headers = {"xi-api-key": settings.elevenlabs_api_key}
    try:
        async with websockets.connect(
            monitor_url(conversation_id), additional_headers=headers
        ) as ws:
            async for message in ws:
                try:
                    raw = json.loads(message)
                except (ValueError, TypeError):
                    continue
                turn = parse_monitor_event(raw)
                if turn is not None:
                    yield turn
    except Exception as exc:  # noqa: BLE001 — a monitor failure must never crash the route
        logger.warning("Live monitor for %s ended: %s", conversation_id, exc)
