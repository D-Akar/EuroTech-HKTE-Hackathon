# Outbound Call Conversation Data — Design

**Date:** 2026-06-06
**Status:** Approved (design)

## Goal

After an outbound AI check-in call ends, let a care coordinator **see what happened
in that conversation** from the dashboard: ElevenLabs' transcript and auto-summary,
plus the structured triage values extracted from the call (mood, pain, medication
adherence, new symptoms, sleep, and a follow-up flag).

Secondarily, make the **most recent call's outcome available as context for the next
outbound call**, so the agent can acknowledge what the patient said last time instead
of starting cold.

## Background — current state

- Outbound calls (`services/telephony.py`) place the call via the ElevenLabs Twilio
  endpoint and store a `CallRecord` carrying `conversation_id` and `call_sid`
  (`models.py`), but **nothing ever fetches the conversation back**. The record is
  fire-and-forget.
- The backend already holds `ELEVENLABS_API_KEY` and uses the EU residency base
  (`https://api.eu.residency.elevenlabs.io`) for the outbound call.
- The frontend `CallPanel` "Recent calls" list shows only timestamp / kind / status.

## ElevenLabs API (verified against docs)

`GET /v1/convai/conversations/{conversation_id}` (residency base, `xi-api-key` header)
returns:

- `status`: `initiated` | `in-progress` | `processing` | `done` | `failed`
- `transcript[]`: `{ role: "user"|"agent", message: string|null, time_in_call_secs: int }`
- `metadata`: `{ call_duration_secs: int, start_time_unix_secs: int }`
- `analysis`:
  - `transcript_summary`: string (free, no agent config)
  - `call_successful`: `success` | `failure` | `unknown` (free)
  - `evaluation_criteria_results`: object (unused for now)
  - `data_collection_results`: `{ <identifier>: { value, rationale, data_collection_id } }`

`data_collection_results` keys only exist for fields configured on the agent (Analysis
tab → Data collection). The agent has been configured with the seven identifiers below.

## Data-collection fields (configured on the outbound agent)

| Identifier | Type | Extraction instruction |
|---|---|---|
| `mood` | String | Patient's overall mood in one or two words. Empty if not discussed. |
| `pain_level` | Integer | Pain rating 0–10 the patient reports. Unset if none given. |
| `medication_taken` | Boolean | True if patient confirmed taking prescribed medication as scheduled; false if missed/skipped. |
| `new_symptoms` | String | Any new or worsening symptoms mentioned. "none" if nothing new. |
| `sleep_quality` | String | Brief description of how they slept. |
| `needs_followup` | Boolean | True if the patient should get a human callback / clinical attention. |
| `followup_reason` | String | One short sentence on why follow-up is needed. Empty if false. |

The backend treats these identifiers as the known set for the structured display and the
prior-call digest. Any additional/unknown fields returned are still passed through to the
display generically; only these drive the digest and the highlighted follow-up flag.

## Scope decisions (from brainstorming)

- **Retrieval:** pull-on-demand from ElevenLabs, with an in-memory cache. **No webhook**
  now; the store interface is shaped so a post-call webhook writer can populate it later
  with zero changes to readers.
- **In scope:** fetch layer, cache/store, a `GET .../conversation` endpoint, frontend
  display, and folding the **last call's digest into the next outbound call's context**.
- **Out of scope (marked follow-on):** feeding the same digest into the inbound
  `get_patient_context` tool. The `latest_digest()` helper is built so this is a one-line
  addition later.
- **Persistence:** in-memory, consistent with `call_store` / `care_plan_store` (resets on
  restart). MongoDB is the same future swap discussed for care plans; out of scope here.
- **Audio:** not fetched. Transcript + summary + structured data only.

## Architecture

New/changed backend modules are small and single-purpose, mirroring existing patterns
(`call_store.py`, `services/telephony.py`, `services/patient_context.py`).

### Data flow

```
Call ends at ElevenLabs
        │
Dashboard opens a call row ──► GET /patients/{id}/calls/{call_id}/conversation
        │                              │
        │                       conversation_store.get_detail(conversation_id)
        │                              │  (cache miss / non-terminal)
        │                              ▼
        │                       elevenlabs_conversations.fetch_conversation(id)
        │                              │  GET /v1/convai/conversations/{id}
        │                              ▼
        │                       parse → ConversationDetail ──► cache if status==done
        ▼
   render summary + structured chips + transcript

Next outbound call ──► telephony.build_recent_summary(patient_id)
        │                      │
        │               conversation_store.latest_digest(patient_id)
        │                      │  (finds latest CallRecord w/ conversation_id, fetch+cache)
        ▼                      ▼
   dynamic variables include "Previous check-in: ..." line
```

### 1. Models (`app/models.py`)

```python
class ConversationTurn(BaseModel):
    role: Literal["user", "agent"]
    message: str | None = None
    time_in_call_secs: int | None = None

class ConversationDataPoint(BaseModel):
    id: str            # the data_collection identifier, e.g. "pain_level"
    value: Any         # str | int | bool | None as returned
    rationale: str | None = None

class ConversationDetail(BaseModel):
    conversation_id: str
    status: str                       # initiated|in-progress|processing|done|failed
    ready: bool                       # True when status == "done"
    transcript_summary: str | None = None
    call_successful: str | None = None  # success|failure|unknown
    call_duration_secs: int | None = None
    started_at: datetime | None = None
    transcript: list[ConversationTurn] = []
    data_collection: list[ConversationDataPoint] = []
```

`data_collection` is a list (stable order: the known seven first, then any extras) so the
frontend can render it directly.

### 2. Fetch layer (`app/services/elevenlabs_conversations.py`)

- `async def fetch_conversation(conversation_id: str) -> ConversationDetail | None`
- `GET {residency_base}/v1/convai/conversations/{id}` with `xi-api-key`.
- Pure-ish: builds a `ConversationDetail` from the JSON. Tolerant — missing `analysis`
  or `metadata` → fields stay `None`; non-`done` status → `ready=False`, partial data.
- Returns `None` only when telephony is not configured. HTTP/parse errors are caught and
  surfaced as a `failed`-status detail with the error in logs (never raises to the route).
- `_parse_conversation(body: dict) -> ConversationDetail` is a separate pure function so
  it can be unit-tested against a captured sample with no network.

### 3. Cache + digest (`app/conversation_store.py`)

In-memory, functional interface (mirrors `care_plan_store`):

```python
async def get_detail(conversation_id) -> ConversationDetail | None
    # cache hit if cached status == "done"; else fetch_conversation and
    # cache when terminal. Short-circuit returns None if not configured.

async def latest_digest(patient_id) -> str | None
    # find the patient's most recent CallRecord with a conversation_id
    # (via call_store), get_detail it, render a one-line digest.
```

Digest format (omits empty fields):

```
Previous check-in (2026-06-05): mood "tired"; pain 6/10; medication taken: no;
new symptoms: "dizzy when standing"; flagged for follow-up (dizziness on standing).
```

A `_render_digest(detail, when)` pure function keeps rendering testable. The store also
exposes a `prime(detail)` writer so a future webhook can populate the cache directly
(forward-compatibility seam for Approach B).

### 4. Endpoint (`app/routers/calls.py`)

```
GET /patients/{patient_id}/calls/{call_id}/conversation  -> ConversationDetail
```

- Validates the patient and that the call belongs to them.
- 404 if the `CallRecord` has no `conversation_id` (e.g. a failed call).
- Otherwise returns `conversation_store.get_detail(...)`. If ElevenLabs hasn't finished,
  the body carries `status: "processing"`, `ready: false` so the UI shows a "check back"
  state rather than an error.

### 5. Context feed (`app/services/telephony.py`)

`build_recent_summary(patient_id)` gains a leading line from
`conversation_store.latest_digest(patient_id)` when present, so the next call's
`recent_summary` dynamic variable opens with what the patient said last time. The fetch is
on-demand (one extra GET at dial time) and cached.

Async note: `latest_digest` is async (it may fetch). `build_recent_summary` and
`build_dynamic_variables` therefore become `async` and are awaited from the already-async
`place_call`. The digest is best-effort: if it returns `None` or errors, the summary is
built exactly as today. Inbound `build_context_summary` (`services/patient_context.py`) is
left unchanged this round but will reuse `latest_digest()`.

### 6. Frontend (`frontend/src/`)

- `api/client.ts`: `getCallConversation(patientId, callId)` → `ConversationDetail`.
- `types.ts`: matching `ConversationDetail` / `ConversationTurn` / `ConversationDataPoint`.
- `CallPanel.tsx` "Recent calls": each row with a `conversation_id` becomes expandable.
  On expand, fetch the conversation and render a new `CallConversation` component:
  - header: `transcript_summary`, a `call_successful` badge, duration;
  - a structured chip row built from `data_collection` — mood, pain, meds, sleep,
    symptoms, with the **follow-up flag highlighted** (reuses the urgent/attention status
    tints) when `needs_followup` is true;
  - a collapsible turn-by-turn transcript (agent/user bubbles);
  - a "still processing — refresh" affordance when `ready` is false.
- Styling reuses existing tokens (`.tag`, status-soft colors, `.schedule-list` patterns);
  no new color strategy.

### 7. Config (`app/config.py`)

Add `elevenlabs_conversations_url` derived from the existing residency base
(`.../v1/convai/conversations`), alongside `elevenlabs_outbound_url`. No new env vars —
reuses `ELEVENLABS_API_KEY`.

## Error handling

| Situation | Behavior |
|---|---|
| Telephony not configured | `get_detail` returns `None`; endpoint returns 404-style "no conversation data"; digest contributes nothing. |
| Call has no `conversation_id` | Endpoint 404. UI shows nothing extra for that row. |
| ElevenLabs not yet `done` | `ConversationDetail` with `status: processing`, `ready: false`; UI shows "check back" + refresh. |
| ElevenLabs HTTP/parse error | Caught; logged; treated as unavailable (no crash, no digest line). |
| Unknown extra data_collection fields | Passed through to display generically; ignored by digest. |

## Testing

Backend unit tests (mirroring `test_calls.py` / `test_integrations.py`), no network:

- `_parse_conversation` against a captured ElevenLabs JSON sample → asserts transcript,
  summary, `call_successful`, duration, and all seven data points parse correctly,
  including a `done` and a `processing` fixture.
- `_render_digest` → correct one-liner; omits empty fields; handles a follow-up flag.
- Endpoint: 404 when no `conversation_id`; `processing` passthrough; `done` happy path
  (with `fetch_conversation` monkeypatched).
- `build_recent_summary` includes the digest line when a prior conversation exists and is
  unchanged when none does.

## Out of scope / future

- Inbound `get_patient_context` digest (one-line follow-on using `latest_digest`).
- Post-call webhook writer into `conversation_store.prime()` (Approach B).
- MongoDB persistence of conversation details.
- Creating/updating a `CheckIn` record from `data_collection` (the fields deliberately
  mirror the `CheckIn` shape, so this is a natural later step).
- Conversation audio playback.
