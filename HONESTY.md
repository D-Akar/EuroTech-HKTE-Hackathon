# HONESTY.md — what's real vs. what's mocked

This document is for the hackathon jury and our partners, to be read alongside our pitch
materials. We believe a prototype is more credible when it's honest about its own
boundaries — so rather than blur the line, we draw it clearly here.

The short version: **the product engine is real and working end to end.** Real outbound AI
voice calls, a voice agent that receives each patient's full clinical context, live
mid-call escalation that recolors the clinician dashboard in real time, real wearable data,
real FHIR ingestion into long-term storage, LLM-generated questions, and PDF clinical
reports all run today. What is *synthetic* is some of the patient **data content** (we can't
demo on real patients), and what is *not yet built* is the **external regulatory
integration** (eHRSS, PDPO controls) — which, importantly, no third party can build yet
because it's gated behind a HK government accreditation scheme (see
`docs/hk-ehealth-market.md`).

Nothing in our pitch should outrun what's recorded here. If a claim elsewhere isn't backed
by a ✅ below, treat it as roadmap.

Legend:
- ✅ **Real** — works end to end against real services/infrastructure.
- 🟡 **Partial** — real and working, with a stated limit (e.g. in-memory persistence).
- 🧪 **Synthetic data** — the mechanism is real; the patient *data* is generated/seeded.
- ⛔ **Roadmap** — described in our vision docs, not yet in code.

Last reviewed: 2026-06-07.

---

## ✅ What's genuinely built and working

| Capability | Status | Reality |
| --- | --- | --- |
| **Outbound AI voice check-in calls** | ✅ Real | Real calls placed via the ElevenLabs + Twilio integration on the EU data-residency endpoint. |
| **Clinical context handed to the voice agent** | ✅ Real | A secured (API-key) server-tool callback assembles each patient's full context — demographics, active alerts, check-in history, wearable readings, configured questions, and their **FHIR-ingested CarePlan + profile from long-term (MongoDB) storage** — and serves it to the agent at call time. |
| **Live mid-call escalation** | ✅ Real | The agent can flag a patient mid-conversation; the backend flips them to *urgent*, **recolors every open clinician dashboard in real time over Server-Sent Events**, and places a nurse-alert call. |
| **Call transcript + extracted check-in data** | ✅ Real | After a call, the transcript and structured check-in data are pulled back on demand from ElevenLabs and shown in the dashboard. |
| **Call scheduling (one-off + recurring)** | 🟡 Real, in-memory | A real APScheduler engine places scheduled and daily check-in calls; the schedule/history store is in-memory and resets on backend restart. |
| **Garmin wearable pipeline** | ✅ Real | Real vitals (heart rate, resting HR, stress, sleep, SpO2, respiration, body battery, steps) pulled from a real Garmin account for the live patient. |
| **FHIR ingestion → long-term storage** | ✅ Real (🧪 data) | A real pipeline parses FHIR records and upserts them into MongoDB (555 records), overlaid onto dashboard patients. The *pipeline and storage are real*; the *records* are synthetic (see below). |
| **FHIR CarePlan ingestion** | ✅ Real | Parses FHIR **CarePlan (R4/R5) from JSON or XML**, persists it, and feeds it into the live call context above. |
| **Rule-based alerting / triage** | ✅ Real | Health alerts are computed from wearable readings and vitals and drive the dashboard's risk flags. |
| **LLM-generated tailored check-in questions** | ✅ Real | The "Questions to ask" panel generates patient-specific questions via an LLM (best-effort; needs an API key). |
| **Clinician PDF report** | ✅ Real | Generates a downloadable clinical summary PDF (reportlab). |
| **Clinician dashboard + live health timeline** | ✅ Real | React dashboard running against the live API, updating in real time over SSE. |

> Read together, the daily-check-in loop is real today: schedule or trigger a call → the
> agent speaks with the patient using their real clinical context → it can escalate live →
> the transcript and extracted check-in flow back to the dashboard. That full loop works.

---

## 🧪 Where the data is synthetic (mechanisms are real)

- **The 555 FHIR patient records are Synthea-generated** (a standard open-source
  synthetic-patient generator), not real patients — we can't and shouldn't demo on real
  clinical data. The ingestion, storage, overlay, and call-context pipelines that process
  them are all real.
- **Most dashboard patients are seeded demo profiles.** One patient runs on real Garmin
  vitals; promoted slots show (synthetic) FHIR profiles; the rest are hand-seeded so the
  dashboard is populated for demonstration.
- **A committed synthetic Garmin fallback** lets a fresh setup show wearable data even
  without the live Garmin login present; the live export is real, the fallback is labelled
  synthetic.
- **Wearable readings aren't yet emitted as FHIR `Observation` resources** — they flow
  through our own data shape today. Mapping them to LOINC-coded FHIR Observations is a
  near-term roadmap step.

---

## ⛔ Roadmap (in our vision docs, not yet in code)

These appear in `PROJECT.md` / `PRODUCT.md` as the product vision. We flag them so they're
never mistaken for working features:

- **Live eHRSS / eHealth integration via HL7 FHIR R4.** No eHRSS integration code today —
  and, crucially, **no third party can connect to eHRSS at present**: the pathway is gated
  behind a HK government accreditation scheme. Our honest position is *FHIR-native and
  accreditation-ready*, not *integrated*. Full background and engagement plan:
  `docs/hk-ehealth-market.md`.
- **PDPO compliance, AES-256 at rest, TLS 1.3, local (HK) data residency.** Stated as our
  compliance intent; the prototype does not yet implement these controls.
- **Authentication / consent layer.** No login or consent flow yet (the ElevenLabs
  server-tool callbacks *are* API-key secured; full user auth is roadmap).
- **Cantonese LLM fine-tuning and speech tuning for elderly speakers.** Voice is provided by
  the external ElevenLabs agent; we have not fine-tuned a Cantonese model.
- **Vector-database long-term memory.** Real long-term context *is* injected into calls
  (history + alerts + FHIR CarePlan from MongoDB); the specific *vector-database*
  implementation in the vision doc is not built.
- **Medical-device telemetry beyond Garmin, cellular-eSIM wearables, GBA cross-border
  sync.** Not implemented.
- **Blood pressure from wearables.** Garmin watches have no blood-pressure sensor, so no
  real BP reading exists in the system.

---

## Code reuse & prior work (transparency disclosure)

In the spirit of fair competition, our disclosure on reused code and external content:

- **Developer familiarity with infrastructure (Derin Akar).** Our integrations with
  **Twilio** and **ElevenLabs** draw on Derin Akar's prior experience setting up that same
  infrastructure. That experience informed *how* we wired things up — it sped up
  configuration and helped us avoid dead ends — but **all of the actual code and
  connections in this repository were written from zero for this hackathon. No code or
  content from any prior project was directly copied in.**
- **Third-party services and open data.** We use standard third-party platforms (ElevenLabs,
  Twilio, MongoDB) via their public SDKs/APIs, and the synthetic patient records come from
  the open-source **Synthea** generator. These are external tools and datasets, not our own
  prior work.

If anything else in our submission warrants a reuse disclosure, we'll add it here.
