"""FastAPI entrypoint for the elderly-care platform wireframe.

Run with:  uvicorn app.main:app --reload  (from the backend/ directory)
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import scheduler
from .routers import alerts, calls, checkins, live, meta, patients, summary, vitals, wearables


@asynccontextmanager
async def lifespan(app: FastAPI):
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

# Open CORS for the Vite dev server during development.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(patients.router)
app.include_router(meta.router)
app.include_router(checkins.router)
app.include_router(wearables.router)
app.include_router(vitals.router)
app.include_router(alerts.router)
app.include_router(summary.router)
app.include_router(live.router)
app.include_router(calls.router)


@app.get("/health", tags=["meta"])
def health() -> dict[str, str]:
    return {"status": "ok"}
