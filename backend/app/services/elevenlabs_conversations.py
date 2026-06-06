"""Fetch and parse post-call conversation detail from the ElevenLabs API.

`parse_conversation` is a pure function (no I/O) so it can be tested against
captured response bodies. `fetch_conversation` wraps it with the HTTP call and
is tolerant of every failure mode: not-configured, HTTP errors, and conversations
that ElevenLabs has not finished processing yet.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import httpx

from ..config import settings
from ..models import (
    ConversationDataPoint,
    ConversationDetail,
    ConversationEvalResult,
    ConversationTurn,
)

logger = logging.getLogger(__name__)

# Canonical order for the triage fields configured on the outbound agent. Known
# fields render before any unexpected extras so the dashboard layout is stable.
KNOWN_DATA_FIELDS: tuple[str, ...] = (
    "mood",
    "pain_level",
    "medication_taken",
    "new_symptoms",
    "sleep_quality",
    "needs_followup",
    "followup_reason",
)


def _data_points(results: dict) -> list[ConversationDataPoint]:
    if not isinstance(results, dict):
        return []
    known = [k for k in KNOWN_DATA_FIELDS if k in results]
    extras = sorted(k for k in results if k not in KNOWN_DATA_FIELDS)
    points: list[ConversationDataPoint] = []
    for key in [*known, *extras]:
        entry = results.get(key) or {}
        points.append(
            ConversationDataPoint(
                id=key,
                value=entry.get("value") if isinstance(entry, dict) else entry,
                rationale=entry.get("rationale") if isinstance(entry, dict) else None,
            )
        )
    return points


def _eval_results(results: dict) -> list[ConversationEvalResult]:
    """Parse ``evaluation_criteria_results`` (a dict keyed by criteria id).

    Each entry is ``{criteria_id, result: success|failure|unknown, rationale}``.
    Unknown ``result`` values are coerced to ``"unknown"`` so a schema drift never
    breaks the read path.
    """
    if not isinstance(results, dict):
        return []
    out: list[ConversationEvalResult] = []
    for key in sorted(results):
        entry = results.get(key) or {}
        if not isinstance(entry, dict):
            continue
        result = entry.get("result")
        if result not in ("success", "failure", "unknown"):
            result = "unknown"
        out.append(
            ConversationEvalResult(
                id=entry.get("criteria_id") or key,
                result=result,
                rationale=entry.get("rationale"),
            )
        )
    return out


def _turns(transcript) -> list[ConversationTurn]:
    out: list[ConversationTurn] = []
    for t in transcript or []:
        if not isinstance(t, dict):
            continue
        role = t.get("role")
        if role not in ("user", "agent"):
            continue
        out.append(
            ConversationTurn(
                role=role,
                message=t.get("message"),
                time_in_call_secs=t.get("time_in_call_secs"),
            )
        )
    return out


def parse_conversation(conversation_id: str, body: dict) -> ConversationDetail:
    """Build a ConversationDetail from an ElevenLabs conversation response body."""
    status = body.get("status") or "unknown"
    analysis = body.get("analysis") or {}
    metadata = body.get("metadata") or {}

    started_at = None
    start_unix = metadata.get("start_time_unix_secs")
    if isinstance(start_unix, (int, float)):
        started_at = datetime.fromtimestamp(start_unix, tz=timezone.utc)

    return ConversationDetail(
        conversation_id=conversation_id,
        status=status,
        ready=status == "done",
        transcript_summary=analysis.get("transcript_summary"),
        call_successful=analysis.get("call_successful"),
        call_duration_secs=metadata.get("call_duration_secs"),
        started_at=started_at,
        transcript=_turns(body.get("transcript")),
        data_collection=_data_points(analysis.get("data_collection_results")),
        evaluation_criteria=_eval_results(analysis.get("evaluation_criteria_results")),
    )


async def fetch_conversation(conversation_id: str) -> ConversationDetail | None:
    """Pull one conversation from ElevenLabs. Returns None if not retrievable.

    None means "no data available" (telephony not configured, or an error) - the
    caller treats that as "nothing to show / nothing to add to context". A valid
    but unfinished conversation comes back with ``ready=False``.
    """
    if not settings.elevenlabs_api_key:
        return None

    url = f"{settings.elevenlabs_conversations_url}/{conversation_id}"
    headers = {"xi-api-key": settings.elevenlabs_api_key}
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.get(url, headers=headers)
        resp.raise_for_status()
        return parse_conversation(conversation_id, resp.json())
    except Exception as exc:  # noqa: BLE001 - never let a fetch failure crash a route
        logger.warning("Failed to fetch conversation %s: %s", conversation_id, exc)
        return None
