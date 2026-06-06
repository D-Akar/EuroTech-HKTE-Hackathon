# Inbound agent setup (ElevenLabs)

The platform runs **two** ElevenLabs Conversational AI agents:

| Direction | Who starts the call | How context is loaded | Agent id env var |
|-----------|--------------------|------------------------|------------------|
| **Outbound** | We dial the patient on the daily schedule (`telephony.place_call`) | Pushed at dial time as dynamic variables (`{{patient_name}}`, `{{recent_summary}}`, `{{questions}}`) | `ELEVENLABS_AGENT_ID` |
| **Inbound** | The patient calls *us* back to chat | Pulled at call start via the `get_patient_context` server tool | `ELEVENLABS_INBOUND_AGENT_ID` |

This guide covers the **inbound** agent. The backend never dials it - ElevenLabs
answers the inbound number and runs the agent. The backend's only role inbound is
serving the `get_patient_context` tool endpoint.

## 1. Create the inbound agent

1. In the ElevenLabs dashboard, create a second Conversational AI agent (e.g.
   "CareLoop Inbound").
2. Link it to your **inbound** Twilio phone number (the number patients dial).
3. Copy its agent id into `backend/.env` as `ELEVENLABS_INBOUND_AGENT_ID`
   (stored for reference; see `backend/.env.example`).

## 2. Attach the `get_patient_context` tool

1. Import the tool definition from
   [`elevenlabs-get_patient_context.tool.json`](./elevenlabs-get_patient_context.tool.json),
   or recreate it as a **Webhook** server tool.
2. Set the tool `url` to your public API host, e.g.
   `https://<your-public-host>/integrations/elevenlabs/patient-context`
   (use a tunnel such as ngrok when developing locally against port 8000).
3. Set the `X-API-Key` request header to your `ELEVENLABS_TOOL_API_KEY` value.
4. The `phone_number` query parameter is bound to the **system dynamic variable**
   `system__caller_id` (the caller's number, populated automatically on voice
   calls). The LLM does not fill it - the caller's real number is always passed to
   `data.get_patient_by_phone()`, which accepts E.164 with or without the `+`.

## 3. System-prompt snippet

Add an instruction so the agent loads context the moment a call connects and
uses the returned `context_summary`:

```
At the very start of every call, immediately call the `get_patient_context`
tool before saying anything else. Use the returned `context_summary` to greet
the caller by name and naturally acknowledge their recent phone check-ins,
wearable trends, and any active health alerts.

Then be a warm, patient companion: speak slowly and simply, ask how they are,
listen, and let them lead the conversation. If `get_patient_context` returns no
match for the caller, greet them politely and continue without personal details.
```

The tool returns the full patient record; `context_summary` is the
ready-to-speak narrative the agent should rely on.

## 3b. First message

Unlike the outbound agent, the inbound agent has **no patient context at connect
time** - it must call `get_patient_context` first. So the **"First message"**
field should be a generic, name-free holding greeting (or left blank so the agent
speaks only after the tool returns). If you set one, keep it neutral:

```
Hello, thank you for calling CareLoop. One moment while I pull up your details.
```

Do **not** put `{{patient_name}}` in the inbound first message - the caller's name
isn't known until the tool resolves their phone number. The personalised,
by-name greeting happens in the system prompt *after* the tool call, using
`context_summary`.

## Verify end to end

1. Run the backend (`uvicorn app.main:app --reload`) and expose it publicly.
2. Confirm the tool endpoint directly:
   `GET /integrations/elevenlabs/patient-context?phone_number=+10000000001`
   with header `X-API-Key: <ELEVENLABS_TOOL_API_KEY>` → `200` with a populated
   `context_summary`.
3. Call the inbound Twilio number from a seeded patient's phone and confirm the
   agent greets by name using the fetched context.
