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

You need **two terminals** — one for each half.

### 1. Backend (FastAPI, port 8000)

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate          # Windows (use: source .venv/bin/activate on macOS/Linux)
pip install -r requirements.txt
uvicorn app.main:app --reload
```

- API root: http://localhost:8000
- Interactive docs: http://localhost:8000/docs

### 2. Frontend (React + Vite, port 5173)

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173. The dashboard expects the backend on port 8000 (override
with `VITE_API_URL` — see `frontend/.env.example`).

## API endpoints

| Method | Path                              | Description                     |
| ------ | --------------------------------- | ------------------------------- |
| GET    | `/health`                         | Liveness check                  |
| GET    | `/patients`                       | List all patients with status   |
| GET    | `/patients/{id}`                  | Single patient detail           |
| GET    | `/patients/{id}/checkins`         | Daily check-in history          |
| GET    | `/patients/{id}/wearables`        | Wearable readings               |

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
