"""FastAPI entrypoint for the elderly-care platform wireframe.

Run with:  uvicorn app.main:app --reload  (from the backend/ directory)
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import infra, scheduler
from .routers import (
    alerts,
    calls,
    care_plans,
    checkins,
    escalations,
    events,
    integrations,
    live,
    meta,
    patients,
    questions,
    reports,
    summary,
    vitals,
    wearables,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Start MongoDB (Docker) and bind real FHIR records onto the featured slots
    # before serving - closes the boot race that otherwise leaves the dash all-mock.
    infra.ensure_mongo_and_overlays()
    scheduler.start()
    try:
        yield
    finally:
        scheduler.shutdown()


app = FastAPI(
    title="Elderly Care Platform API",
    description="Wireframe backend: patients, daily check-ins, and wearable data.",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS: local Vite dev server, any Vercel preview/prod domain, and ngrok tunnels
# (so a deployed frontend can reach this backend through a tunnel during demos).
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=(
        r"https?://(localhost|127\.0\.0\.1)(:\d+)?"
        r"|https://[a-z0-9-]+\.vercel\.app"
        r"|https://[a-z0-9-]+\.ngrok(-free)?\.(dev|app|io)"
    ),
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(patients.router)
app.include_router(meta.router)
app.include_router(checkins.router)
app.include_router(questions.router)
app.include_router(wearables.router)
app.include_router(vitals.router)
app.include_router(alerts.router)
app.include_router(summary.router)
app.include_router(live.router)
app.include_router(calls.router)
app.include_router(reports.router)
app.include_router(care_plans.router)
app.include_router(integrations.router)
app.include_router(escalations.router)
app.include_router(events.router)


@app.get("/health", tags=["meta"])
def health() -> dict[str, str]:
    return {"status": "ok"}
