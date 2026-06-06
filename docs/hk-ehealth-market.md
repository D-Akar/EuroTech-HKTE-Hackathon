# Hong Kong eHealth Market & Integration Brief

Internal reference for positioning this platform to the Hong Kong government (healthcare
track). Covers the eHRSS / eHealth+ landscape, where HL7 FHIR actually sits, the funding
vehicles, the policy hooks, and the honest gap-and-build roadmap.

> **Sourcing caveat.** The facts below were gathered from primary HK government sources
> (info.gov.hk, ehealth.gov.hk, primaryhealthcare.gov.hk, news.gov.hk) via an automated
> research pass on 2026-06-06. The pass's *verification* step did not complete (infra
> failure), so treat specific figures as **sourced but not independently re-verified** -
> **open the cited URL and confirm any number before it goes in front of officials.**

---

## TL;DR - why this is a real opportunity, not a solved problem

The HK government has **publicly named the exact gap this product fills** and is **spending
money to close it**:

- **>99% of the ~4.5 billion records in eHRSS come from *public* providers.** Private /
  outpatient contribution is minimal, and the government calls it a *"critical barrier to
  realizing the system's full potential."*
- Patient-generated and **wearable data is not yet connected** to eHRSS - the Primary
  Healthcare Blueprint lists third-party app/wearable connectivity as a *future* goal.
- Connecting a private practice is **gated behind a government accreditation scheme** -
  no third party can self-serve an eHRSS integration today.

So the honest, strong position is **"the on-ramp before the highway opens"**: build
FHIR-native and accreditation-ready now, so we're a conformance exercise away - not a
re-architecture away - the day the connectivity spec opens to systems like ours.

---

## 1. eHRSS / eHealth+ - current state & roadmap

- **eHRSS ("eHealth", 醫健通)** is the territory-wide health-record sharing system. As of
  end-Feb 2025 it covered **>80% of the population**, with **3,726 registered healthcare
  providers** and **~58,827 registered professionals** (~49% of the workforce).
  *(info.gov.hk P2025032600440)*
- **The data is lopsided toward the public sector**: >99% of the ~4.5B shared records
  originate from public providers - the private/outpatient edge barely feeds in.
  *(primaryhealthcare.gov.hk "Improve Connectivity"; SCMP 3252275)*
- **eHealth+ five-year development plan** (announced in the 2023 Policy Address) is built on
  four strategic directions: **"One Health Record, One Care Journey, One Digital Front Door
  to Empowering Tool, One Health Data Repository."** *(info.gov.hk P2025032600440)*
- The plan explicitly aims to transform eHealth **from a record-*sharing* system into a
  comprehensive integrated health-information infrastructure**, including **connectivity
  with third-party health apps and wearables** - currently a stated goal, not a built
  capability. *(primaryhealthcare.gov.hk "Improve Connectivity")*
- A **Strategic Health Service Operation Platform (SHSOP)** is being built in phases as
  part of this. *(info.gov.hk P2025040200493)*

**Takeaway for us:** we are early on the wearable/PGHD on-ramp the government has said it
wants but hasn't yet delivered. Position as a contributor to "One Health Record" and "One
Health Data Repository" from the community edge.

---

## 2. HL7 FHIR - adopted? mandated? (the honest answer)

- **eHRSS integration today is HL7 v2 message-based.** The government publishes official
  HL7 interface specifications defining how eHR data is packaged between eHealth and
  providers. **FHIR is not the mandated standard on those integration spec pages.**
  *(ehealth.gov.hk information-standards page)*
- **But the direction of travel is explicitly toward FHIR.** The HK eHealth office
  published training material titled **"Advancing from HL7 to FHIR" (2021)** - government's
  own roadmap signal. *(ehealth.gov.hk training PDF, 2021-02-02)*
- The Primary Healthcare Blueprint **does not name FHIR or any specific data-exchange
  standard** - it describes interoperability only functionally (share allergies,
  diagnoses, prescriptions). *(primaryhealthcare.gov.hk blueprint-2)*

**Positioning line (defensible):**
> "FHIR isn't our bet - it's eHealth's own published roadmap. We're building FHIR R4-native
> and aligned with where they said they're going, so we're ready when the connectivity
> accreditation spec moves to FHIR."

Do **not** claim "we sync with eHRSS via FHIR R4 today." That is currently impossible for
any third party (see §1 gating) and untrue of our code (see HONESTY.md).

---

## 3. Funding & procurement vehicles

| Vehicle | What it is | How we use it |
| --- | --- | --- |
| **eHealth+ Connectivity Support Scheme** (~Oct 2025) | Direct gov funding to get **private** providers onto accredited EMR systems that deposit into eHRSS. *(ehealth.gov.hk news_26 / connectivity-support-scheme)* | Purpose-built for what we do. Position as an eligible connectivity solution for outpatient/eldercare practices. |
| **eHealth+ Connectivity Accreditation Scheme** (tiered **gold / silver / bronze**) | Technical-conformance recognition for systems depositing eHRs. *(ehealth.gov.hk news_26)* | Name a target tier as a roadmap milestone; treat their conformance spec as the bar. |
| **Chronic Disease Co-Care (CDCC) Scheme** (regularized 2026; 200k+ enrolled by Jan 2026; ~131,200 as of 31 May 2025) | Subsidized **private**-sector screening/management of diabetes, hypertension, hyperlipidaemia for 45+. The eHealth App is the tool patients use to upload "health indexes." *(info.gov.hk P2025061100420; news.gov.hk 20260313)* | Our wearable + phone check-in **automates** the health-index feed that's manual today. |
| **Primary Healthcare Co-care Network** (launched **13 Mar 2026**; ~700k target; 5-yr phase; run by the Primary Healthcare Commission) | New large-scale primary-care network; DHC registration + eHealth enrollment **mandatory** to join. *(news.gov.hk 20260313)* | A fresh, government-run channel needing community-data tooling. |
| **HKSTP / Cyberport** | Standard healthtech incubation + access to gov pilots. **(Not re-verified this run - confirm current programs before citing.)** | Entry vehicle to land and run a DHC pilot. |

**The ask framing:** don't ask them to *buy software* - ask them to **fund a pilot that
proves private-outpatient + patient-generated/wearable data can flow into the eHRSS
pipeline.** That's the proof of the thing their own Blueprint says is missing.

---

## 4. Policy hooks (alignment surface)

- **Primary Healthcare Blueprint** - wants eHealth to become integrated infrastructure
  *including* wearables/third-party apps; mandates PHC providers use eHealth and input data
  to users' accounts. *(primaryhealthcare.gov.hk blueprint-2)*
- **District Health Centres (DHCs)** - now across **all 18 districts** with **100+ service
  points**; the standardized entry point to primary care, doing chronic-disease screening
  and family-doctor pairing, manageable via the eHealth App. **This is our deployment
  channel / pilot site.** *(news.gov.hk 20260313; info.gov.hk P2025040200493)*
- **Ageing + chronic disease + primary care** - the through-line of every recent move.
  Outpatient elderly care with daily check-ins is dead-center.
- **eHealth App = "One Digital Front Door"** - the patient-facing destination our data
  ultimately wants to surface in.

**Second value prop hiding in the data:** a 2025 study found private physicians recognize
eHRSS but participation **depends on already having an EMR system** - many small practices
don't. *(ScienceDirect S2211883725000231)* Our lightweight platform can double as the
**EMR-lite** that gets a solo eldercare GP onto eHRSS for the first time.

---

## 5. Gap & build roadmap

What's real vs. mocked in the code is tracked authoritatively in **`/HONESTY.md`**. Summary
of what real eHRSS engagement would require, beyond the current scaffold:

- **FHIR R4 read/write surface** (we ingest FHIR JSON today but expose no FHIR API).
- **Wearable → FHIR `Observation`** mapping with proper **LOINC** codes (heart rate
  `8867-4`, SpO2 `59408-5`, steps, etc.).
- **Accreditation conformance** against the eHealth+ Connectivity spec (gated, gov-issued).
- **Consent / OAuth** and a real auth layer (none today).
- **PDPO controls, encryption at rest/in transit, HK data residency** (claimed in
  PROJECT.md, not implemented in code).
- **HL7 ↔ FHIR mapping layer** for the eventual eHRSS deposit path.

**Sequencing:** the small, high-credibility demo upgrades (a real `GET /fhir/Patient/{id}`
+ `GET /fhir/Observation` emitting LOINC-coded wearable readings, a `/fhir/metadata`
CapabilityStatement) prove FHIR competence *now* without overclaiming integration. The
heavy items (accreditation, consent, PDPO, residency) are post-funding, gated on the
connectivity spec opening - exactly the roadmap a pilot grant would fund.

---

## Source list

Primary (HK government):
- https://www.ehealth.gov.hk/en/whats-new/ehealth-news/ehealth_news_26/ehealth-updates.html
- https://www.ehealth.gov.hk/en/healthcare-provider-and-professional/resources/ehealth-plus-connectivity-support-scheme/index.html
- https://www.ehealth.gov.hk/en/healthcare-provider-and-professional/resources/information-standards/information-standard-document.html
- https://www.ehealth.gov.hk/filemanager/content/pdf/common/training/2021/02/02/2021-02-02-advancing-from-hl7-to-fhir.pdf
- https://www.primaryhealthcare.gov.hk/bp/en/blueprint-2/
- https://www.primaryhealthcare.gov.hk/bp/en/supplementary-documents/improve-connectivity/
- https://www.info.gov.hk/gia/general/202503/26/P2025032600440.htm
- https://www.info.gov.hk/gia/general/202504/02/P2025040200493.htm
- https://www.info.gov.hk/gia/general/202506/11/P2025061100420.htm
- https://www.news.gov.hk/eng/2026/03/20260313/20260313_165420_787.html

Secondary / academic:
- https://www.scmp.com/news/hong-kong/health-environment/article/3252275/ (80% adoption, private-sharing gap)
- https://www.scmp.com/news/hong-kong/health-environment/article/3258116/ (connect half of private providers target)
- https://www.sciencedirect.com/science/article/abs/pii/S2211883725000231 (private physician eHRSS participation vs. EMR adoption)
- https://link.springer.com/article/10.1007/s12553-025-00977-5
