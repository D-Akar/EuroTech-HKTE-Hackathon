"""In-memory cache of fetched ElevenLabs conversation detail, plus the prior-call
digest fed into the next outbound call's context.

Behind a small functional interface (mirrors ``call_store`` / ``care_plan_store``)
so a post-call webhook writer (``prime``) or a MongoDB backing can be added later
without touching readers. Resets on restart.
"""

from __future__ import annotations

from datetime import date

from . import call_store
from .models import ConversationDetail
from .services import elevenlabs_conversations as _conversations

# conversation_id -> ConversationDetail (only terminal results are kept)
_CACHE: dict[str, ConversationDetail] = {}

_TERMINAL = {"done", "failed"}


def prime(detail: ConversationDetail) -> None:
    """Populate the cache directly (e.g. from a future post-call webhook)."""
    if detail.status in _TERMINAL:
        _CACHE[detail.conversation_id] = detail


async def get_detail(conversation_id: str) -> ConversationDetail | None:
    """Return conversation detail, fetching from ElevenLabs on a cache miss.

    Terminal results (done/failed) are cached; an in-flight conversation is
    re-fetched each call until it finishes.
    """
    cached = _CACHE.get(conversation_id)
    if cached is not None:
        return cached
    detail = await _conversations.fetch_conversation(conversation_id)
    if detail is not None and detail.status in _TERMINAL:
        _CACHE[conversation_id] = detail
    return detail


async def latest_digest(patient_id: int) -> str | None:
    """One-line digest of the patient's most recent completed call, or None."""
    for record in call_store.list_call_records(patient_id):  # most-recent first
        if not record.conversation_id:
            continue
        detail = await get_detail(record.conversation_id)
        if detail is None or not detail.ready:
            return None  # newest call not ready yet — don't skip to an older one
        when = (detail.started_at.date() if detail.started_at
                else record.triggered_at.date())
        return render_digest(detail, when)
    return None


def _values(detail: ConversationDetail) -> dict[str, object]:
    return {p.id: p.value for p in detail.data_collection}


def render_digest(detail: ConversationDetail, when: date) -> str | None:
    """Render a compact prior-call summary line for the agent's context."""
    v = _values(detail)
    parts: list[str] = []

    mood = v.get("mood")
    if isinstance(mood, str) and mood.strip():
        parts.append(f'mood "{mood.strip()}"')

    pain = v.get("pain_level")
    if isinstance(pain, (int, float)) and not isinstance(pain, bool):
        parts.append(f"pain {int(pain)}/10")

    med = v.get("medication_taken")
    if isinstance(med, bool):
        parts.append(f"medication taken: {'yes' if med else 'no'}")

    symptoms = v.get("new_symptoms")
    if isinstance(symptoms, str) and symptoms.strip() and symptoms.strip().lower() != "none":
        parts.append(f'new symptoms "{symptoms.strip()}"')

    sleep = v.get("sleep_quality")
    if isinstance(sleep, str) and sleep.strip():
        parts.append(f"sleep: {sleep.strip()}")

    if v.get("needs_followup") is True:
        reason = v.get("followup_reason")
        if isinstance(reason, str) and reason.strip():
            parts.append(f"flagged for follow-up ({reason.strip()})")
        else:
            parts.append("flagged for follow-up")

    if parts:
        return f"Previous check-in ({when.isoformat()}): " + "; ".join(parts) + "."
    if detail.transcript_summary:
        return f"Previous check-in ({when.isoformat()}): {detail.transcript_summary}"
    return None
