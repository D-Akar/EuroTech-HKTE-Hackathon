"""Tests for fetching and parsing ElevenLabs conversation detail.

No real network: the parser is a pure function tested against captured-shape
sample bodies, and the endpoint test monkeypatches the fetch layer.
"""

import asyncio
from datetime import date, datetime, timezone

from app import call_store, conversation_store
from app.models import CallRecord, ConversationDataPoint, ConversationDetail
from app.services import elevenlabs_conversations as elc


def _detail(conversation_id="conv_abc", **points):
    """Build a ready ConversationDetail with the given data_collection values."""
    return ConversationDetail(
        conversation_id=conversation_id,
        status="done",
        ready=True,
        transcript_summary="Summary.",
        call_successful="success",
        started_at=datetime(2026, 6, 5, 9, 0, tzinfo=timezone.utc),
        data_collection=[
            ConversationDataPoint(id=k, value=v) for k, v in points.items()
        ],
    )


# A realistic "done" conversation body, shaped like the ElevenLabs API response.
DONE_BODY = {
    "conversation_id": "conv_abc",
    "status": "done",
    "transcript": [
        {"role": "agent", "message": "Good morning Mary, how are you?", "time_in_call_secs": 0},
        {"role": "user", "message": "A bit tired, my knee hurts.", "time_in_call_secs": 4},
        {"role": "agent", "message": None, "time_in_call_secs": 6},
    ],
    "metadata": {"call_duration_secs": 92, "start_time_unix_secs": 1717660800},
    "analysis": {
        "transcript_summary": "Patient reports tiredness and knee pain.",
        "call_successful": "success",
        "evaluation_criteria_results": {},
        "data_collection_results": {
            "pain_level": {
                "data_collection_id": "pain_level",
                "value": 6,
                "rationale": "Said knee hurts, rated 6.",
            },
            "medication_taken": {
                "data_collection_id": "medication_taken",
                "value": False,
                "rationale": "Said she forgot the morning dose.",
            },
            "mood": {
                "data_collection_id": "mood",
                "value": "tired",
                "rationale": "Described herself as a bit tired.",
            },
        },
    },
}

PROCESSING_BODY = {
    "conversation_id": "conv_pending",
    "status": "processing",
    "transcript": [],
    "metadata": {},
    "analysis": None,
}


def test_parse_done_conversation_core_fields():
    detail = elc.parse_conversation("conv_abc", DONE_BODY)
    assert detail.conversation_id == "conv_abc"
    assert detail.status == "done"
    assert detail.ready is True
    assert detail.transcript_summary == "Patient reports tiredness and knee pain."
    assert detail.call_successful == "success"
    assert detail.call_duration_secs == 92
    assert detail.started_at is not None


def test_parse_done_conversation_transcript():
    detail = elc.parse_conversation("conv_abc", DONE_BODY)
    assert len(detail.transcript) == 3
    assert detail.transcript[0].role == "agent"
    assert detail.transcript[1].message == "A bit tired, my knee hurts."
    assert detail.transcript[2].message is None


def test_parse_done_conversation_data_collection():
    detail = elc.parse_conversation("conv_abc", DONE_BODY)
    by_id = {d.id: d for d in detail.data_collection}
    assert by_id["pain_level"].value == 6
    assert by_id["medication_taken"].value is False
    assert by_id["mood"].value == "tired"
    assert by_id["pain_level"].rationale == "Said knee hurts, rated 6."


def test_parse_data_collection_known_fields_first():
    # Known triage fields render before any unknown extras, in canonical order.
    body = {
        "conversation_id": "c",
        "status": "done",
        "analysis": {
            "data_collection_results": {
                "some_extra": {"value": "x"},
                "mood": {"value": "calm"},
                "pain_level": {"value": 2},
            }
        },
    }
    detail = elc.parse_conversation("c", body)
    ids = [d.id for d in detail.data_collection]
    assert ids.index("mood") < ids.index("pain_level") < ids.index("some_extra")


def test_parse_processing_conversation_not_ready():
    detail = elc.parse_conversation("conv_pending", PROCESSING_BODY)
    assert detail.status == "processing"
    assert detail.ready is False
    assert detail.transcript_summary is None
    assert detail.transcript == []
    assert detail.data_collection == []


# --- Digest rendering --------------------------------------------------------


def test_render_digest_full():
    detail = _detail(
        mood="tired",
        pain_level=6,
        medication_taken=False,
        new_symptoms="dizzy when standing",
        sleep_quality="poor",
        needs_followup=True,
        followup_reason="dizziness on standing",
    )
    text = conversation_store.render_digest(detail, date(2026, 6, 5))
    assert text.startswith("Previous check-in (2026-06-05):")
    assert 'mood "tired"' in text
    assert "pain 6/10" in text
    assert "medication taken: no" in text
    assert "dizzy when standing" in text
    assert "sleep: poor" in text
    assert "flagged for follow-up (dizziness on standing)" in text


def test_render_digest_medication_yes():
    detail = _detail(medication_taken=True)
    assert "medication taken: yes" in conversation_store.render_digest(detail, date(2026, 6, 5))


def test_render_digest_omits_empty_and_none_fields():
    detail = _detail(mood="calm", new_symptoms="none", needs_followup=False)
    text = conversation_store.render_digest(detail, date(2026, 6, 5))
    assert 'mood "calm"' in text
    assert "new symptoms" not in text  # "none" is dropped
    assert "follow-up" not in text  # not flagged


def test_render_digest_falls_back_to_summary_when_no_structured_data():
    detail = ConversationDetail(
        conversation_id="c", status="done", ready=True,
        transcript_summary="Patient was cheerful.",
    )
    text = conversation_store.render_digest(detail, date(2026, 6, 5))
    assert "Patient was cheerful." in text


def test_render_digest_returns_none_when_nothing():
    detail = ConversationDetail(conversation_id="c", status="done", ready=True)
    assert conversation_store.render_digest(detail, date(2026, 6, 5)) is None


# --- Store: caching + latest_digest ------------------------------------------


def test_get_detail_caches_terminal_result(monkeypatch):
    conversation_store._CACHE.clear()
    calls = {"n": 0}

    async def fake_fetch(cid):
        calls["n"] += 1
        return _detail(conversation_id=cid, mood="calm")

    monkeypatch.setattr(elc, "fetch_conversation", fake_fetch)

    first = asyncio.run(conversation_store.get_detail("conv_cache"))
    second = asyncio.run(conversation_store.get_detail("conv_cache"))
    assert first.ready is True
    assert second.ready is True
    assert calls["n"] == 1  # second call served from cache, no refetch


def test_latest_digest_uses_most_recent_call_with_conversation(monkeypatch):
    conversation_store._CACHE.clear()

    async def fake_fetch(cid):
        return _detail(conversation_id=cid, mood="tired", pain_level=7)

    monkeypatch.setattr(elc, "fetch_conversation", fake_fetch)

    pid = 777
    call_store.add_call_record(
        CallRecord(
            id=call_store.next_record_id(),
            patient_id=pid,
            triggered_at=datetime(2026, 6, 5, 9, 0),
            kind="instant",
            to_number="+100",
            status="initiated",
            conversation_id="conv_latest",
        )
    )
    text = asyncio.run(conversation_store.latest_digest(pid))
    assert text is not None
    assert 'mood "tired"' in text
    assert "pain 7/10" in text


def test_latest_digest_none_when_no_conversation(monkeypatch):
    text = asyncio.run(conversation_store.latest_digest(888))
    assert text is None


# --- Endpoint: GET /patients/{id}/calls/{call_id}/conversation ---------------

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

client = TestClient(app)


def _seed_call(patient_id, conversation_id):
    record = CallRecord(
        id=call_store.next_record_id(),
        patient_id=patient_id,
        triggered_at=datetime(2026, 6, 5, 9, 0),
        kind="instant",
        to_number="+100",
        status="initiated",
        conversation_id=conversation_id,
    )
    return call_store.add_call_record(record)


def test_conversation_endpoint_returns_detail(monkeypatch):
    conversation_store._CACHE.clear()
    record = _seed_call(1, "conv_ep_done")

    async def fake_get_detail(cid):
        return _detail(conversation_id=cid, mood="calm", pain_level=2)

    monkeypatch.setattr(conversation_store, "get_detail", fake_get_detail)

    resp = client.get(f"/patients/1/calls/{record.id}/conversation")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ready"] is True
    assert any(d["id"] == "mood" and d["value"] == "calm" for d in body["data_collection"])


def test_conversation_endpoint_processing_passthrough(monkeypatch):
    record = _seed_call(1, "conv_ep_proc")

    async def fake_get_detail(cid):
        return ConversationDetail(conversation_id=cid, status="processing", ready=False)

    monkeypatch.setattr(conversation_store, "get_detail", fake_get_detail)

    resp = client.get(f"/patients/1/calls/{record.id}/conversation")
    assert resp.status_code == 200
    assert resp.json()["ready"] is False
    assert resp.json()["status"] == "processing"


def test_conversation_endpoint_404_when_call_has_no_conversation():
    record = call_store.add_call_record(
        CallRecord(
            id=call_store.next_record_id(),
            patient_id=1,
            triggered_at=datetime(2026, 6, 5, 9, 0),
            kind="instant",
            to_number="+100",
            status="failed",
        )
    )
    assert client.get(f"/patients/1/calls/{record.id}/conversation").status_code == 404


def test_conversation_endpoint_404_unknown_call():
    assert client.get("/patients/1/calls/99999999/conversation").status_code == 404


def test_conversation_endpoint_404_unknown_patient():
    assert client.get("/patients/999/calls/1/conversation").status_code == 404
