# Product - Project LotusCare / CareLoop

## Next-Generation AI-Driven Elderly Tele-Health Platform

A two-way platform connecting outpatient elderly-care practices with their patients.
Patients get daily AI voice check-in calls (ElevenLabs + Twilio) and wear health
trackers; the platform fuses both streams into a live, city-scale overview of every
patient's wellbeing. Targeted initially at **Hong Kong and the Greater Bay Area (GBA)**,
it addresses a critical challenge in rapidly aging societies: letting elderly patients
living alone stay independent while their health is continuously, proactively monitored.

By leveraging voice over standard phone lines, the platform bypasses the digital-literacy
barriers seniors often face. It acts as a proactive health companion that conducts
regular check-ins, ingests wearable health data, and surfaces actionable, real-time
insight to clinicians through a dedicated dashboard.

> **Vision vs. built-today.** This document describes the **product vision** and its
> **design direction**. Capabilities are tagged ✅ built / 🟡 partial / ⬜ vision to keep
> the vision honest. For the authoritative, line-by-line map of what is implemented vs.
> mocked, [`HONESTY.md`](HONESTY.md) is the source of truth; for the privacy/security
> posture see [`PRIVACY.md`](PRIVACY.md). Where any of these disagree, **`HONESTY.md` wins.**

---

## 1. Users

**Primary (operational):** Care coordinators and practice staff at outpatient
elderly-care practices. They watch over a large roster of elderly outpatients at once,
all day, and need to know at a glance who is fine, who needs a look, and who needs
someone dispatched *now*. Their job is triage and deployment: turn a flood of check-in
answers and wearable signals into the next action for the right patient.

**Secondary (demo):** Hackathon judges and prospective partners seeing this for the
first time in a short live demo. They must immediately grasp the product's ambition,
the "city-scale care command center" narrative, and feel that this is what the future
of elderly care coordination looks like.

The design is **demo-first but must read as a believable real operational tool** the
moment anyone looks past the wow factor.

---

## 2. Product Purpose & Signature Surface

The platform fuses two patient streams - AI voice check-ins and wearable telemetry -
into a live, city-scale overview of every patient's wellbeing. The signature surface is
a **digital twin of the city (Hong Kong)**: a stylized 3D cityscape where patients live
as points of light, status ripples across the map in real time, and emergencies surface
as markers a coordinator can dispatch care toward. Success = a coordinator opens it and
instantly knows where attention is needed, and a first-time viewer instantly understands
the whole product.

---

## 3. Core Product Architecture

### A. Patient-Facing Voice AI Interface

To maximize accessibility, the patient interface requires **zero smartphone literacy**.

* **Outbound automated proactive calling ✅** - the platform places a **real phone call**
  (ElevenLabs + Twilio, EU data-residency endpoint) where the AI agent speaks with the
  patient and runs their check-in.
* **Inbound daily check-ups 🟡** - an ElevenLabs inbound agent can be configured to answer
  patient call-backs to a dedicated number (setup in
  `backend/integrations/INBOUND_AGENT_SETUP.md`); it is configured at the provider, not yet
  a built-in app feature with its own logic.
* **Localized, multi-lingual speech ⬜ (vision)** - the goal is **Cantonese (with localized
  Hong Kong idioms), Mandarin, and English** STT/TTS tuned for elderly speech patterns
  (slower cadence, tremor, repetition). Today the agent uses stock ElevenLabs voices;
  there is **no custom Cantonese fine-tuning**.

### B. Context-Aware Health Intelligence Engine

The AI assistant functions as a contextual clinical-intake tool, not a linear chatbot.

* **FHIR ingestion + read surface ✅ / eHRSS integration ⬜** - the backend ingests
  **HL7 FHIR** patient records (JSON; XML for care plans) into MongoDB and exposes a
  **FHIR R4 read API** (`/fhir/metadata`, `/fhir/Patient`, `/fhir/Observation`). It is
  **FHIR-native and accreditation-ready**, but **not** integrated with Hong Kong's eHRSS -
  connection is gated behind a government accreditation scheme (see
  [`docs/hk-ehealth-market.md`](docs/hk-ehealth-market.md)).
* **Wearable / IoT telemetry ✅** - ingests biometric streams from a consumer wearable
  (Garmin): heart rate, resting HR, SpO₂, stress, sleep, respiration, body battery, and
  steps. **No blood pressure** - consumer watches have no BP sensor.
* **Long-term contextual memory 🟡** - structured long-term context (check-in history,
  active alerts, and the FHIR-ingested CarePlan + profile) is injected into each call so
  the agent can relate today's readings to past events. This is **structured context, not
  a vector-database memory** - semantic/vector recall is a ⬜ roadmap item.

### C. Clinician & Caregiver Portal

The frontend is built for elderly-care homes, community nurses, and clinicians. It turns
raw voice check-ins into structured, reviewable data:

* **Daily input summaries ✅** - LLM-generated clinical notes from the call (via the
  Gemma/Gemini API; best-effort, needs a key) highlighting symptoms, adherence, and mood.
* **Real-time triage & alerting dashboard ✅** - rule-based alerts combine wearable
  readings and vitals into severity-tagged risk flags; a React Hong Kong digital-twin map
  + roster updates live over **Server-Sent Events**, recoloring patients the instant a
  status changes.
* **Live mid-call escalation ✅** - the agent's "escalate" tool-call flips a patient to
  *urgent*, recolors every open dashboard over SSE, and places a nurse-alert call.
* **Explainable review 🟡 → ⬜** - call transcripts and the structured check-in are pulled
  from ElevenLabs and are **clinician-reviewable** today. **Clickable citations linking a
  summary line to the specific transcript timestamp** are a ⬜ roadmap item.

---

## 4. Market Alignment: Hong Kong & the Greater Bay Area

| Market challenge | LotusCare direction | Status |
| --- | --- | --- |
| High prevalence of elderly speaking only Cantonese / regional dialects | Native Cantonese understanding with hyper-localized colloquial speech | ⬜ Vision (stock voices today) |
| HK citizens retiring in the GBA needing continuity of care | Cloud architecture to sync data between GBA care homes and HK clinical hubs | ⬜ Vision |
| Severe nursing / caretaking staff shortage in Hong Kong | AI automates routine check-ins so staff focus on high-risk alerts | ✅ Core loop built |

---

## 5. Regulatory Compliance & Data Governance

Operating in Hong Kong with sensitive biomedical data requires strict adherence to
regional frameworks. The controls below are **implemented but config-gated and OFF by
default** in the demo (see [`PRIVACY.md`](PRIVACY.md) §8/§11); they enforce for real when
the `CARELOOP_*` env flags are set.

* **PDPO alignment** - designed against the **Personal Data (Privacy) Ordinance
  (Cap. 486)**. **AES-256-GCM encryption at rest** and **enforced HTTPS/HSTS in transit**
  are implemented and config-gated (TLS itself is terminated by the deployment proxy).
  🟡 Implemented, default OFF.
* **Local data residency** - the target is HK-region hosting so health data does not cross
  unauthorized borders; the code is region-agnostic via `CARELOOP_DATA_RESIDENCY`, but
  today it runs locally via Docker. ⬜ Hosting decision, not yet done.
* **eHRSS compatibility** - designed to align with the eHRSS Technical Standards for
  Interoperability (FHIR-native, accreditation-ready). ⬜ Not integrated.

---

## 6. Implementation & Ease-of-Adoption Strategy

A frictionless onboarding blueprint for fragmented care homes and public-health sectors:

1. **For the elderly (zero setup) - partly built.** No app to download and the AI works
   over a standard phone line ✅. The vision of wearables shipping **pre-configured with
   cellular IoT e-SIMs** (no Bluetooth pairing by the senior) is ⬜ roadmap.
2. **For care facilities (modular, API-first) - vision.** A modular frontend that runs
   standalone or embeds into existing Care Home Management Systems via webhooks / iframe
   micro-frontends. ⬜ Roadmap.
3. **Clinician trust (explainable AI) - partly built.** Clinician-reviewable transcripts
   and source-cited extracted data exist today ✅; **clickable per-line citations to the
   exact transcript timestamp** are ⬜ roadmap.

---

## 7. Brand Personality

Futuristic, alive, reassuring. Three words: **luminous, vigilant, calm**. The voice is
competent and quiet, never alarmist. The interface feels like a living system keeping
watch over real people, so its confidence comes from precision and responsiveness, not
from shouting. Calm is the resting state; intensity is reserved for the moment a real
person genuinely needs help, and then it is unmistakable.

---

## 8. Anti-references

- **Generic SaaS dashboard**: identical card grids, hero-metric tiles, KPI boxes with a
  gradient accent. This is a living map, not a metrics report.
- **Alarming "all-red medical" UI**: blood-red everywhere, crisis-by-default. We are
  watching grandparents; the default state must feel safe, not like an ER monitor.
- **Sterile EHR / hospital software**: gray forms, dense clinical tables, cognitive
  overload. Trust here comes from clarity and life, not institutional grayness.
- **Cliché sci-fi neon-on-black "crypto/gamer" look**: pure black backgrounds, garish
  full-saturation neon, HUD clutter for decoration. Futuristic must stay humane and
  legible, not a video-game overlay.

---

## 9. Design Principles

1. **The city is alive, the patients are people.** The twin breathes and responds, but
   every point of light is a named human being one click from full context. Never let the
   spectacle abstract the patient away.
2. **Calm until it counts.** Stable is the quiet default; the UI spends its visual energy
   only where a real need exists. Emergencies earn motion, brightness, and focus; nothing
   else competes for them.
3. **Glance, then drill.** The twin answers "where do I look?" in one second; the
   list/timeline answers "what exactly is happening, and what do I do?" Both must be
   first-class, with a fluid path from the map to one patient's full story.
4. **Earn the future.** Depth, light, and motion must mean something (status, recency,
   urgency, location), never decorate. If an effect doesn't encode information, cut it.
5. **Trust through precision.** Reassurance is delivered by accuracy and responsiveness,
   not soft pastels. The system feels safe because it is clearly, competently watching.

---

## 10. Accessibility & Inclusion

- **WCAG AA contrast** for all text and status indicators, including over the 3D canvas
  (status markers and labels must stay legible against a busy/animated background).
- **Colorblind-safe status**: stable / attention / urgent must never rely on color alone.
  Pair every status with shape, icon, label, and/or motion so it survives any color-vision
  deficiency and any monochrome screen.
- Honor `prefers-reduced-motion`: the "living" map and emergency animations need a calm,
  static-but-still-legible fallback (good practice even though not explicitly required).
- The 3D twin must never be the *only* way to reach information; the list and timeline
  provide a complete, non-spatial path to every patient and action.
</content>
</invoke>
