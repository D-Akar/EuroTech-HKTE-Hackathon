# Live call transcript - design

**Date:** 2026-06-07
**Status:** approved, implementing

## Goal

Let a practice watch a check-in call's transcript stream in **real time** on the
dashboard, as the patient and agent speak - not just review it after the call ends.

## Chosen approach

ElevenLabs exposes a **real-time monitoring WebSocket** per conversation:
`wss://api.elevenlabs.io/v1/convai/conversations/{id}/monitor`. It streams text
events (transcripts, agent responses, corrections - no audio) for an **active**
conversation. This is an **Enterprise-tier** capability and the API key needs
`Agents Write` scope + `EDITOR` workspace access.

The browser cannot connect to that socket directly (it would leak `xi-api-key`
and won't pass auth/CORS), so the **backend proxies**:

```
Browser ──EventSource(SSE)──▶ FastAPI ──WebSocket client──▶ wss://…/conversations/{id}/monitor
        ◀── turn events ─────         ◀── user_transcript / agent_response ──
```

- **Downstream (browser ⇄ backend): SSE.** "Watch only" is one-directional, so
  SSE is the right fit - `EventSource` reconnects on its own, no extra frontend
  library. Mirrors the existing `/events` endpoint pattern.
- **Upstream (backend ⇄ ElevenLabs): WebSocket client** via the `websockets`
  package (already present transitively through `uvicorn[standard]`; pinned
  explicitly in `requirements.txt`).

## Events we care about

The monitor stream emits ElevenLabs client events. Only three map to transcript turns:

| Event type | Speaker | Text field |
|---|---|---|
| `user_transcript` | patient | `user_transcript` (or nested `user_transcript_event.user_transcript`) |
| `agent_response` | agent | `agent_response` (or nested `agent_response_event.agent_response`) |
| `agent_response_correction` | agent | corrected text (nested or flat) |

Everything else (`audio`, `ping`, `vad_score`, tool calls, metadata) is ignored.
The exact nesting isn't fully pinned in the docs, so the parser is **tolerant of
both flat and `*_event`-wrapped shapes** and is unit-tested against both.

## Backend

### `app/services/elevenlabs_monitor.py` (new)
- `parse_monitor_event(raw: dict) -> ConversationTurn | None` - **pure, no I/O**,
  unit-tested against captured-shape sample bodies. Maps the three transcript
  events to a `ConversationTurn` (reusing the existing model); returns `None` for
  everything else and for empty/missing text.
- `format_sse(turn: ConversationTurn) -> str` - **pure**, returns one SSE frame:
  `event: turn\ndata: {"role":...,"message":...}\n\n`. Unit-tested.
- `monitor_url(conversation_id) -> str` - **pure** URL builder.
- `stream_turns(conversation_id) -> AsyncIterator[ConversationTurn]` - opens the
  upstream WS (`xi-api-key` header), parses each frame, yields turns. The thin,
  I/O seam. **Cleanup guaranteed**: `async with websockets.connect(...)` closes
  the upstream socket when the consumer stops iterating (tab closed / call ended)
  - this is the leak-prevention requirement. Tolerant: not-configured or
  connect-rejected → the stream simply ends (caller falls back to post-call view).

### Route: `GET /patients/{patient_id}/calls/{call_id}/live`
On the existing calls router. Returns `text/event-stream`. Reuses the
`_require_patient` / call-lookup / 404 patterns from `get_call_conversation`,
then streams: `event: ready` immediately, one `event: turn` per parsed turn, and
a terminal `event: end` when the upstream closes. Breaks out on
`request.is_disconnected()` (mirrors `/events`). `stream_turns` is a
module-level reference so tests can monkeypatch it with a fake async iterator.

## Frontend

### `LiveCallTranscript.tsx` (new)
Opens `EventSource` to the live URL, appends a turn on each `turn` event, renders
with the **same `conv-turn*` styling** as `CallConversation` for visual
consistency. On `end` it closes the stream and notifies the parent (so the row
can flip to the archived post-call view).

### `api.liveCallUrl(patientId, callId)` (new)
Returns the URL string (mirrors `eventsUrl()`), consumed via `new EventSource(...)`.

### Wire into `CallPanel` "Recent calls"
A call is treated as **potentially live** only when `status === "initiated"` **and**
it was triggered recently (within ~15 min - avoids opening a socket for stale
records). Expanding such a row shows `LiveCallTranscript`; when its stream ends,
or for any other call, the row shows the existing `CallConversation`. No new UI
region - live-then-archived in the same expander.

## Error handling / fallback

Every failure mode degrades to the existing post-call view: no Enterprise access,
WS rejected, telephony unconfigured, or call already ended → the live stream just
ends. No new path can crash an existing route (best-effort, like the rest of the
codebase).

## Testing

Backend (pytest - the repo's test layer):
- `parse_monitor_event` against `user_transcript` / `agent_response` /
  `agent_response_correction` in **both flat and wrapped shapes**, plus ignored
  events (`audio`, `ping`) and empty-text → `None`.
- `format_sse` framing.
- The `/live` route with a monkeypatched `stream_turns` yielding a finite fake
  sequence: asserts `ready` → `turn`(s) → `end` framing, and the 404s (unknown
  patient / unknown call / call with no conversation).
- The real WS `connect` stays the single thin, untested seam.

Frontend has no test runner; `LiveCallTranscript` follows the existing untested
`CallConversation` component pattern.

## Known caveats

- **Enterprise gate** - without `Agents Write` + `EDITOR`, the socket is rejected
  and it silently falls back to post-call. Verify the plan/key early.
- **Marginal ElevenLabs cost ≈ $0** - billing is per call-minute (~$0.08-0.12/min
  + LLM passthrough) on connection duration; monitoring is observing a call you
  already pay for, with no documented separate fee. Confirm at scale.
- **Resource leak on disconnect** is the key correctness risk - handled by the
  `async with` upstream socket; covered as a must-pass behaviour.
- **Reconnect loop** - `EventSource` auto-reconnects; the terminal `event: end` +
  frontend `.close()` + the "recent calls only" rule prevent a storm.
- **Event ordering** - ElevenLabs warns monitor events can arrive out of order;
  rendered in arrival order, acceptable for a check-in's pace.
- **Privacy/auth** - this streams live PHI over an endpoint with no auth yet (same
  gap as the post-call view, higher sensitivity). Acceptable for the demo; must
  sit behind auth before production.
