# Outbound agent setup (ElevenLabs)

The platform runs **two** ElevenLabs Conversational AI agents:

| Direction | Who starts the call | How context is loaded | Agent id env var |
|-----------|--------------------|------------------------|------------------|
| **Outbound** | We dial the patient on the daily schedule (`telephony.place_call`) | Pushed at dial time as dynamic variables (`{{patient_name}}`, `{{patient_age}}`, `{{recent_summary}}`, `{{questions}}`) | `ELEVENLABS_AGENT_ID` |
| **Inbound** | The patient calls *us* back to chat | Pulled at call start via the `get_patient_context` server tool | `ELEVENLABS_INBOUND_AGENT_ID` |

This guide covers the **outbound** agent. The backend dials it via
`telephony.place_call`, which POSTs to the ElevenLabs outbound call API with the
per-patient context injected as **dynamic variables** — see
`build_dynamic_variables()` in `backend/app/services/telephony.py`. The agent's
prompt (configured in the ElevenLabs dashboard) must reference those variables.

## 1. Create the outbound agent

1. In the ElevenLabs dashboard, create a Conversational AI agent (e.g.
   "CareLoop Outbound").
2. Link it to your **outbound** Twilio phone number (the number we dial *from*),
   and copy its phone-number id into `backend/.env` as
   `ELEVENLABS_AGENT_PHONE_NUMBER_ID`.
3. Copy the agent id into `backend/.env` as `ELEVENLABS_AGENT_ID`
   (see `backend/.env.example`).

## 2. Dynamic variables

The backend pushes these at dial time — no server tool is required for the
outbound agent. Reference them directly in the prompt with `{{...}}`:

| Variable | Contents |
|----------|----------|
| `{{patient_name}}` | Patient's name |
| `{{patient_age}}` | Patient's age |
| `{{recent_summary}}` | Last 3 phone check-ins + latest wearable reading |
| `{{questions}}` | The practice's configured check-in questions, numbered |

## 3. System-prompt snippet

Add an instruction so the agent opens warmly, works through the configured
check-in questions, and then **hands the conversation back to the patient** so
they can ask their own questions before the call ends:

```
You are a warm, patient phone companion calling {{patient_name}} (age
{{patient_age}}) for their daily care check-in. Speak slowly and simply.

Recent context for this patient:
{{recent_summary}}

Greet {{patient_name}} by name and naturally acknowledge their recent check-ins
or wearable trends from the context above. Then gently work through these
check-in questions, one at a time, listening fully to each answer before moving
on:

{{questions}}

Once you have been through the questions, do NOT end the call. Ask the patient
warmly whether there is anything they would like to talk about or any questions
they have for you — about how they have been feeling, their medication, sleep,
or anything else on their mind. Answer simply and reassuringly. Keep inviting
follow-ups ("Is there anything else I can help with?") until the patient signals
they are done, then thank them and close the call kindly.

If a question would require clinical judgement or a diagnosis, do not give
medical advice — reassure them and say their care practice will follow up.
```

The key line is *"do NOT end the call"* after the questions: without it the agent
tends to wrap up as soon as the scripted questions are answered. This snippet
keeps the floor open for the patient, mirroring the inbound agent's
"let them lead the conversation" guidance in
[`INBOUND_AGENT_SETUP.md`](./INBOUND_AGENT_SETUP.md).

## 4. First message

The **"First message"** field in the ElevenLabs dashboard is the line the agent
speaks the instant the call connects. Because the outbound agent already has the
dynamic variables at dial time, it can greet the patient by name immediately. Use
one of these (or rotate between them):

```
Hello {{patient_name}}, it's CareLoop calling for your daily check-in. How are you doing today?
```

A warmer, lower-pressure variant:

```
Hi {{patient_name}}, this is your CareLoop companion checking in. Is now a good time for a quick chat about how you've been feeling?
```

Keep it short and end on an open question so the patient starts talking. The
deeper context (`{{recent_summary}}`, the `{{questions}}`) is handled by the
system prompt once the conversation is underway — don't cram it into the first
message.

## (Optional) Let the outbound agent answer data questions

The outbound agent only receives `{{recent_summary}}`, so it can only speak to
what is in that summary. If you want it to answer richer questions during the
open-floor phase (e.g. "what was my heart rate last Tuesday?"), attach the same
`get_patient_context` server tool used by the inbound agent — see
[`elevenlabs-get_patient_context.tool.json`](./elevenlabs-get_patient_context.tool.json)
and step 2 of [`INBOUND_AGENT_SETUP.md`](./INBOUND_AGENT_SETUP.md) — and add:

```
If the patient asks about their health history or readings and the answer is not
in the context above, call the `get_patient_context` tool to look it up before
answering.
```

## Verify end to end

1. Run the backend (`uvicorn app.main:app --reload`) with the `ELEVENLABS_*`
   vars set in `backend/.env`.
2. Trigger an instant call to a seeded patient from the dashboard (or POST to the
   calls endpoint).
3. Confirm the agent greets by name, works through the configured questions, and
   then invites the patient to ask their own questions before hanging up.
