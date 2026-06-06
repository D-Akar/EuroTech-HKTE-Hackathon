# Clinician-Ready Patient PDF Report — Design

**Date:** 2026-06-06
**Status:** Approved design, pending implementation plan

## Goal

Give a practice a downloadable, clinician-ready PDF for any patient that contains:

1. Short summaries of the latest "appointments" (the daily phone check-in calls).
2. How the patient's health status has been developing over the recent window.

For now this is a **mock**: the summary narrative and trend wording are rule-based
(deterministic), computed from the existing in-memory data. The summary generation is
isolated behind a seam so it can later be replaced by real data and/or an LLM-written
narrative without touching the PDF renderer or the endpoint.

## Scope decisions

- **Generation location:** backend. A FastAPI route builds and streams the PDF. The
  frontend just links to it.
- **"Appointments" maps to:** the existing daily check-in calls (`CheckIn`). No new
  entity, no schema change.
- **Rendering library:** `reportlab` (pure-pip, works on Windows 11 / PowerShell, no
  system dependencies). HTML→PDF via WeasyPrint was rejected due to GTK setup friction
  on Windows.
- **Mock history window:** unchanged at `_HISTORY_DAYS = 4`. Trends are computed over
  this short window and worded as a "recent trend", not a long history. (Extending the
  window was considered and deliberately deferred.)

## Architecture

```
Frontend (PatientDetail)                 Backend (FastAPI)
  "Download clinician report"  ──GET──▶  /patients/{id}/report.pdf
                               ◀─PDF──    routers/reports.py
                                             │
                                             ├─ data.py            (patient, check-ins, wearables)
                                             ├─ report_summary.py  (data → narrative + trends; the mock "brain")
                                             └─ report_pdf.py      (patient + summary + data → PDF bytes via reportlab)
```

### New modules

| Module | Responsibility | Depends on | Tested how |
|---|---|---|---|
| `backend/app/report_summary.py` | Pure functions: turn check-ins + wearables into a `ReportSummary` (narrative strings + computed trends). Deterministic. No I/O, no reportlab. | `models` only | Unit tests on trend direction + narrative thresholds with synthetic input |
| `backend/app/report_pdf.py` | `build_report_pdf(patient, summary, checkins, wearables) -> bytes`. Lays out the document with reportlab. No data access, no business logic. | `reportlab`, `models` | Smoke test: returns non-empty bytes starting with `%PDF` |
| `backend/app/routers/reports.py` | `GET /patients/{id}/report.pdf`. Loads data, calls summary + pdf, returns `Response(content=..., media_type="application/pdf")` with a download filename. 404 if patient missing. | `data`, `report_summary`, `report_pdf` | Endpoint test |

Wiring: register the router in `app/main.py` alongside the existing routers. Add
`reportlab` to `backend/requirements.txt`.

### Data shapes (in `report_summary.py`)

```python
class Trend(BaseModel):
    label: str            # e.g. "Pain level"
    current: float        # latest value
    direction: Literal["improving", "worsening", "stable"]
    arrow: str            # "↓" / "↑" / "→" (mapped for clinical sense per metric)
    series: list[float]   # the ~4 points, oldest→newest, for the mini chart

class ReportSummary(BaseModel):
    checkins_narrative: str   # 1–2 sentences on the recent check-ins
    status_narrative: str     # 1–2 sentences on the overall trend
    trends: list[Trend]       # pain, heart rate, sleep, steps, answer-rate
```

Direction is decided by comparing the oldest vs newest value (and/or simple slope) of
each metric against a small threshold. Per-metric polarity is handled so the wording is
clinically correct (e.g. rising pain = "worsening", rising sleep = "improving").

## PDF content layout

Single page (overflowing to a second if needed), top to bottom:

1. **Header** — patient name; age · district · practice; status (colorblind-safe color
   **and** text label, per the product's accessibility direction); report date.
2. **Latest check-ins** — the `checkins_narrative` paragraph, then a table of the most
   recent check-ins (date, answered?, mood, pain 0–10, notes).
3. **Health status — recent trend** — the `status_narrative` paragraph, then per-metric
   rows (pain, heart rate, sleep, steps, answer-rate) each showing current value, the
   direction arrow + label, and a small reportlab line chart of `series`.
4. **At-a-glance vitals** — latest heart rate / steps / sleep.
5. **Footer** — "Generated mock report — not for clinical use." + generation timestamp.

## Frontend integration

- `client.ts`: add `reportUrl(patientId) => \`${BASE_URL}/patients/${patientId}/report.pdf\``.
- `PatientDetail.tsx`: a "Download clinician report" button in the detail header that
  opens `api.reportUrl(patient.id)` in a new tab (browser handles the download).
  Minimal styling consistent with existing buttons.

## Testing

`pytest` (backend):

- `report_summary`: feed synthetic check-ins/wearables with known shapes; assert each
  `Trend.direction`/`arrow` and that narrative strings reflect the thresholds.
- `report_pdf`: `build_report_pdf(...)` returns non-empty `bytes` starting with `b"%PDF"`.
- endpoint: `GET /patients/1/report.pdf` → 200, `content-type: application/pdf`, body
  starts with `%PDF`; unknown id → 404.

## Out of scope (future)

- Real EHR/appointment data and a real `Appointment` entity.
- LLM-generated narrative (the `report_summary` seam is where it plugs in).
- Longer history window / richer charts.
- Auth on the report endpoint.
```
