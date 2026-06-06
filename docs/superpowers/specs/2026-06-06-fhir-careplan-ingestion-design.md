# FHIR Care Plan Ingestion — Design

**Date:** 2026-06-06
**Status:** Approved (design)

## Goal

Let a practice upload a patient's care plan in [FHIR CarePlan](https://hl7.org/fhir/careplan.profile.json.html)
format and turn it into a human-readable piece of context — **primarily so the
ElevenLabs check-in agent can reference the plan during calls with the patient.**
It also appears in the clinician PDF report and is retrievable via API.

## Scope decisions (from brainstorming)

- **Surfacing:** (1) agent call context, (2) clinician PDF report, (3) a GET API
  endpoint. **No** new dashboard *display* view — but the dashboard does get an
  *upload control*.
- **Patient linkage:** clinician uploads against a chosen patient from the dashboard
  (explicit `patient_id`); a no-id endpoint auto-matches by FHIR `CarePlan.subject`.
- **Input formats:** FHIR JSON resource, FHIR JSON Bundle, FHIR XML, and raw pasted
  text/content.
- **Storage:** in-memory now, behind a functional interface so it can swap to the
  existing MongoDB later without touching callers.
- **Conversion:** deterministic field extraction → prose. No LLM call.

## Parsing approach (chosen: "normalize-to-dict")

Parse JSON with `json.loads`; parse XML with stdlib `xml.etree.ElementTree`, collapsing
FHIR's `<status value="active"/>` attribute convention into the **same dict shape** JSON
uses. Then a single extractor reads the human-relevant fields from that dict, regardless
of source format. No heavy FHIR dependency; full control over the rendered prose. This is
the only approach that cleanly gives "one extractor, four input forms."

Rejected: `fhir.resources` — large dependency, strict validation rejects slightly-off
real-world docs, and it does not parse XML anyway.

## Architecture

All new backend modules are small and single-purpose, mirroring existing patterns
(`call_store.py`, `report_summary.py`, `services/patient_context.py`).

### New modules

**`app/fhir_careplan.py`** — pure parsing/extraction, no I/O:

- `parse_document(raw: str) -> dict`
  Sniff JSON (leading `{`/`[`) vs XML (leading `<`), parse, and for XML normalize the
  `@value` attribute convention into JSON-shaped values. Raises `CarePlanParseError` on
  unparseable input.
- `locate_care_plan(resource: dict) -> tuple[dict, dict]`
  If `resourceType == "Bundle"`, find the `CarePlan` entry and build a reference lookup
  (`{"Goal/123": {...}}`) from the bundle's other entries for dereferencing. If it's
  already a `CarePlan`, return it with an empty lookup. Contained resources
  (`CarePlan.contained[]`) are added to the lookup too. Raises `CarePlanParseError` if no
  CarePlan is found.
- `extract_care_plan(care_plan: dict, refs: dict) -> CarePlanContext`
  Pull and shape the fields below, dereferencing goals/activities via `refs`.
- `render_care_plan_text(ctx: CarePlanContext) -> str`
  Deterministic prose block. Omits any section whose data is absent.

Fields extracted (FHIR R4/R5, tolerant of both):

| Field | Source | Notes |
|-------|--------|-------|
| `status` | `CarePlan.status` | e.g. active, draft, completed |
| `intent` | `CarePlan.intent` | e.g. plan, order |
| `title` | `CarePlan.title` | falls back to category text |
| `description` | `CarePlan.description` | |
| `period_start`/`period_end` | `CarePlan.period` | ISO dates |
| `categories` | `CarePlan.category[].text` / coding display | |
| `subject_display` | `CarePlan.subject.display` / `.reference` | used for auto-match |
| `addresses` | `CarePlan.addresses` → Condition text, or inline CodeableConcept | conditions the plan targets |
| `goals` | `CarePlan.goal[]` → `Goal.description.text` (+ target) | dereferenced via `refs`; bare references show their display if present |
| `activities` | `CarePlan.activity[]` | `detail.code.text`/`detail.description`, `detail.status`, scheduled timing/period; R5 `plannedActivityReference` dereferenced via `refs` |
| `notes` | `CarePlan.note[].text` | |

**`app/care_plan_store.py`** — in-memory store, Mongo-ready interface:

- Internal `_STORE: dict[int, StoredCarePlan]` keyed by `patient_id`.
- `get(patient_id) -> StoredCarePlan | None`, `set(patient_id, raw, ctx) -> StoredCarePlan`,
  `delete(patient_id) -> bool`.
- `StoredCarePlan` holds the parsed `CarePlanContext`, the raw document string, and
  `uploaded_at`. Callers only touch these three functions, so internals can later become
  MongoDB reads/writes.

### Model additions (`app/models.py`)

- `CarePlanGoal(description: str, target: str | None)`
- `CarePlanActivity(description: str, status: str | None, scheduled: str | None)`
- `CarePlanContext` with the extracted fields above plus `rendered_text: str`.
- `StoredCarePlan(care_plan: CarePlanContext, raw: str, uploaded_at: datetime)`.
- Extend `PatientContextResponse` with `care_plan: CarePlanContext | None = None`.

### Wiring into existing code

- **`services/patient_context.py`**: `build_patient_context` calls
  `care_plan_store.get(patient_id)`; passes the context into the response and into
  `build_context_summary`, which appends a `Care plan:` section **only when one exists**.
  This is the core requirement — the agent now sees the plan during calls.
- **`data.py`**: add `get_patient_by_subject(display: str) -> Patient | None`, reusing
  case-insensitive name matching against `Patient.name`.
- **New router `app/routers/care_plans.py`** (registered in `main.py`):
  - `POST /patients/{patient_id}/care-plan` — raw request body (JSON/XML/pasted text);
    parse → store → return `CarePlanContext`. Browser file upload sends the file's text
    as the body, so this one raw-body endpoint covers both file and paste.
  - `POST /care-plans` — no id; parse, auto-match by subject →
    `{patient_id, care_plan}`; 422 echoing the subject display if no match.
  - `GET /patients/{patient_id}/care-plan` — stored `CarePlanContext`, or 404.
  - `DELETE /patients/{patient_id}/care-plan` — 204 / 404.
- **`report_pdf.py` + `routers/reports.py`**: `build_report_pdf` gains an optional
  `care_plan: CarePlanContext | None`; the reports endpoint looks up the stored plan and
  passes it. A "Care plan" PDF section renders title/status/goals/activities when present.

### Frontend (upload control only)

- **`api/client.ts`**: `uploadCarePlan(patientId, text)` (POST raw text),
  `getCarePlan(patientId)`, `deleteCarePlan(patientId)`.
- **`types.ts`**: `CarePlanContext` (+ goal/activity) mirroring the backend model.
- **`components/CarePlanPanel.tsx`** rendered inside `PatientDetail`: a file picker
  (`.json`/`.xml`) + paste `textarea` + Upload button. When a plan is attached, shows
  `Care plan attached: «title»` with a Remove button. Reads the chosen file's text
  client-side and POSTs it as the body.

## Data flow

```
Clinician (dashboard) ──file/paste──▶ POST /patients/{id}/care-plan
                                            │ raw text body
                                            ▼
                                  fhir_careplan.parse_document
                                            ▼
                                  fhir_careplan.locate_care_plan
                                            ▼
                                  fhir_careplan.extract_care_plan ──▶ CarePlanContext
                                            ▼
                                  care_plan_store.set(id, raw, ctx)

Agent call ──▶ /integrations/elevenlabs/patient-context
                    ▼
            build_patient_context ──▶ care_plan_store.get(id)
                    ▼
            build_context_summary appends "Care plan:" section ──▶ agent reads it

PDF ──▶ /patients/{id}/report.pdf ──▶ care_plan_store.get(id) ──▶ "Care plan" PDF section
```

## Error handling

- Unparseable JSON/XML → `CarePlanParseError` → HTTP 422 with a clear message.
- Bundle with no CarePlan entry → 422.
- `POST /care-plans` with no subject match → 422 echoing the subject display so the
  clinician can upload against a patient manually.
- Missing optional fields (no goals, no period, etc.) → simply omitted from the prose and
  the structured context; never an error.

## Rendered prose example

```
Care plan: "Weight management plan" (status: active, intent: plan).
Covers 2026-01-01 to 2026-06-01. Category: Weight management.
Addresses: obesity.
Goals:
- Achieve ideal body weight (target: BMI < 25).
Planned activities:
- [in-progress] Weight management classes — three times a week.
- [scheduled] Dietary consultation.
Notes: Patient is motivated to lose weight.
```

## Testing (`backend/tests/test_care_plans.py`)

A saved copy of the HL7 CarePlan example under `app/sample_data/` in JSON, a Bundle
variant, and XML. Tests:

- `parse_document` handles JSON, XML, and pasted text; raises on garbage.
- `locate_care_plan` finds the CarePlan in a Bundle and dereferences goals/activities.
- `extract_care_plan` pulls the expected fields; `render_care_plan_text` includes them
  and omits absent sections.
- `data.get_patient_by_subject` matches by name (case-insensitive) and misses cleanly.
- `care_plan_store` get/set/delete roundtrip.
- Endpoints: upload (JSON + XML + paste), get, delete, the no-id auto-match endpoint
  (match + no-match 422).
- `build_context_summary` includes the care-plan section once a plan is stored.

## Out of scope (YAGNI)

- Full FHIR validation / round-trip serialization.
- A rich dashboard care-plan *viewer* (only an upload control + "attached" status).
- LLM-written summaries.
- Versioning / history of uploaded plans (latest upload replaces the previous).
