# Elderly Care Platform — Scaffold Design

**Date:** 2026-06-06
**Status:** Approved

## Purpose

A two-way platform connecting outpatient elderly-care practices with their patients.
Patients receive daily phone-call check-ins about their health; this is combined with
wearable health data and surfaced to practices as a health timeline per patient.

This document covers the **initial scaffold only**: a basic React dashboard and a
FastAPI backend wireframe with mock data. It is a demo skeleton, not production.

## Scope

In scope:
- FastAPI backend serving JSON from in-memory mock data (read-only endpoints).
- React + Vite + TypeScript dashboard visualizing patients and their health timeline.
- Three entities: Patient, CheckIn, WearableReading.

Out of scope (noted for later):
- Practices entity, authentication, persistence / database, write endpoints.
- Real telephony integration and real wearable-device integration.

## Repo Layout

```
backend/
  app/
    main.py              app factory, CORS, router mounting
    models.py            Pydantic schemas (Patient, CheckIn, WearableReading)
    data.py              in-memory mock dataset (sample patients + history)
    routers/
      patients.py        GET /patients, GET /patients/{id}
      checkins.py        GET /patients/{id}/checkins
      wearables.py       GET /patients/{id}/wearables
  requirements.txt
frontend/
  src/
    api/client.ts        typed fetch wrapper to backend
    types.ts             shared TS types mirroring backend models
    components/          PatientList, PatientDetail, HealthTimeline, StatusBadge
    App.tsx              dashboard shell
  package.json, vite config, etc.
README.md                run instructions for both halves
```

## Data Model (mock)

- **Patient** — id, name, age, status (`stable` | `attention` | `urgent`), practice name.
- **CheckIn** — id, patient_id, date, mood, pain_level, answered (bool), notes.
- **WearableReading** — id, patient_id, timestamp, heart_rate, steps, sleep_hours.

Seed data: ~4 sample patients, each with a few days of check-ins and wearable readings
so the timeline looks realistic.

## Backend

FastAPI app. CORS open to the Vite dev server. Read-only endpoints per entity. Data
lives in `data.py` as Python lists seeded at import time.

Endpoints:
- `GET /patients` — list all patients with current status.
- `GET /patients/{id}` — single patient detail.
- `GET /patients/{id}/checkins` — check-in history for a patient.
- `GET /patients/{id}/wearables` — wearable readings for a patient.
- `GET /health` — liveness check.

## Frontend

Two-pane dashboard:
- Left: patient list with color-coded status badges.
- Right: selected patient's health timeline (check-ins + wearable readings merged
  chronologically) plus latest-vitals summary cards.

Plain CSS, no UI component library, to stay lightweight.

## Testing

Scaffold-level only: a smoke test that the FastAPI app starts and `/patients`
returns the seeded list. Frontend verified by running the dev server against the API.
