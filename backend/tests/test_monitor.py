"""Tests for the live-call monitor: event parsing + SSE framing + the /live route.

No real network. ``parse_monitor_event`` and ``format_sse`` are pure and tested
against captured-shape event bodies; the route test monkeypatches ``stream_turns``
with a finite fake async iterator, so the real WebSocket connect is the only
untested seam.
"""

import json
from datetime import datetime, timedelta

from app.models import ConversationTurn
from app.services import elevenlabs_monitor as mon


# --- parse_monitor_event: transcript turns -----------------------------------


def test_parse_user_transcript_wrapped():
    turn = mon.parse_monitor_event(
        {"type": "user_transcript", "user_transcript_event": {"user_transcript": "My knee hurts."}}
    )
    assert turn == ConversationTurn(role="user", message="My knee hurts.")


def test_parse_user_transcript_flat():
    turn = mon.parse_monitor_event({"type": "user_transcript", "user_transcript": "Hello."})
    assert turn == ConversationTurn(role="user", message="Hello.")


def test_parse_user_transcript_real_elevenlabs_wrapper():
    # The shape ElevenLabs actually sends: the `user_transcript` event nests its text
    # under `user_transcription_event` (transcription, not transcript) — asymmetric
    # with `agent_response`/`agent_response_event`. Regression for patient turns that
    # silently dropped while agent turns came through.
    turn = mon.parse_monitor_event(
        {"type": "user_transcript", "user_transcription_event": {"user_transcript": "My head hurts."}}
    )
    assert turn == ConversationTurn(role="user", message="My head hurts.")


def test_parse_agent_response_wrapped():
    turn = mon.parse_monitor_event(
        {"type": "agent_response", "agent_response_event": {"agent_response": "Good morning Mary."}}
    )
    assert turn == ConversationTurn(role="agent", message="Good morning Mary.")


def test_parse_agent_response_flat():
    turn = mon.parse_monitor_event({"type": "agent_response", "agent_response": "How are you?"})
    assert turn == ConversationTurn(role="agent", message="How are you?")


def test_parse_agent_response_correction_is_agent_turn():
    turn = mon.parse_monitor_event(
        {
            "type": "agent_response_correction",
            "agent_response_correction_event": {"corrected_agent_response": "Sorry, go on."},
        }
    )
    assert turn is not None
    assert turn.role == "agent"
    assert turn.message == "Sorry, go on."


# --- parse_monitor_event: mood / audio-tag stripping -------------------------


def test_parse_strips_leading_audio_tag_from_agent():
    turn = mon.parse_monitor_event(
        {"type": "agent_response", "agent_response_event": {"agent_response": "[concerned] I am sorry to hear that."}}
    )
    assert turn == ConversationTurn(role="agent", message="I am sorry to hear that.")


def test_parse_strips_inline_and_multiple_audio_tags():
    turn = mon.parse_monitor_event(
        {"type": "agent_response", "agent_response": "[slow] Wonderful, Devon. [happy] Glad we connected."}
    )
    assert turn == ConversationTurn(role="agent", message="Wonderful, Devon. Glad we connected.")


def test_parse_keeps_non_tag_brackets():
    # A bracketed value that isn't an audio tag (digits/slash) must survive.
    turn = mon.parse_monitor_event(
        {"type": "agent_response", "agent_response": "Your pain is [2/10] today."}
    )
    assert turn == ConversationTurn(role="agent", message="Your pain is [2/10] today.")


def test_parse_agent_message_that_is_only_a_tag_is_dropped():
    assert mon.parse_monitor_event({"type": "agent_response", "agent_response": "[laughs]"}) is None


# --- parse_monitor_event: tool calls -----------------------------------------


def test_parse_client_tool_call_becomes_tool_turn():
    turn = mon.parse_monitor_event(
        {
            "type": "client_tool_call",
            "client_tool_call": {
                "tool_name": "escalate_emergency",
                "tool_call_id": "tc_1",
                "parameters": {"patient_id": "20", "reason": "Severe persistent headache."},
            },
        }
    )
    assert turn is not None
    assert turn.role == "tool"
    assert turn.tool_name == "escalate_emergency"
    # The patient-facing reason is the useful detail; the id is noise.
    assert turn.message == "Severe persistent headache."


def test_parse_client_tool_call_without_reason_has_no_message():
    turn = mon.parse_monitor_event(
        {"type": "client_tool_call", "client_tool_call": {"tool_name": "lookup", "parameters": {}}}
    )
    assert turn is not None
    assert turn.role == "tool"
    assert turn.tool_name == "lookup"
    assert turn.message is None


def test_parse_tool_call_missing_name_is_ignored():
    assert mon.parse_monitor_event({"type": "client_tool_call", "client_tool_call": {}}) is None


def test_parse_agent_tool_response_becomes_tool_turn():
    # Server/webhook tools (our `escalate_emergency` is `"type": "webhook"`) never
    # emit `client_tool_call`; ElevenLabs reports them as `agent_tool_response`.
    # Regression for webhook tool calls that silently never reached the live UI.
    turn = mon.parse_monitor_event(
        {
            "type": "agent_tool_response",
            "agent_tool_response": {
                "tool_name": "escalate_emergency",
                "tool_call_id": "tc_9",
                "tool_type": "webhook",
                "is_error": False,
            },
        }
    )
    assert turn is not None
    assert turn.role == "tool"
    assert turn.tool_name == "escalate_emergency"


def test_parse_agent_tool_response_with_detail():
    # When the response event does echo the call detail, surface it as the message.
    turn = mon.parse_monitor_event(
        {
            "type": "agent_tool_response",
            "agent_tool_response": {
                "tool_name": "escalate_emergency",
                "parameters": {"reason": "Sudden chest pain."},
            },
        }
    )
    assert turn == ConversationTurn(
        role="tool", tool_name="escalate_emergency", message="Sudden chest pain."
    )


def test_parse_agent_tool_response_missing_name_is_ignored():
    assert (
        mon.parse_monitor_event(
            {"type": "agent_tool_response", "agent_tool_response": {"is_error": True}}
        )
        is None
    )


# --- parse_monitor_event: events we ignore -----------------------------------


def test_parse_ignores_audio_event():
    assert mon.parse_monitor_event({"type": "audio", "audio_event": {"audio_base_64": "..."}}) is None


def test_parse_ignores_ping_event():
    assert mon.parse_monitor_event({"type": "ping", "ping_event": {"event_id": 1}}) is None


def test_parse_ignores_unknown_event():
    assert mon.parse_monitor_event({"type": "vad_score", "vad_score_event": {"vad_score": 0.9}}) is None


def test_parse_empty_text_returns_none():
    # A transcript event with no usable text is not a turn worth emitting.
    assert mon.parse_monitor_event({"type": "user_transcript", "user_transcript": ""}) is None
    assert mon.parse_monitor_event({"type": "agent_response", "agent_response": None}) is None


def test_parse_non_dict_returns_none():
    assert mon.parse_monitor_event("not a dict") is None
    assert mon.parse_monitor_event({}) is None


# --- format_sse --------------------------------------------------------------


def test_format_sse_frames_a_turn():
    frame = mon.format_sse(ConversationTurn(role="user", message="Hi there."))
    assert frame.startswith("event: turn\n")
    assert frame.endswith("\n\n")
    # The data line carries JSON with role + message.
    data_line = next(l for l in frame.splitlines() if l.startswith("data: "))
    payload = json.loads(data_line[len("data: "):])
    assert payload == {"role": "user", "message": "Hi there."}


def test_format_sse_carries_tool_name():
    frame = mon.format_sse(ConversationTurn(role="tool", tool_name="escalate_emergency", message="Severe headache."))
    data_line = next(l for l in frame.splitlines() if l.startswith("data: "))
    payload = json.loads(data_line[len("data: "):])
    assert payload == {"role": "tool", "message": "Severe headache.", "tool_name": "escalate_emergency"}


# --- /live route -------------------------------------------------------------

from fastapi.testclient import TestClient  # noqa: E402

from app import call_store  # noqa: E402
from app.main import app  # noqa: E402
from app.models import CallRecord  # noqa: E402

client = TestClient(app)


def _seed_call(patient_id, conversation_id, triggered_at=None, status="initiated"):
    record = CallRecord(
        id=call_store.next_record_id(),
        patient_id=patient_id,
        triggered_at=triggered_at or datetime.now(),
        kind="instant",
        to_number="+100",
        status=status,
        conversation_id=conversation_id,
    )
    return call_store.add_call_record(record)


def test_live_route_streams_turns_then_end(monkeypatch):
    record = _seed_call(1, "conv_live")

    async def fake_stream(conversation_id):
        assert conversation_id == "conv_live"
        yield ConversationTurn(role="agent", message="Hello Mary.")
        yield ConversationTurn(role="user", message="Hi doctor.")

    monkeypatch.setattr(mon, "stream_turns", fake_stream)

    resp = client.get("/patients/1/calls/%d/live" % record.id)
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/event-stream")
    body = resp.text
    assert "event: ready" in body
    assert "Hello Mary." in body
    assert "Hi doctor." in body
    assert "event: turn" in body
    assert "event: end" in body


def test_live_route_404_when_call_has_no_conversation():
    record = call_store.add_call_record(
        CallRecord(
            id=call_store.next_record_id(),
            patient_id=1,
            triggered_at=datetime.now(),
            kind="instant",
            to_number="+100",
            status="failed",
        )
    )
    assert client.get("/patients/1/calls/%d/live" % record.id).status_code == 404


def test_live_route_404_unknown_call():
    assert client.get("/patients/1/calls/99999999/live").status_code == 404


def test_live_route_404_unknown_patient():
    assert client.get("/patients/999/calls/1/live").status_code == 404


# --- stream_turns against a real local WebSocket server ----------------------
#
# Exercises the actual network seam (real websockets.connect, real JSON frames,
# real async iteration + clean close) without ElevenLabs. This is the pattern for
# testing the WS layer: stand up a scripted local ws server and point the URL
# builder at it. It also guards the `additional_headers` kwarg — the wrong name
# would raise here, not just in production.

import asyncio  # noqa: E402

import websockets  # noqa: E402

from app.config import settings  # noqa: E402


def test_stream_turns_parses_live_server_frames(monkeypatch):
    frames = [
        json.dumps({"type": "agent_response", "agent_response_event": {"agent_response": "Hello Mary."}}),
        json.dumps({"type": "user_transcript", "user_transcription_event": {"user_transcript": "Hi doctor."}}),
        json.dumps({"type": "audio", "audio_event": {"audio_base_64": "..."}}),  # ignored
        json.dumps({"type": "ping", "ping_event": {"event_id": 1}}),  # ignored
    ]

    async def run():
        async def handler(ws):
            # The client must send the api key header; assert it actually arrived.
            assert ws.request.headers.get("xi-api-key") == "test-key"
            for frame in frames:
                await ws.send(frame)
            await ws.close()  # call "ends" -> stream_turns should finish cleanly

        async with websockets.serve(handler, "localhost", 0) as server:
            port = server.sockets[0].getsockname()[1]
            monkeypatch.setattr(settings, "elevenlabs_api_key", "test-key")
            monkeypatch.setattr(
                mon, "monitor_url", lambda cid: f"ws://localhost:{port}/{cid}/monitor"
            )
            return [t async for t in mon.stream_turns("conv_x")]

    turns = asyncio.run(run())
    assert [(t.role, t.message) for t in turns] == [
        ("agent", "Hello Mary."),
        ("user", "Hi doctor."),
    ]


def test_stream_turns_yields_nothing_when_not_configured(monkeypatch):
    monkeypatch.setattr(settings, "elevenlabs_api_key", "")
    turns = asyncio.run(_collect(mon.stream_turns("conv_x")))
    assert turns == []


async def _collect(aiter):
    return [x async for x in aiter]
