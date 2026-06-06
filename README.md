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
