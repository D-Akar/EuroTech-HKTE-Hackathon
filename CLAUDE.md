# CLAUDE.md

Guidance for working in this repo. See `README.md` for the product overview and
`docs/superpowers/specs/` for the design.

## What this is

A two-way platform connecting outpatient elderly-care practices with their patients:
daily phone-call check-ins + wearable health data, surfaced to practices as a per-patient
health timeline. **Currently an early scaffold** — React dashboard + FastAPI backend
serving in-memory mock data. No database, auth, or write endpoints yet.

## Layout

```
backend/    FastAPI app — app/main.py (routes), app/models.py, app/data.py (mock data)
frontend/   React + Vite + TypeScript dashboard
docs/       Design specs
```

## Environment

- **OS:** Windows 11, **shell:** Windows PowerShell 5.1.
  - No `&&` chaining — run commands on separate lines or use `;`.
  - No `python -m venv ... && activate` one-liners.
- **Python:** 3.14 via the `py` launcher (`py -3.14`). Bare `python` may resolve to the
  Microsoft Store stub — avoid it for venv creation.
- **Node:** v24, npm 11.

## Running the app

Two halves, two terminals, both must run at once. The `.venv` and `node_modules` are
**already installed** — don't recreate them.

**Backend (port 8000):**
```powershell
cd backend
.venv\Scripts\activate
uvicorn app.main:app --reload
```

**Frontend (port 5173):**
```powershell
cd frontend
npm run dev
```

Dashboard: http://localhost:5173 · API docs: http://localhost:8000/docs

## Tests

```powershell
cd backend
.venv\Scripts\activate
pytest
```

`pytest`, `httpx`, `fastapi`, and `uvicorn` are already in the venv.

## Gotchas

- **`'&&' is not a valid statement separator`** → PowerShell 5.1; split the line.
- **`Unable to copy ...venvlauncher.exe`** → the `.venv` already exists and is locked.
  Don't recreate it — just activate. To rebuild: stop everything using it, then
  `Remove-Item -Recurse -Force .venv` and `py -3.14 -m venv .venv`.
- **`Activate.ps1 cannot be loaded`** → `Set-ExecutionPolicy -Scope Process -Bypass` once
  per terminal, or call the venv directly: `.venv\Scripts\python.exe -m uvicorn app.main:app --reload`.

## Conventions

- Backend FastAPI app object is `app.main:app`. Mock data lives in `app/data.py`;
  Pydantic models in `app/models.py`. Keep new endpoints reading from the mock layer
  until a real database is introduced.
- Frontend points at the backend via `VITE_API_URL` (default `http://localhost:8000`);
  see `frontend/.env.example`.
