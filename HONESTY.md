# HONESTY.md

> Mandatory disclosure for the hackathon. This file lives at the root of your repository. Judges cross-check it against your code and your technical video.
>
> **The deal:** disclosed shortcuts are **not** penalized - that is the entire point of this file. Hidden ones are. Undisclosed pre-built code is heavily penalized, each undisclosed mock carries a small penalty, and a faked demo is heavily penalized. Telling the truth here costs you nothing.

---

## 1. Team - who did what
Judges compare this against `git shortlog -sn`, so keep it honest.

| Member | GitHub handle | Main contributions |
|---|---|---|
| Derin Akar | `D-Akar` | Platform scaffold (FastAPI backend + React dashboard); Hong Kong 3D digital-twin frontend; outbound/inbound voice check-in framework + ElevenLabs agent tool-calls; FHIR CarePlan ingestion; nurse escalation / emergency-redirect logic; clinician PDF report generation; live call transcript tracking. |
| Barnabas Juhasz | `BarnabasJuhasz1` | MongoDB + Docker data layer; FHIR patient-record import and on-dashboard profiles; LLM (Gemma) check-in question generation wired to ElevenLabs; chronic-disease and worsening-symptom modelling. |
| Dario Monopoli | `dariomonopoli-dev` | Garmin wearable pipeline - live vitals, trends, alerts - running on his **own** Garmin account (he is the "live Garmin" patient); real-time patient escalation over Server-Sent Events + nurse call; photoreal HK twin, theming and UI polish; cognitive-screening agent; auto-updating call summaries. |
| Jan | *(no commits - non-code)* | Business development groundwork and the business pitch / go-to-market case (HK government healthcare track). |

---

## 2. What is fully working
Features that run end-to-end on the live app, with real data and real logic.

- **Outbound AI voice check-in call.** Input: a patient + their resolved check-in questions. Output: a **real phone call** placed via the ElevenLabs + Twilio integration (EU data-residency endpoint), where the AI agent speaks with the patient.
- **Consent-gated check-in persona.** Every outbound check-in call (manual "Call now", scheduled, and wearable-triggered) opens by asking the patient for recording/data consent, driven by a per-call `system_prompt`/`first_message` override from code (`app/checkin_agent.py`) rather than a hand-pasted dashboard prompt; the same persona escalates immediately and overrides the gate the moment the patient reports an emergency. (Relies on the ElevenLabs agent's prompt-override toggles being enabled.)
- **Clinical context handed to the voice agent.** Input: the patient's phone number, on an API-key-secured server-tool callback. Output: a JSON context bundle - demographics, active alerts, check-in history, wearable readings, configured questions, and the patient's **FHIR-ingested CarePlan + profile from MongoDB** - consumed by the agent at call time.
- **Live mid-call escalation.** Input: the agent's "escalate" tool-call during a conversation. Output: the patient flips to *urgent*, **every open clinician dashboard recolors in real time over Server-Sent Events**, and a nurse-alert call is placed.
- **Wearable-triggered auto-call + nurse fallback.** Input: live vitals crossing the urgent threshold (Garmin `/live`, or a real Bluetooth heart-rate watch via Web Bluetooth, or the demo control). Output: the patient flips to *urgent* over SSE and a consent-gated check-in call is placed automatically; if the patient does not answer, the emergency is routed to the on-call nurse.
- **Scheduled & auto-seeded daily check-ins.** Input: a per-patient schedule. Output: recurring daily (or one-off) check-in calls via an APScheduler cron job in **Asia/Hong_Kong**; a daily call per patient is seeded on startup, and schedules can be added/cancelled per patient from the dashboard.
- **Post-call transcript + extracted check-in.** Input: a completed call ID. Output: the transcript and structured check-in data, pulled on demand from ElevenLabs into the dashboard.
- **Garmin wearable vitals.** Input: a real Garmin account export. Output: daily heart rate, resting HR, stress, sleep, SpO2, respiration, body battery and steps on the dashboard.
- **FHIR ingestion → long-term storage.** Input: FHIR patient JSON. Output: 555 records upserted into MongoDB and overlaid onto dashboard patients (`GET /patients/{id}/profile`).
- **FHIR CarePlan ingestion.** Input: a FHIR CarePlan (R4/R5) as JSON or XML. Output: a stored, parsed plan that feeds the live call context above.
- **Rule-based triage alerts.** Input: wearable readings + vitals. Output: severity-tagged health alerts driving the dashboard's risk flags.
- **LLM-generated check-in questions.** Input: a patient's context. Output: patient-specific check-in questions (via the Gemma/Gemini API; best-effort, needs a key).
- **Clinician PDF report.** Input: a patient ID. Output: a downloadable clinical-summary PDF (reportlab).
- **Live clinician dashboard.** A React Hong Kong digital-twin map + roster, updating in real time over SSE.

---

## 3. What is mocked, stubbed, or hardcoded
Every shortcut. **Undisclosed mocks carry a small penalty each. Anything listed here = free.**

| What is faked | Where (file:line or folder) | Why we mocked it | What the real version would do |
|---|---|---|---|
| Patient roster (names + baseline check-ins/wearables for non-featured patients) | `backend/app/data.py` | Need a populated demo roster without using real patient data | Read patients from the practice's real registry |
| The 555 "FHIR patient records" are **Synthea**-generated synthetic data, not real patients | `data/fhir_processed/` (surfaced via `backend/app/fhir_source.py`) | Cannot and should not demo on real clinical records | Ingest consented, real patient FHIR records |
| Call schedules + call history persist to MongoDB best-effort, with an in-memory fallback when Mongo is unreachable (which resets on restart) | `backend/app/call_store.py` | No dedicated DB layer; reuse the Mongo instance, degrade to memory if it's down | Persist to a real, always-on database |
| Check-in, conversation and care-plan stores are Mongo-backed best-effort with an in-memory fallback | `backend/app/checkin_store.py`, `conversation_store.py`, `care_plan_store.py` | Same - reuse Mongo where wired, fall back to memory | DB-backed persistence with history |
| Auth/RBAC + encryption + consent (+ scope enforcement) + audit + rectification + per-client callback keys exist but default OFF in the demo | `backend/app/security/`, `app/audit.py`, `app/consent_store.py`, `routers/privacy.py`, `routers/integrations.py`; gated by `CARELOOP_*` env flags | Keep the open demo working without tokens/keys; controls are real when enabled | Enabled in production via env; managed KMS + HK residency |

---

## 4. External APIs, services & data sources
Everything the project calls. Each marked real or mocked.

| Service / API / dataset | Used for | Real call or mocked? | Auth |
|---|---|---|---|
| ElevenLabs Conversational AI | The voice agent that conducts check-in calls | **Real** | API key |
| Twilio (via the ElevenLabs integration) | Telephony / placing the outbound PSTN calls | **Real** | Via ElevenLabs (key) |
| Garmin Connect | Live wearable vitals for the featured patient | **Real** | Account login (a team member's own account) |
| MongoDB | Patient / FHIR record store (long-term) | **Real** (local, Docker Compose) | Local / none |
| Gemma via the Gemini API | Generating tailored check-in questions | **Real** | API key |
| Synthea (synthetic patient generator) | The 555 synthetic FHIR records | **Dataset, generated offline** | None |

---

## 5. Pre-existing code

*All code in this repo was written during the hackathon window.*

Clarifications, for full transparency:
- **Prior experience, not prior code (Derin Akar).** The Twilio + ElevenLabs wiring drew on Derin's prior experience setting up that infrastructure - that know-how sped up configuration and helped us avoid dead ends - but **no code or content from any prior project was copied in.**
- **Third-party tooling.** We use ElevenLabs, Twilio and MongoDB via their public SDKs/APIs, and the synthetic records come from the open-source **Synthea** generator. These are external tools/datasets, not our own pre-existing code.

---

## 6. Known limitations & next steps
Naming these honestly is a strength, not a flaw.

- **No live eHRSS / eHealth integration.** No third party can connect to eHRSS today - it is gated behind a HK government accreditation scheme. We are *FHIR-native and accreditation-ready*, not integrated. Full background and engagement plan: [`docs/hk-ehealth-market.md`](docs/hk-ehealth-market.md).
- **PDPO/GDPR/PIPL controls are implemented but config-gated and OFF by default** - AES-256-GCM encryption at rest, RBAC auth, a tamper-evident audit log, a retention engine, consent records + consent-scope enforcement + a verbal-consent webhook, data export/rectification/erasure, per-client integration keys, and HTTPS/HSTS hardening all exist (`app/security/`, `app/audit.py`, `app/consent_store.py`, `app/retention.py`, `app/routers/privacy.py`, `app/routers/integrations.py`), default off so the demo runs unchanged, and tested when enabled. A breach-response runbook is documented ([`docs/breach-runbook.md`](docs/breach-runbook.md)) and the LLM can be kept in-region (`LLM_PROVIDER=vllm`). See [`PRIVACY.md`](PRIVACY.md). **Still not done (needs hosting/cloud/front-end/government, not code):** HK data residency, a managed KMS, dashboard auto-logout, and eHRSS accreditation.
- **Auth/consent default to OFF in the demo** - RBAC and consent records are implemented (above) but disabled unless the env flags are set; the ElevenLabs callbacks support a per-client rotatable keyset (`CARELOOP_TOOL_API_KEYS`) but default to a single shared key.
- **Persistence is in-memory** for calls, check-ins, conversations and care plans - these reset on backend restart (MongoDB backing is best-effort where wired).
- **The "Demo" control injects synthetic vitals.** The top-bar *Demo* button pins the featured patient's heart rate (~85 bpm, lightly jittered, with a climbing step count) so the escalation can be triggered on cue without a live device (`frontend/src/hooks/useLiveVitals.ts`); it is clearly labelled "Simulating" in the UI. The real path is the Bluetooth watch (Web Bluetooth) or the Garmin export. The featured/demo patient is also started *stable* so the live stable→urgent flip is visible on stage.
- **Daily check-in calls are auto-seeded at 09:00 (Asia/Hong_Kong) and the schedules are in-memory** (reset on restart, re-seeded each boot). With live ElevenLabs keys this would place real calls at that time; disable with `CARELOOP_SEED_DAILY_CHECKINS=0`.
- **Wearable readings are exposed as LOINC-coded FHIR `Observation`s** via the read surface (`GET /fhir/Observation?patient=`), but there is **no FHIR write surface and no eHRSS deposit** yet (see the eHRSS item above).
- **No Cantonese LLM fine-tuning and no vector-database memory** - structured long-term context *is* injected into calls (history + alerts + FHIR CarePlan), but it isn't a fine-tuned Cantonese model or a vector store.
- **No real blood pressure** - Garmin watches have no BP sensor, so no BP reading exists in the system.
