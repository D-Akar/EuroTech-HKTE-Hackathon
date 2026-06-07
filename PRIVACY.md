# Privacy & Data Protection

How **CareLoop** (the elderly-care platform in this repo) protects patient data and
how it is designed to comply with the data-protection regimes of the markets it
targets: the **EU (GDPR)**, **Hong Kong (PDPO)**, and the wider **Greater Bay Area /
Mainland China (PIPL)** — with first-class alignment to Hong Kong's **eHRSS /
eHealth+** health-record-sharing ecosystem.

Data protection is the platform's **number-one design priority**: we handle the
voice, vitals, and clinical records of vulnerable elderly people, and the trust of
patients, families, and clinicians depends entirely on getting this right.

> ### Honesty note (read this first)
> CareLoop is an early hackathon scaffold. This document describes both **what is
> implemented today** and **the target compliance architecture we are building
> toward** — and it labels every control with which it is. It is a *privacy-by-design*
> blueprint, not a certification claim. For the authoritative, line-by-line map of
> what is real vs. mocked, see [`HONESTY.md`](HONESTY.md); for the Hong Kong eHealth
> regulatory and market context, see [`docs/hk-ehealth-market.md`](docs/hk-ehealth-market.md).
> Where the two ever disagree, **`HONESTY.md` wins.**

**Status legend used throughout:**

| Marker | Meaning |
|---|---|
| ✅ **Implemented** | Working in the current codebase today |
| 🟡 **Partial** | Foundations exist; not yet a complete control |
| ⬜ **Planned** | Design target / roadmap — not yet in code |

---

## 1. Principles

1. **Data minimisation.** Collect only what triage and care provision require
   (e.g. heart rate, SpO₂, sleep, the answers to a check-in), never ambient or
   incidental data "just in case."
2. **Purpose limitation.** Patient data is used **only** to deliver and coordinate
   care. No marketing, no insurance profiling, no secondary use without explicit,
   revocable opt-in consent.
3. **Consent before capture.** No check-in proceeds until the patient has explicitly
   consented to the call being recorded and their data processed (see §7).
4. **Security in depth.** Encryption in transit and at rest, least-privilege access,
   and auditable trails are the default, not an add-on.
5. **Locality of data.** Health data should rest in the patient's own jurisdiction
   (Hong Kong for HK patients; EU for EU patients) and move across borders only under
   a lawful transfer mechanism.
6. **Transparency & control.** Patients and their authorised caregivers can see what
   we hold, correct it, export it, and ask for its deletion.
7. **Interoperate, don't hoard.** Where a government health-record system exists
   (eHRSS), integrate into it through its own accredited, secure channels rather than
   building a competing data silo (see §6).

---

## 2. Regulatory landscape

CareLoop is designed to satisfy the **strictest applicable** requirement across all
target jurisdictions, so a single architecture stays compliant everywhere.

| Regime | Jurisdiction | What it governs for us |
|---|---|---|
| **PDPO** — Personal Data (Privacy) Ordinance (Cap. 486) | Hong Kong | The six Data Protection Principles (DPPs); the primary regime for HK patients. See §4. |
| **GDPR** — General Data Protection Regulation | EU / EEA | Lawful basis, special-category (health) data, data-subject rights, DPIA, processor contracts. See §5. |
| **PIPL** — Personal Information Protection Law | Mainland China / Greater Bay Area | Cross-border transfer rules, separate consent for sensitive personal information, data localisation. See §5.3. |
| **eHealth/eHRSS framework** | Hong Kong | The Electronic Health Record Sharing System Ordinance + eHealth+ Connectivity & Accreditation Schemes — the secure-channel and accreditation regime for sharing records. See §6. |
| **Sector context** | Hong Kong | Chronic Disease Co-Care (CDCC) and the Primary Healthcare Co-care Network — programmes our wearable + check-in feed is designed to serve. |

Health data is **special-category data under GDPR (Art. 9)** and **sensitive personal
information under PIPL** — the highest-protection tier in every regime. We treat *all*
patient data, including voice recordings and wearable telemetry, at that tier.

---

## 3. What data we handle

| Data category | Examples | Source | Sensitivity |
|---|---|---|---|
| **Identity & demographics** | Name, age, district, phone number, FHIR id | Practice registry / FHIR record | Personal |
| **Wearable telemetry** | Heart rate, resting HR, SpO₂, sleep, stress, respiration, steps | Garmin device | Health (special category) |
| **Voice check-ins** | Call audio, transcript, extracted mood/pain/notes | ElevenLabs + Twilio call | Health (special category) |
| **Clinical records** | Conditions, medications, allergies, procedures, CarePlan | FHIR ingest → MongoDB | Health (special category) |
| **Derived signals** | Triage alerts, worsening-symptom flags, generated questions | Computed on-platform / LLM | Health (special category) |
| **Operational** | Call history, schedules, consent records | Platform stores | Personal |

> **Today, no real patient data is processed.** The 555 patient records are
> **Synthea-generated synthetic data**, and the only live wearable stream is a team
> member's **own** Garmin account. This is itself a privacy control during
> development: we do not demo on, or train on, real clinical records. (See
> [`HONESTY.md`](HONESTY.md) §3–4.)

---

## 4. Hong Kong PDPO — Data Protection Principles compliance

| Principle | CareLoop implementation strategy | Status |
|---|---|---|
| **DPP 1 — Purpose & Manner of Collection** | Collect only telemetry relevant to immediate triage and care (heart rate, SpO₂, sleep, check-in answers); do **not** over-collect ambient/environment data. Collection is preceded by an explicit spoken consent gate (§7), and each decision is persisted as a consent record. | ✅ Consent gate + consent records; 🟡 minimisation by design |
| **DPP 2 — Accuracy & Retention** | Use the *explainable* architecture — clinician-reviewable transcripts and source-cited extracted data — so a clinician can correct a flawed AI assumption **before** it becomes part of the permanent health record. Per-class retention limits, purged daily and on demand (`app/retention.py`). | ✅ Retention engine (config-gated); transcript review ✅ |
| **DPP 3 — Use of Data** | Strictly restrict use to healthcare provision. **Explicitly bar** use of patient patterns for marketing or insurance profiling without separate opt-in consent. Data-use endpoints are gated on an active consent record for the requested *scope* (`app/security/consent_guard.py`), so a purpose the patient did not consent to is technically refused (451), not just policy-barred. | ✅ Consent-scope enforcement (config-gated `CARELOOP_CONSENT_ENFORCEMENT`) |
| **DPP 4 — Data Security** | AES-256-GCM at rest, enfordced TLS + HSTS in transit, strict Role-Based Access Control (RBAC), a tamper-evident audit log, and automatic session logout on the city-scale dashboard. See §8. | ✅ Encryption, RBAC, audit, transport (config-gated); ⬜ dashboard auto-logout |
| **DPP 5 — Openness & Transparency** | Maintain an accessible privacy policy (this document) describing eHRSS integration and local hosting; the voice agent reads the patient a plain-language privacy statement on request (§7). | ✅ This policy + spoken privacy response |
| **DPP 6 — Access & Correction** | A utility to **export a complete history** of a patient's data on request (`GET /patients/{id}/data-export`), **correct** it (`PATCH /patients/{id}`, audited), plus erasure (`DELETE /patients/{id}/data`) and the clinician PDF. | ✅ Full JSON export + rectification + erasure |

PDPO also requires a **data user** to notify and obtain consent for any *new* purpose.
CareLoop's consent record (§7) is the anchor for this: a purpose not covered by the
consent the patient gave cannot be applied to their data.

---

## 5. GDPR & cross-border alignment

### 5.1 Lawful basis
For EU patients, processing of health data relies on **explicit consent (Art. 9(2)(a))**
captured at the start of every call (§7), backed by **provision of healthcare
(Art. 9(2)(h))** under the care relationship. Consent is **specific, informed, and
revocable** — a patient may decline at the consent gate and the check-in does not
proceed.

### 5.2 Data-subject rights
The platform honours: **access** & **portability** (`GET /patients/{id}/data-export`
returns a full machine-readable bundle), **erasure** (`DELETE /patients/{id}/data`
removes the patient's data across every store), **rectification** (`PATCH
/patients/{id}` corrects a record, audited old→new), and consent management (§7) —
each operation RBAC-gated and written to the audit log. ✅ **Restriction/objection**
flags remain ⬜.

### 5.3 Cross-border transfers (EU ↔ HK ↔ GBA)
- **Voice processing already uses the EU data-residency endpoint** for ElevenLabs/Twilio
  (`api.eu.residency.elevenlabs.io`), keeping call audio/transcripts in-region for EU
  patients. ✅
- For **Hong Kong** patients, the target is **HK data residency** for storage and
  processing, with no routine export off-territory. ⬜
- Any **GBA / Mainland** transfer would be gated by **PIPL**: separate consent for
  sensitive personal information, a transfer mechanism (standard contract / security
  assessment), and data localisation where required. ⬜
- Inter-jurisdiction transfers default to **deny**; data follows the patient's home
  regime unless a lawful mechanism explicitly permits the move.

---

## 6. eHRSS / eHealth+ integration & secure channels

The user's request — *"integrate into the e-health system when possible and use the
same secure channels"* — is core to our strategy, stated **honestly**:

> **No third party can connect to eHRSS today.** Connection is gated behind a Hong
> Kong government **accreditation scheme**; wearable / patient-generated data is a
> *future* connectivity goal in the Primary Healthcare Blueprint. CareLoop is
> **FHIR-native and accreditation-ready, not integrated.** Do not read this section as
> "we sync with eHRSS today" — we do not.

**Our position — "the on-ramp before the highway opens":** build to the government's
own published direction now, so connecting is a conformance exercise, not a
re-architecture, the day the spec opens to systems like ours.

| Integration element | Approach | Status |
|---|---|---|
| **Record format** | FHIR **R4-native** clinical records (we ingest FHIR R4/R5 JSON & XML today) and expose a FHIR **read API** (`/fhir/metadata`, `/fhir/Patient`, `/fhir/Observation`). | ✅ Ingest + R4 read surface / ⬜ write surface |
| **Wearable → eHR** | Map device vitals to FHIR **`Observation`** resources with proper **LOINC** codes (heart rate `8867-4`, SpO₂ `59408-5`, steps, …). | ✅ LOINC `Observation` read surface / ⬜ eHR deposit |
| **Deposit channel** | Use eHRSS's own accredited interface. eHRSS integration is **HL7 v2** message-based today, with government's published roadmap **"Advancing from HL7 to FHIR"** — we build to that direction and add an HL7↔FHIR mapping layer for the deposit path. | ⬜ Planned |
| **Accreditation** | Target a tier under the **eHealth+ Connectivity Accreditation Scheme** (gold / silver / bronze) and treat its conformance spec as the security/interoperability bar. | ⬜ Roadmap milestone |
| **Funding alignment** | Position as an eligible solution under the **eHealth+ Connectivity Support Scheme** (gov funding to get private/outpatient providers depositing into eHRSS). | n/a (commercial) |
| **Secure transport** | Adopt the **same secure channel eHRSS mandates** for accredited providers (mutually-authenticated, encrypted transport per the eHealth interface spec) rather than a bespoke channel. | ⬜ Planned |

By depositing through eHRSS's accredited secure channel — instead of inventing our own
— patient data inherits the government system's vetted security and consent model, and
CareLoop becomes the **EMR-lite** that can get a solo eldercare practice onto eHRSS for
the first time. Full background: [`docs/hk-ehealth-market.md`](docs/hk-ehealth-market.md).

---

## 7. Consent & the voice-call consent gate ✅

Consent is not a checkbox buried in a portal — for elderly patients it is **spoken and
confirmed at the start of every call**, and it is **implemented in code today**.

- The outbound voice agent runs a **strict consent gate** before anything else: it asks
  the patient to confirm they agree to the call being recorded and their information
  processed per this policy, and it **will not ask any check-in question, discuss
  symptoms, or proceed in any way** until it hears a clear affirmative. (The only
  override is a described medical emergency, where patient safety comes first.)
- If the patient asks *"is my data safe?"*, *"is this recording encrypted?"*, or any
  privacy question, the agent speaks an **operator-controlled privacy statement
  verbatim**, then returns to ask for consent again — answering a privacy question is
  **not** treated as consent.
- The consent question and the privacy statement are **plain-text, operator-editable**
  files, read fresh on every call (no redeploy needed):
  [`opening_question.md`](opening_question.md) (the consent prompt) and
  [`privacy_response.md`](privacy_response.md) (the verbatim privacy statement).
- Enforced in code at the call layer in
  [`backend/app/checkin_agent.py`](backend/app/checkin_agent.py); see
  [`backend/integrations/OUTBOUND_AGENT_SETUP.md`](backend/integrations/OUTBOUND_AGENT_SETUP.md).

✅ **Consent records are persisted** (`app/consent_store.py`, `ConsentRecord`): who
consented, to what scope, by what method, when, and the **policy version** — the
durable anchor for PDPO/GDPR/PIPL. View/record via `GET|POST /patients/{id}/consent`.
✅ **Verbal consent is persisted automatically:** the voice agent calls
`POST /integrations/elevenlabs/consent` once the patient answers the opening
consent question, writing their decision as a `method="voice"` consent record
(`routers/integrations.py`) — the link between the live consent gate and the
durable store. The caregiver-portal endpoint (`POST /patients/{id}/consent`)
remains for `method="portal"`.

---

## 8. Security architecture

The controls (DPP 4 / GDPR Art. 32). Most are now implemented but **config-gated and
OFF by default** (`backend/.env`) so the open demo runs unchanged; switching them on
gives the real, enforced behaviour. See [§12 How to enable](#12-how-to-enable).

| Control | Implementation | Status |
|---|---|---|
| **Encryption at rest** | AES-256-GCM authenticated encryption of sensitive fields (check-in notes, phone numbers, call/care-plan text, consent notes, audit detail) before they reach MongoDB; fails closed if enabled without a valid key/lib (`app/security/crypto.py`) | ✅ Config-gated (`CARELOOP_ENCRYPT_AT_REST`) |
| **Encryption in transit** | HTTP→HTTPS redirect + HSTS + hardening headers (`app/security/transport.py`); TLS itself terminated by the deployment proxy/platform | ✅ Config-gated (`CARELOOP_FORCE_HTTPS`) |
| **Voice data residency** | EU-residency endpoint for ElevenLabs/Twilio | ✅ In use (`config.py`) |
| **Access control (RBAC)** | Bearer-token / API-key auth mapped to roles (coordinator < clinician < admin), least privilege via `require_role` (`app/security/auth.py`) | ✅ Config-gated (`CARELOOP_AUTH_ENABLED`) |
| **Audit logging** | Every patient-data mutation logged via middleware, plus explicit events on export/erase/consent/retention; admin-only `GET /audit` (`app/audit.py`) | ✅ Implemented |
| **Session hygiene** | Auto-logout / idle timeout on the city-scale dashboard | ⬜ Planned (frontend) |
| **Integration auth** | Server-tool callbacks authenticated by API key | ✅ Per-client rotatable keyset (`CARELOOP_TOOL_API_KEYS`), constant-time match, caller recorded in the audit log; single shared key still supported |
| **Key management** | Key from `CARELOOP_DATA_KEY`; `crypto._load_key()` is the single seam for a managed KMS | 🟡 Env key today; KMS ⬜ |
| **Data minimisation at source** | Only triage-relevant fields collected/retained | 🟡 By design; broad enforcement ⬜ |

> **Current honest state:** the controls above are real and tested, but **default to
> OFF** so the hackathon demo and existing frontend keep working without tokens or a
> key. With the env flags set they enforce for real (verified: RBAC returns 401/403,
> AES-256-GCM round-trips and fails closed on a bad key, mutations are audited).
> Still genuinely outstanding: **HK data residency** (a hosting choice), dashboard
> auto-logout, and a managed KMS. Synthetic-only data and the EU-residency voice
> channel remain in force regardless.

---

## 9. Sub-processors & data flows

Third parties that may process patient data, and what each one sees. Each must be
covered by a data-processing agreement before any real patient data flows.

| Sub-processor | Purpose | Data it sees | Residency |
|---|---|---|---|
| **ElevenLabs** (Conversational AI) | Conduct the voice check-in; transcript/analysis | Call audio, transcript, the context bundle handed at call time | **EU** data-residency endpoint ✅ |
| **Twilio** (via ElevenLabs) | PSTN telephony for the call | Phone number, call metadata | Via ElevenLabs |
| **Garmin Connect** | Wearable vitals | Device telemetry for consented patients | Garmin cloud |
| **MongoDB** | FHIR record / long-term store | Clinical records, demographics | Local (Docker) today; **HK-resident managed** ⬜ |
| **Google Gemini API (Gemma)** | Generate tailored check-in questions | Patient check-in summaries + chronic conditions | Google API |

> ⚠️ **Disclosed data flow:** check-in question generation by default sends a patient's
> recent check-in summaries and conditions to the **Gemini API**. 🟡 A switch to keep
> this in-region already exists: set `LLM_PROVIDER=vllm` (with `VLLM_BASE_URL`) to route
> generation to a **self-hosted / in-region OpenAI-compatible model** (`llm/config.py`,
> `llm/serve_vllm.sh`) so special-category data never leaves the trust boundary. The
> default remains Gemini for the demo; production should flip this switch.

---

## 10. Retention, deletion & breach response

- **Retention** ✅ — Each data class has a configurable retention period
  (`CARELOOP_RETENTION_*`); a daily scheduled job and `POST /admin/retention/run`
  purge data past its limit (`app/retention.py`). Default `0` = keep forever, so
  retention is a no-op until a practice sets real limits.
- **Deletion / erasure** ✅ — `DELETE /patients/{id}/data` deletes a patient's
  derived/stored data across every store (check-ins, calls + config + schedules,
  care plan, consent, generated questions, cached conversations, phone override) from
  both memory **and** MongoDB. It also **deletes the call recordings/transcripts at
  ElevenLabs** (the sub-processor) via the conversation API, best-effort. The patient's
  FHIR-overlaid identity/profile is redacted **and durably tombstoned**
  (`app/erasure_store.py`) so the overlay keeps the slot redacted across restarts
  (verified: a re-applied overlay leaves an erased patient as `[erased]` while other
  patients overlay normally). Subject to any statutory retention obligation in production.
  - *Honest caveat:* the synthetic record in the read-only `fhir_patients` **source**
    collection is intentionally left intact — in production the source registry / eHRSS
    is the system of record for that, not CareLoop, so erasure there is the registry's
    responsibility. ⬜
- **Breach response** 🟡 — A documented incident runbook now exists
  ([`docs/breach-runbook.md`](docs/breach-runbook.md)): roles, the **72-hour GDPR /
  PCPD notification clock**, containment (secret rotation, kill-switch), risk
  assessment, and a pre-breach checklist. The audit log (§8) is the forensic
  foundation. *Execution* is organizational (named on-call team + signed
  sub-processor DPAs), which a hackathon repo cannot itself stand up.

---

## 11. How to enable the controls

Everything in §8 is config-gated and OFF by default. To turn it on, set these in
`backend/.env` (see `backend/.env.example`) and restart the backend:

```bash
# Encryption at rest (needs `pip install cryptography`)
CARELOOP_ENCRYPT_AT_REST=1
CARELOOP_DATA_KEY=$(python -c "import secrets,base64;print(base64.b64encode(secrets.token_bytes(32)).decode())")

# Authentication + RBAC (roles: admin, clinician, coordinator)
CARELOOP_AUTH_ENABLED=1
CARELOOP_AUTH_TOKENS=supersecret-admin:admin,nurse-token:clinician,desk-token:coordinator

# Enforce HTTPS (behind a TLS-terminating proxy) + hardening headers
CARELOOP_FORCE_HTTPS=1

# Data-retention windows (days; 0 = keep forever)
CARELOOP_RETENTION_CALLS_DAYS=365
CARELOOP_RETENTION_AUDIT_DAYS=730

# Declared residency region (local | hk | eu)
CARELOOP_DATA_RESIDENCY=hk
```

With auth on, call protected endpoints with `Authorization: Bearer <token>`.

---

## 12. Roadmap to full compliance

Remaining items (data protection first), drawn from
[`docs/hk-ehealth-market.md`](docs/hk-ehealth-market.md) and [`HONESTY.md`](HONESTY.md).
Implemented: **encryption at rest, RBAC, audit log, retention engine, consent records,
consent-scope enforcement, verbal-consent webhook, data export/rectification/erasure,
per-client integration keys, transport hardening, FHIR R4 read surface, an in-region
LLM switch, and a breach-response runbook** (controls config-gated; see §8/§11).

Still outstanding — and these are the items a code repository *cannot* finish on its
own (they need hosting/procurement, a cloud service, the front end, or a government
process), which is why they remain ⬜:

1. **HK data residency** — a *hosting* decision: run MongoDB + processing in an HK
   region for HK patients (the code is already region-agnostic via
   `CARELOOP_DATA_RESIDENCY`; flip `LLM_PROVIDER=vllm` to keep generation in-region).
2. **Managed KMS** — source `CARELOOP_DATA_KEY` from a cloud KMS with rotation
   (the `crypto._load_key()` seam is ready; needs the procured KMS).
3. **Dashboard session hygiene** — idle auto-logout on the front end (deferred:
   backend-only iteration).
4. **Restriction/objection flags** — the remaining GDPR data-subject rights beyond
   access/rectification/erasure.
5. **eHRSS accreditation** — conform to the eHealth+ Connectivity spec, target a tier,
   and deposit through the mandated secure channel (§6): a Hong Kong **government**
   process, not yet open to systems like ours. Needs a FHIR R4 **write** surface +
   HL7↔FHIR mapping once the spec opens.
6. **Organizational/legal** — signed sub-processor DPAs, a named incident team, DPIA,
   and DPO appointment (the breach *runbook* exists; standing up the *team* does not).

---

*This document is a living privacy-by-design specification for a hackathon-stage
project. It states intent transparently and is cross-checked against
[`HONESTY.md`](HONESTY.md), which remains the source of truth for what is implemented.*
