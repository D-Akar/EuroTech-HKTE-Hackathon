# Data Breach Response Runbook

> Organizational incident process for a suspected or confirmed personal-data
> breach affecting CareLoop patient data. Pairs with the technical controls in
> [`PRIVACY.md`](../PRIVACY.md) §8 (the audit log is the forensic foundation) and
> the honest-status map in [`HONESTY.md`](../HONESTY.md).
>
> **Status:** organizational procedure (document). It does not run itself - it is
> the playbook the on-call team follows. Notification *timeframes* below are the
> regulatory targets CareLoop commits to meeting.

---

## 0. What counts as a breach

Any unauthorised or accidental **access, disclosure, loss, alteration, or
destruction** of patient personal data - including health (special-category) data:
voice recordings/transcripts, wearable vitals, clinical records, demographics, or
consent records. Examples: a leaked `CARELOOP_DATA_KEY`, an exposed MongoDB
instance, a misdirected data export, a compromised auth/integration token, or a
sub-processor (ElevenLabs, Twilio, Garmin, MongoDB host, LLM provider) notifying us
of an incident on their side.

When in doubt, treat it as a breach and start this runbook. Under-reacting is the
costlier error.

## 1. Roles

| Role | Responsibility |
|---|---|
| **Incident Lead** | Owns the response end-to-end; makes the notification call. |
| **Technical Lead** | Contains and investigates; pulls audit-log evidence. |
| **Privacy/Legal contact** | Assesses notification duties per jurisdiction; drafts notices. |
| **Comms contact** | Communicates with affected patients/caregivers and the practice. |

For the hackathon team these may be the same people; name them before go-live.

## 2. The clock

Two regulatory deadlines drive the timeline. **Start the clock at the moment of
awareness**, not confirmation.

| Regime | Notify the regulator | Notify individuals |
|---|---|---|
| **GDPR** (EU patients) | Supervisory authority **within 72 hours** of becoming aware, where there is a risk to individuals. | "Without undue delay" when **high risk**. |
| **PDPO** (HK patients) | PCPD notification is **recommended** (not strictly mandatory); do it promptly for any material breach. | Affected individuals, as soon as practicable. |
| **PIPL** (GBA/Mainland data) | Authority + individuals promptly per PIPL Art.57. | Promptly, with remedial steps. |

Regulator contacts: **HK PCPD** (Office of the Privacy Commissioner for Personal
Data); the relevant **EU lead supervisory authority** for EU data subjects.

## 3. Procedure

**1 - Detect & record (immediately).**
Log the time of awareness, who reported it, and what is known. Open an incident
record. Preserve evidence: snapshot the [audit log](../PRIVACY.md#8-security-architecture)
(`GET /audit`, admin) and relevant server logs before any change.

**2 - Contain (within hours).**
Stop the bleeding: rotate the exposed secret (`CARELOOP_DATA_KEY`, auth tokens,
`CARELOOP_TOOL_API_KEYS`/`ELEVENLABS_TOOL_API_KEY`), revoke compromised tokens,
take the affected surface offline, or close the open port. Confirm encryption at
rest (`CARELOOP_ENCRYPT_AT_REST`) status - encrypted-at-rest data with an
uncompromised key materially lowers the risk assessment.

**3 - Assess scope & risk.**
Using the audit log, determine **which patients**, **which data categories**
(§3 of PRIVACY.md), and **how many records**. Health data is special-category →
default to *high risk* unless strong mitigation (e.g. data was encrypted and the
key was not exposed) shows otherwise.

**4 - Notify.**
On the §2 timelines: regulator first where required, then affected individuals when
the risk threshold is met. Notices state, in plain language: what happened, what
data, likely consequences, what we have done, and what the person can do. Route
patient/caregiver comms through the Comms contact.

**5 - Eradicate & recover.**
Remove the root cause, restore from clean state, verify the fix, and confirm
controls are back on (`CARELOOP_AUTH_ENABLED`, `CARELOOP_FORCE_HTTPS`,
`CARELOOP_ENCRYPT_AT_REST`).

**6 - Post-incident review.**
Within ~2 weeks: timeline, root cause, what worked, and concrete preventive
actions (with owners). Update this runbook and the controls accordingly.

## 4. Pre-breach checklist (reduce blast radius now)

- [ ] Encryption at rest **on** in production (`CARELOOP_ENCRYPT_AT_REST=1`) with a
      KMS-sourced key, so a store leak does not expose plaintext.
- [ ] Auth + RBAC **on** (`CARELOOP_AUTH_ENABLED=1`); least-privilege tokens.
- [ ] Per-client integration keys (`CARELOOP_TOOL_API_KEYS`) so one leaked key is
      scoped and individually revocable.
- [ ] Audit log retained long enough for forensics (`CARELOOP_RETENTION_AUDIT_DAYS`).
- [ ] Sub-processor breach-notification contacts on file (DPAs in place).
- [ ] Named Incident Lead + Privacy/Legal contact, with the regulator contact
      details to hand.
