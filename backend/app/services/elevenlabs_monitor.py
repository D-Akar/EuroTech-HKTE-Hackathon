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

# Monitor client events that carry transcript text, mapped to (turn role, the
# ``*_event`` wrapper key ElevenLabs nests the text under, the field name(s) the
# text may live under). The wrapper key is asymmetric and does NOT always equal
# ``{type}_event``: user speech arrives under ``user_transcription_event`` (note:
# transcription, not transcript) while agent text uses ``agent_response_event``.
_TRANSCRIPT_EVENTS: dict[str, tuple[str, str, tuple[str, ...]]] = {
    "user_transcript": ("user", "user_transcription_event", ("user_transcript",)),
    "agent_response": ("agent", "agent_response_event", ("agent_response",)),
    "agent_response_correction": (
        "agent",
        "agent_response_correction_event",
        ("corrected_agent_response", "agent_response"),
    ),
}


def monitor_url(conversation_id: str) -> str:
    """The monitor WebSocket URL for one conversation."""
    return f"{_MONITOR_BASE}/{conversation_id}/monitor"


def _first_text(sources: tuple[dict, ...], fields: tuple[str, ...]) -> str | None:
    """Pull the first non-empty string under any of ``fields`` across ``sources``."""
    for source in sources:
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
    role, wrapper_key, fields = mapping
    # Look in the known wrapper, the type-derived ``{type}_event`` name (tolerant of
    # shapes whose wrapper does match the type), then the flat body — first hit wins.
    sources = [
        raw[key]
        for key in (wrapper_key, f"{raw['type']}_event")
        if isinstance(raw.get(key), dict)
    ]
    sources.append(raw)
    message = _first_text(tuple(sources), fields)
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
        logger.warning("Live monitor for %s skipped: ELEVENLABS_API_KEY not set", conversation_id)
        return
    headers = {"xi-api-key": settings.elevenlabs_api_key}
    url = monitor_url(conversation_id)
    turns = 0
    try:
        logger.info("Live monitor connecting: %s", url)
        async with websockets.connect(url, additional_headers=headers) as ws:
            logger.info("Live monitor connected: %s", conversation_id)
            async for message in ws:
                try:
                    raw = json.loads(message)
                except (ValueError, TypeError):
                    continue
                turn = parse_monitor_event(raw)
                if turn is not None:
                    turns += 1
                    yield turn
        # Reached only when the upstream closes cleanly (call ended). A 0-turn clean
        # close usually means the conversation wasn't active to monitor (e.g. still
        # ringing / already over), distinct from a connect rejection below.
        logger.info("Live monitor for %s closed by server after %d turn(s)", conversation_id, turns)
    except Exception as exc:  # noqa: BLE001 — a monitor failure must never crash the route
        logger.warning(
            "Live monitor for %s ended (%s) after %d turn(s): %s",
            conversation_id, type(exc).__name__, turns, exc,
        )
