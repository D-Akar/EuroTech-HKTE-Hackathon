# Outbound agent setup (ElevenLabs)

The platform runs **two** ElevenLabs Conversational AI agents:

| Direction | Who starts the call | How context is loaded | Agent id env var |
|-----------|--------------------|------------------------|------------------|
| **Outbound** | We dial the patient on the daily schedule (`telephony.place_call`) | Pushed at dial time as dynamic variables (`{{patient_name}}`, `{{patient_age}}`, `{{recent_summary}}`, `{{questions}}`, `{{opening_question}}`, `{{privacy_response}}`) | `ELEVENLABS_AGENT_ID` |
| **Inbound** | The patient calls *us* back to chat | Pulled at call start via the `get_patient_context` server tool | `ELEVENLABS_INBOUND_AGENT_ID` |

This guide covers the **outbound** agent. The backend dials it via
`telephony.place_call`, which POSTs to the ElevenLabs outbound call API with the
per-patient context injected as **dynamic variables** - see
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

The backend pushes these at dial time - no server tool is required for the
outbound agent. Reference them directly in the prompt with `{{...}}`:

| Variable | Contents |
|----------|----------|
| `{{patient_id}}` | Opaque patient identifier. **Not for the prompt** - it is the value the `escalate_emergency` tool sends back so the backend knows which patient to escalate. |
| `{{patient_name}}` | Patient's name |
| `{{patient_age}}` | Patient's age |
| `{{recent_summary}}` | Last 3 phone check-ins + latest wearable reading |
| `{{questions}}` | The patient's **personalised** check-in questions for today, numbered and in priority order. Generated offline by cross-referencing the patient's recent check-ins against the worsening-symptom guide for their chronic conditions (`question_gen` / the dashboard "Questions to ask" panel); falls back to the practice's default questions if none have been generated. The agent leads with question 1. |
| `{{opening_question}}` | A **fixed opening question** asked first, before `{{questions}}`. Editable in [`opening_question.md`](../../Prompts/opening_question.md) (in Prompts/); read fresh on every call, so edits need no restart. |
| `{{privacy_response}}` | The **verbatim** reply the agent speaks when the patient asks about data storage, privacy, security, or encryption ("is my data safe?", "is this recording encrypted?"). Editable in [`privacy_response.md`](../../Prompts/privacy_response.md) (in Prompts/); read fresh on every call. |

## 3. System-prompt snippet

Add an instruction so the agent opens warmly, **gates the whole call behind a
consent confirmation** (the opening question), only then works through the
personalised questions in order, stays flexible when the patient brings something
up, and finally **hands the conversation back to the patient** before the call
ends:

```
You are a warm, patient phone companion calling {{patient_name}} (age
{{patient_age}}) for their daily care check-in. Speak slowly and simply.

Recent context for this patient:
{{recent_summary}}

CONSENT QUESTION (you MUST get a clear answer to this before anything else):

{{opening_question}}

These are the personalised check-in questions for today, in priority order:

{{questions}}

STEP 1 - GREET, THEN ASK FOR CONSENT.
Greet {{patient_name}} warmly by name, then immediately ask the CONSENT QUESTION
above, word for word. Do not do anything else yet.

STEP 2 - THE CONSENT GATE (this is strict).
You may NOT ask any check-in question, acknowledge or discuss symptoms, give any
advice, or move the conversation forward in ANY way until the patient has clearly
confirmed the consent question with an affirmative answer (for example "yes",
"yes I agree", "that's fine", "go ahead"). Until you hear that clear yes:
- If the patient starts talking about something else - even something important
  like "I actually felt dizzy today" - do NOT engage with it, do not ask
  follow-ups, and do not start the check-in. Warmly acknowledge you heard them and
  that you will come back to it, explain you first need their confirmation, and
  then ask the CONSENT QUESTION again. For example: "I do want to hear about that,
  and we will come back to it in just a moment. First, though, I need your
  confirmation. [re-ask the consent question]"
- If the patient asks about privacy, their data, the recording, security, or
  encryption, handle it with the PRIVACY rule below, and then ask the CONSENT
  QUESTION again. Answering a privacy question is NOT consent - you still need a
  clear yes afterwards before you may continue.
- If the answer is unclear, ambiguous, or off-topic, gently ask the CONSENT
  QUESTION again. Keep doing this until you get a clear yes or a clear no.
- If the patient clearly declines or says no, do not start the check-in. Warmly
  reassure them that that is okay, let them know their care practice will follow
  up, thank them, and close the call kindly.

STEP 3 - ONLY AFTER A CLEAR YES, run the check-in.
Once, and only once, the patient has confirmed, thank them and begin the
personalised questions. Ask the FIRST question in the list, then work through the
rest IN ORDER, one at a time, listening fully to each answer. Make sure every
question gets asked before you wrap up.

After consent, stay conversational, not robotic. You are NOT limited to reading
the list:
- If the patient brings up something relevant - a symptom, a worry, how they
  slept, a medication issue - FIRST respond to what they raised: acknowledge it,
  ask a natural follow-up, and let them finish. THEN return to the questions
  where you left off.
- If their answer already covers a later question on the list, don't ask it
  again robotically - acknowledge it and move to the next one still outstanding.
- Keep a mental note of which questions you have and haven't covered, so a
  tangent never causes you to skip one.

PRIVACY AND DATA QUESTIONS (applies at any point in the call).
If the patient asks about how their information or this call is stored, who can
see it, whether it is private, safe, secure, or encrypted, or anything similar
about their data or recording, respond by speaking the following text VERBATIM,
word for word, without adding to it, summarising it, or changing it:

{{privacy_response}}

Do not improvise your own answer about data or privacy - always use the exact
text above. After you have spoken it: if you do not yet have the patient's
consent, ask the CONSENT QUESTION again; otherwise ask if that answers their
question and return to the check-in where you left off.

Once you have been through all the questions, do NOT end the call. Ask the
patient warmly whether there is anything else they would like to talk about or
any questions they have for you - about how they have been feeling, their
medication, sleep, or anything else on their mind. Answer simply and
reassuringly. Keep inviting follow-ups ("Is there anything else I can help
with?") until the patient signals they are done, then thank them and close the
call kindly.

If a question would require clinical judgement or a diagnosis, do not give
medical advice - reassure them and say their care practice will follow up.

The ONE exception to the consent gate is a medical emergency: if the patient
describes an emergency at any point, including before they have consented, act on
it immediately per the emergency-escalation rules. Patient safety always
overrides the consent step.
```

Key behaviours this snippet enforces:

- **Consent gate, asked first.** The agent asks `{{opening_question}}` (from
  [`opening_question.md`](../../Prompts/opening_question.md), now phrased as a consent
  confirmation) before anything else, and will **not** ask a check-in question or
  engage with any topic the patient raises - even "I felt dizzy today" - until it
  hears a clear affirmative. An unclear answer, a tangent, or a privacy question
  all just loop back to re-asking the consent question.
- **Verbatim privacy answer (does not count as consent).** When the patient asks
  about their data, privacy, or encryption, the agent speaks `{{privacy_response}}`
  (from [`privacy_response.md`](../../Prompts/privacy_response.md)) word for word, then
  still needs a clear yes before continuing. Edit either markdown file and the
  change takes effect on the next call (no restart).
- **Only after a yes: the personalised questions, in order.** Then it works
  through `{{questions}}` (top of the list is the highest-priority symptom
  follow-up), staying flexible - responding to what the patient raises before
  returning to the list - rather than reading a rigid script. The *"do NOT end the
  call"* line keeps the floor open for the patient afterwards, mirroring
  [`INBOUND_AGENT_SETUP.md`](./INBOUND_AGENT_SETUP.md).
- **Emergencies override the gate.** A described medical emergency is acted on
  immediately, even before consent - patient safety comes first.

## 4. First message

The **"First message"** field in the ElevenLabs dashboard is the line the agent
speaks the instant the call connects. Because the consent gate must come first,
the first message should greet the patient and hand **straight into the consent
question** - do NOT end it on an open "how are you?" invitation, which would
encourage the patient to start talking before they have confirmed. Use:

```
Hello {{patient_name}}, it's CareLoop calling for your daily check-in. Before we begin, I just need to confirm one quick thing with you.
```

A warmer variant:

```
Hi {{patient_name}}, this is your CareLoop companion. It's lovely to reach you. Before we get started, there's one quick thing I need to ask for your agreement on.
```

Keep it short; the system prompt then speaks the consent question (`{{opening_question}}`)
and holds the gate until the patient confirms. The deeper context
(`{{recent_summary}}`, the `{{questions}}`) is handled by the system prompt once
the conversation is underway - don't cram it into the first message.

## (Optional) Let the outbound agent answer data questions

The outbound agent only receives `{{recent_summary}}`, so it can only speak to
what is in that summary. If you want it to answer richer questions during the
open-floor phase (e.g. "what was my heart rate last Tuesday?"), attach the same
`get_patient_context` server tool used by the inbound agent - see
[`elevenlabs-get_patient_context.tool.json`](./elevenlabs-get_patient_context.tool.json)
and step 2 of [`INBOUND_AGENT_SETUP.md`](./INBOUND_AGENT_SETUP.md) - and add:

```
If the patient asks about their health history or readings and the answer is not
in the context above, call the `get_patient_context` tool to look it up before
answering.
```

## 5. Emergency-escalation tool (`escalate_emergency`)

This lets the agent raise an urgent clinical escalation **mid-call** when the
patient reports an emergency. Calling it flips the patient to **URGENT** on every
dashboard in real time (over SSE) and places an immediate alert call to the
on-call nurse - the same path as the dashboard's manual escalate button, behind
`POST /integrations/elevenlabs/escalate`.

### Attach the tool

1. Import [`elevenlabs-escalate_emergency.tool.json`](./elevenlabs-escalate_emergency.tool.json),
   or recreate it as a **Webhook** server tool.
2. Set the tool `url` to your public host:
   `https://<your-public-host>/integrations/elevenlabs/escalate`
   (use a tunnel such as ngrok against port 8000 when developing locally).
3. Set the `X-API-Key` request header to your `ELEVENLABS_TOOL_API_KEY` value -
   the **same** key as the `get_patient_context` tool.
4. The request body has two fields:
   - `patient_id` - bound to the **dynamic variable** `{{patient_id}}` (injected
     at dial time; the LLM must **not** fill or ask for it).
   - `reason` - filled by the LLM with what the patient just reported.

### When the agent should call it - trigger conditions

Be explicit in the prompt, because the cost of a false negative (missing a real
emergency) and a false positive (a nurse scrambled for nothing) are both high.
Add this block to the system prompt:

```
EMERGENCY ESCALATION
You have a tool named `escalate_emergency`. When the patient describes any of the
following, you MUST use it:
- Chest pain, pressure, or tightness; difficulty breathing.
- Signs of a stroke: face drooping, arm weakness, slurred or confused speech.
- A fall with injury, inability to get up, or hitting their head.
- Heavy or uncontrolled bleeding.
- Fainting, loss of consciousness, or a seizure.
- Thoughts of harming themselves.
- Any symptom they describe as severe, sudden, or frightening, or that you judge
  needs a clinician right now.

How to respond, IN THIS ORDER:
1. FIRST, actually call the `escalate_emergency` tool. Do this before you say
   anything reassuring, mid-sentence if necessary, and before finishing any
   check-in questions. Put what the patient said into `reason`, in their own
   words (one or two sentences). Do NOT ask them for an ID or reference number.
2. ONLY AFTER the tool call returns: stay on the line, calmly tell the patient a
   nurse has been alerted and will follow up right away, keep them company, and
   if appropriate suggest they also call local emergency services.

CRITICAL: Saying "I am escalating this" or "a nurse has been alerted" WITHOUT
actually calling the `escalate_emergency` tool is a critical failure. Your words
alone do nothing - only the tool call alerts the nurse and flips the patient's
status. Never tell the patient a nurse has been alerted unless you have actually
called the tool in this turn. Speaking about escalating is NOT escalating.

Do NOT escalate for routine or mild concerns (a slightly poor night's sleep, a
mild ache, general low mood with no risk of self-harm, a medication question).
For those, reassure them and note that their practice will follow up. When in
genuine doubt about severity, escalate.
```

Place this block **after** the check-in instructions but make clear it overrides
them - escalation interrupts the normal flow. The `{{patient_id}}` plumbing is
invisible to the patient; the agent never speaks or requests it.

> **If the agent describes escalating but no request reaches your backend**
> (check `http://localhost:4040`), the prompt is not the problem - the tool is
> almost certainly **not attached to this agent**. A model cannot call a tool it
> doesn't have, so it narrates the action instead. Open the agent → **Tools** and
> confirm `escalate_emergency` is in the list before blaming the wording.

## 6. Consent-record tool (`record_consent`) - optional

The consent gate (§ system prompt, `app/checkin_agent.py`) already *enforces*
consent live on every call. To also **persist** the patient's spoken decision as a
durable consent record, wire one more tool so the agent reports the answer back:

1. Add a tool `record_consent` (a webhook POST), same `X-API-Key` header as the
   other tools, to:
   `https://<your-public-host>/integrations/elevenlabs/consent`
2. Body parameters: `patient_id` (use the `{{patient_id}}` dynamic variable),
   `granted` (boolean - true on a clear yes, false on a decline), and optionally a
   short `note` paraphrasing what the patient said.
3. In the consent step of the prompt, instruct the agent: *the moment the patient
   gives a clear yes or no to the consent question, call `record_consent` with that
   decision, then continue.*

→ The backend stores a `method="voice"` `ConsentRecord` (policy-versioned) and
audits it. Without this tool the consent gate still works; you just won't have the
verbal grant written to the consent store automatically.

## Verify end to end

1. Run the backend (`uvicorn app.main:app --reload`) with the `ELEVENLABS_*`
   vars set in `backend/.env`, and expose it publicly (e.g. `ngrok http 8000`)
   so the tool URLs are reachable.
2. **Tool smoke test (no call):** in the ElevenLabs tool builder, use the
   **Test** button on `escalate_emergency` with `patient_id` = a seeded id and a
   sample `reason`. Equivalently, from a terminal:
   ```powershell
   $body = @{ patient_id = 1; reason = "Reports crushing chest pain now." } | ConvertTo-Json
   Invoke-RestMethod -Uri "https://<your-public-host>/integrations/elevenlabs/escalate" `
     -Method Post -ContentType "application/json" `
     -Headers @{ "X-API-Key" = "<ELEVENLABS_TOOL_API_KEY>" } -Body $body
   ```
   → `200` with `"status": "urgent"`, the patient recolors to red on an open
   dashboard, and the nurse alert call is placed (if `NURSE_PHONE_NUMBER` is set).
3. **Full call:** trigger an instant call to a seeded patient, then act out one
   of the trigger symptoms above. Confirm the agent invokes `escalate_emergency`,
   the patient flips to urgent live on the dashboard, the nurse is called, and the
   agent reassures the patient that their care team has been alerted.
4. Confirm the check-in flow still works normally when no emergency is mentioned
   (agent greets by name, works through the questions, invites open questions).
