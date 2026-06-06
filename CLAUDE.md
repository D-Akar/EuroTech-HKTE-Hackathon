# CLAUDE.md

Guidance for working in this repo. See `README.md` for the product overview and
`docs/superpowers/specs/` for the design.

## What this is

A two-way platform connecting outpatient elderly-care practices with their patients:
daily phone-call check-ins + wearable health data, surfaced to practices as a per-patient
health timeline. **Currently an early scaffold** — React dashboard + FastAPI backend
serving mostly in-memory mock data, plus a MongoDB store (run via Docker Compose) holding
processed FHIR patient records. No auth or write endpoints yet.

## Layout

```
backend/    FastAPI app — app/main.py (routes), app/models.py, app/data.py (mock data)
            scripts/  preprocess_fhir.py + import_fhir_to_mongo.py
frontend/   React + Vite + TypeScript dashboard
docker/     Dockerfiles: docker/mongo (mongo:7), docker/importer (FHIR import job)
data/       data/fhir_processed/ — 555 FHIR patient records (JSON), imported into Mongo
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

## MongoDB (patient records)

Run from the repo root via Docker Compose. `docker compose up` starts MongoDB **and**
auto-loads the FHIR records via the one-shot `importer` service — no manual import step.

**Auto-started by the backend:** on `uvicorn` startup `app/infra.py` runs `docker compose
up -d`, waits for Mongo to accept connections, then applies the FHIR overlays — so the
featured patients show real data without a manual `docker compose up` or a backend
restart. Best-effort: no Docker / Mongo down → the app still boots on mock data. Disable
with `CARELOOP_AUTOSTART_MONGO=0` (tunables: `CARELOOP_MONGO_AUTOSTART_TIMEOUT`,
`CARELOOP_MONGO_READY_TIMEOUT` in `app/config.py`).

```bash
docker compose up -d --wait     # start mongo + import, block until healthy
docker compose down             # stop (data kept in named volume careloop-mongo-data)
docker compose down -v          # stop AND wipe the database
```

- Database `careloop`, collection `fhir_patients`, keyed by `_id` (patient UUID), 555 records.
- The `importer` upserts by `_id` (idempotent) from `data/fhir_processed/` (bind-mounted ro).
- Query by id: `docker exec careloop-mongo mongosh careloop --quiet --eval
  'db.fhir_patients.findOne({_id: "<uuid>"})'`.
- Manual re-import: `cd backend; python -m scripts.import_fhir_to_mongo` (`--drop` for clean
  reload). Needs `pymongo` (in `backend/requirements.txt`).

**Real patients on the dashboard:** list MongoDB `_id`s in `featured_patients.md` (repo
root). At startup `app/fhir_source.py` binds each, in order, to a dashboard patient slot
(skipping the live Garmin patient) and overlays the real name/age + a medical profile
(`GET /patients/{id}/profile`). Best-effort: Mongo down / id missing → that slot stays
mock. Read **at startup**, so restart the backend after editing the file. Mongo settings
(`MONGODB_URI`, `MONGODB_DB`, `FHIR_COLLECTION`) and `FEATURED_PATIENTS_FILE` live in
`app/config.py`.

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
  Pydantic models in `app/models.py`. Most endpoints read the mock layer; the FHIR
  read-path (`app/fhir_source.py` → patient demographics + `/profile`) overlays real
  MongoDB data onto the slots listed in `featured_patients.md`. Keep new endpoints on the
  mock layer unless you're extending the Mongo-backed path.
- Frontend points at the backend via `VITE_API_URL` (default `http://localhost:8000`);
  see `frontend/.env.example`.
