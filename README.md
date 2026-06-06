# Elderly Care Platform

A two-way platform connecting outpatient elderly-care practices with their patients.
Patients receive **daily phone-call check-ins** about their health; combined with
**wearable health data**, this is surfaced to practices as a **health timeline** per
patient.

> This repo is currently an early scaffold: a React dashboard and a FastAPI backend
> serving mock data. See `docs/superpowers/specs/` for the design.

## Structure

```
backend/    FastAPI wireframe — patients, check-ins, wearable readings (in-memory mock data)
frontend/   React + Vite + TypeScript dashboard
docs/       Design specs
```

## Running it

The app has **two halves that run at the same time**, so you need **two terminals** —
one for the backend, one for the frontend.

> **Windows / PowerShell note:** PowerShell 5.1 does not support `&&` to chain commands.
> Run each line separately, or use `;`. Commands below are written for PowerShell.

### 1. Backend (FastAPI, port 8000)

```powershell
cd backend
.venv\Scripts\activate
uvicorn app.main:app --reload
```

- API root: http://localhost:8000
- Interactive docs: http://localhost:8000/docs

If `.venv` does **not** exist yet (fresh clone), create it once first:

```powershell
py -3.14 -m venv .venv          # use the `py` launcher, not bare `python`
.venv\Scripts\activate
pip install -r requirements.txt
```

If `.venv\Scripts\activate` errors with "cannot be loaded ... execution policy",
run this once per terminal, then re-run activate:

```powershell
Set-ExecutionPolicy -Scope Process -Bypass
```

### 2. Frontend (React + Vite, port 5173)

Open a **second** terminal:

```powershell
cd frontend
npm run dev
```

If `node_modules` does not exist yet (fresh clone), run `npm install` once first.

Open http://localhost:5173. The dashboard expects the backend on port 8000 (override
with `VITE_API_URL` — see `frontend/.env.example`).

### Common gotchas

- **`The token '&&' is not a valid statement separator`** — you're on PowerShell 5.1;
  run the commands on separate lines instead of joining with `&&`.
- **`Unable to copy ...venvlauncher.exe to ...python.exe`** — the `.venv` already exists
  and was locked (a running server, editor, or antivirus). Don't recreate it; just
  activate it. To rebuild from scratch, close everything using it, then
  `Remove-Item -Recurse -Force .venv` and recreate.
- **Bare `python` opens the Microsoft Store** — the `python` command can resolve to a
  Store stub. Prefer the `py` launcher (`py -3.14 ...`) for venv creation.

## API endpoints

| Method | Path                              | Description                     |
| ------ | --------------------------------- | ------------------------------- |
| GET    | `/health`                         | Liveness check                  |
| GET    | `/patients`                       | List all patients with status   |
| GET    | `/patients/{id}`                  | Single patient detail           |
| GET    | `/patients/{id}/checkins`         | Daily check-in history          |
| GET    | `/patients/{id}/wearables`        | Wearable readings (daily)       |
| GET    | `/patients/{id}/vitals`           | Rich Garmin vitals (stress, SpO2, etc.) |
| POST   | `/patients/{id}/calls/trigger`    | Place an instant check-in call  |
| GET    | `/patients/{id}/calls`            | Call history                    |
| GET/PUT| `/patients/{id}/calls/config`     | Read/update the questions asked  |
| POST   | `/patients/{id}/calls/schedules`  | Schedule a call (one-off/daily) |
| GET    | `/patients/{id}/calls/schedules`  | List upcoming schedules         |
| DELETE | `/patients/{id}/calls/schedules/{sid}` | Cancel a schedule          |

## Real Garmin wearable data (patient 5)

Patient id 5 ("Dario Monopoli - live Garmin") is backed by real data pulled from a Garmin
account, not mock seed data. It shows the wearable pipeline working end to end. The four
elderly patients above stay mock.

How it fits together:

- Extraction: `backend/garmin_pipeline/` pulls vitals from Garmin (heart rate, resting HR,
  stress, sleep, SpO2, respiration, body battery, steps) and exports them as sample dicts.
  Needs `pip install garminconnect curl_cffi` and the account owner's own login.
- Serving: `app/wearable_source.py` aggregates those sample dicts per day into the existing
  `WearableReading` model, so `GET /patients/5/wearables` returns real daily vitals with no
  frontend change. The richer per-reading data is at `GET /patients/5/vitals?kind=<kind>`
  (e.g. `stress`, `spo2`, `sleep_stage`), in the same sample-dict shape used for FHIR mapping.
- Data source: it reads `$GARMIN_SAMPLES` if set, otherwise `backend/data/garmin_samples.json`
  (the real export, gitignored so the data stays local), otherwise
  `backend/app/sample_data/garmin_fallback.json` (a committed synthetic file, source
  "synthetic", so a fresh clone still has data to show).

Refresh the real data (on the machine with the Garmin login):

```bash
cd backend
python -m garmin_pipeline.cli login            # once; enter the emailed code if asked
python -m garmin_pipeline.cli backfill --days 30
python -m garmin_pipeline.cli export --out data/garmin_samples.json
# restart the backend to pick it up
```

Blood pressure is not included: Garmin watches have no blood-pressure sensor.

## Outbound check-in calls (ElevenLabs + Twilio)

Practices can trigger an **AI voice check-in call** to a patient — instantly ("Call now"),
once at a chosen time, or repeating daily. Each call carries the patient's recent context
(last few check-ins + latest wearable reading) and the practice's configured questions.
Calls are placed via the ElevenLabs Twilio integration on the **EU data-residency**
endpoint (`POST https://api.eu.residency.elevenlabs.io/v1/convai/twilio/outbound-call`).

**Setup:**

1. Copy `backend/.env.example` to `backend/.env` and fill in:
   `ELEVENLABS_API_KEY`, `ELEVENLABS_AGENT_ID`, `ELEVENLABS_AGENT_PHONE_NUMBER_ID`
   (and optionally `TWILIO_API_KEY`).
2. Context is injected as ElevenLabs **dynamic variables**, so the agent's prompt in the
   ElevenLabs dashboard **must reference** these placeholders, or calls go out context-less:
   `{{patient_name}}`, `{{patient_age}}`, `{{recent_summary}}`, `{{questions}}`.
3. To demo, set a patient's "To number" (in the dashboard's call panel) to your own phone.

Schedules and call history are in-memory and reset when the backend restarts.

## Tests

```bash
cd backend
.venv\Scripts\activate
pip install pytest httpx
pytest
```

## Not yet built (planned)

Practices entity, authentication, a real database, write endpoints, and real
telephony / wearable-device integrations.
