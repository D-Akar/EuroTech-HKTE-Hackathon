"""A completed AI call materializes into a persisted check-in entry.

Persistence is patched off (``_collection`` -> None) so these run offline and
fast, and never touch a real Mongo. The materialization logic itself is exercised
end-to-end via conversation_store's terminal-result choke point.
"""

import asyncio
from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from app import call_store, checkin_store, conversation_store
from app.main import app
from app.models import CallRecord, ConversationDataPoint, ConversationDetail

client = TestClient(app)


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    # Keep tests offline/fast and isolated from a real Mongo.
    monkeypatch.setattr(checkin_store, "_collection", lambda: None)
    checkin_store._STORE.clear()
    conversation_store._CACHE.clear()
    yield
    checkin_store._STORE.clear()
    conversation_store._CACHE.clear()


def _done_detail(conversation_id: str) -> ConversationDetail:
    return ConversationDetail(
        conversation_id=conversation_id,
        status="done",
        ready=True,
        transcript_summary="Patient is doing well, mild knee pain.",
        call_successful="success",
        started_at=datetime(2026, 6, 6, 9, 0, 0),
        transcript=[],
        data_collection=[
            ConversationDataPoint(id="mood", value="cheerful"),
            ConversationDataPoint(id="pain_level", value=3),
            ConversationDataPoint(id="needs_followup", value=False),
        ],
    )


def _seed_call(patient_id: int, conversation_id: str, call_id: int) -> CallRecord:
    record = CallRecord(
        id=call_id,
        patient_id=patient_id,
        triggered_at=datetime(2026, 6, 6, 9, 0, 0),
        kind="instant",
        to_number="+85291234567",
        status="initiated",
        conversation_id=conversation_id,
    )
    call_store.CALL_HISTORY.insert(0, record)
    return record


def test_completed_call_becomes_checkin(monkeypatch):
    _seed_call(patient_id=1, conversation_id="conv_a", call_id=990001)

    async def fake_fetch(cid):
        return _done_detail("conv_a")

    monkeypatch.setattr(conversation_store._conversations, "fetch_conversation", fake_fetch)

    detail = asyncio.run(conversation_store.get_detail("conv_a"))
    assert detail is not None and detail.ready

    derived = checkin_store.list_for_patient(1)
    assert len(derived) == 1
    c = derived[0]
    assert c.mood == "cheerful"
    assert c.pain_level == 3
    assert c.answered is True
    assert "knee pain" in c.notes
    assert c.id >= 1_000_000  # above the mock id space


def test_materialization_is_idempotent():
    _seed_call(patient_id=2, conversation_id="conv_b", call_id=990002)

    conversation_store._materialize_checkin(_done_detail("conv_b"))
    first = checkin_store.list_for_patient(2)
    assert len(first) == 1

    # Re-processing the same conversation updates the same entry, not a new one.
    conversation_store._materialize_checkin(_done_detail("conv_b"))
    second = checkin_store.list_for_patient(2)
    assert len(second) == 1
    assert second[0].id == first[0].id


def test_checkins_endpoint_merges_derived():
    _seed_call(patient_id=3, conversation_id="conv_c", call_id=990003)
    conversation_store._materialize_checkin(_done_detail("conv_c"))

    resp = client.get("/patients/3/checkins")
    assert resp.status_code == 200
    rows = resp.json()
    assert any(r["mood"] == "cheerful" and r["pain_level"] == 3 for r in rows)
    assert len(rows) > 1  # derived entry sits alongside the mock history


def test_failed_call_does_not_create_checkin():
    _seed_call(patient_id=4, conversation_id="conv_failed", call_id=990004)
    conversation_store._remember(
        ConversationDetail(conversation_id="conv_failed", status="failed", ready=False)
    )
    assert checkin_store.list_for_patient(4) == []


def test_call_without_owning_record_is_skipped():
    # No seeded call record for this conversation -> nothing to attribute it to.
    conversation_store._materialize_checkin(_done_detail("conv_orphan"))
    assert all(c.patient_id != 0 for c in checkin_store._STORE.values())
    assert "conv_orphan" not in checkin_store._STORE
