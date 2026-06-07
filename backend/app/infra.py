"""Best-effort local-infrastructure bootstrap, run on `uvicorn` startup.

When the backend boots we (1) bring up the MongoDB + FHIR-importer stack via Docker
Compose, (2) wait until Mongo actually accepts connections, then (3) (re)apply the
real FHIR overlays onto the dashboard slots listed in ``Prompts/featured_patients.md``.

This closes the startup race that otherwise leaves the dashboard all-mock: the
import-time overlay in ``app.data`` runs before Mongo is healthy and silently binds
zero slots. Re-applying *after* Mongo is reachable guarantees the featured patients
show real data without a manual backend restart.

Every step is best-effort and non-fatal - if Docker isn't installed or the stack
can't start, the app still boots on the full mock dataset. Disable the whole thing
with ``CARELOOP_AUTOSTART_MONGO=0``.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
import time

from . import (
    call_store,
    care_plan_store,
    checkin_store,
    data,
    erasure_store,
    fhir_source,
    patient_overrides,
    wearable_source,
)
from .config import settings

log = logging.getLogger("careloop.infra")


def _start_stack() -> bool:
    """Run ``docker compose up -d`` from the repo root. True on success."""
    if shutil.which("docker") is None:
        log.warning("Docker not found on PATH - skipping Mongo autostart.")
        return False
    cmd = ["docker", "compose", "up", "-d"]
    try:
        subprocess.run(
            cmd,
            cwd=settings.repo_root,
            check=True,
            capture_output=True,
            text=True,
            timeout=settings.mongo_autostart_timeout,
        )
        return True
    except subprocess.CalledProcessError as exc:
        log.warning("`docker compose up` failed (exit %s): %s", exc.returncode, exc.stderr.strip())
    except subprocess.TimeoutExpired:
        log.warning("`docker compose up` timed out after %ss.", settings.mongo_autostart_timeout)
    except OSError as exc:
        log.warning("Could not run docker compose: %s", exc)
    return False


def _wait_for_mongo(timeout: float) -> bool:
    """Poll until Mongo answers a ping, or ``timeout`` elapses. True if reachable."""
    try:
        from pymongo import MongoClient
        from pymongo.errors import PyMongoError
    except ImportError:
        log.warning("pymongo not installed - cannot load real FHIR records.")
        return False

    deadline = time.monotonic() + timeout
    while True:
        try:
            client = MongoClient(settings.mongodb_uri, serverSelectionTimeoutMS=1000)
            client.admin.command("ping")
            client.close()
            return True
        except (PyMongoError, Exception):  # noqa: BLE001 - any driver/network error -> retry
            if time.monotonic() >= deadline:
                return False
            time.sleep(1.0)


def ensure_mongo_and_overlays() -> None:
    """Bring up Mongo (best-effort), wait for it, then (re)apply FHIR overlays."""
    if settings.autostart_mongo:
        if _start_stack():
            log.info("Docker Compose stack started; waiting for MongoDB...")
            if _wait_for_mongo(settings.mongo_ready_timeout):
                log.info("MongoDB is accepting connections.")
            else:
                log.warning(
                    "MongoDB not reachable after %ss - dashboard may stay on mock data.",
                    settings.mongo_ready_timeout,
                )

    # Load erasure tombstones first so the overlay keeps erased slots redacted.
    erased = erasure_store.load_persisted()
    if erased:
        log.info("Loaded %d right-to-erasure tombstone(s).", erased)

    bound = fhir_source.apply_overlays(data.PATIENTS, wearable_source.REAL_PATIENT_ID)
    if bound:
        log.info("Overlaid %d real FHIR patient(s) onto dashboard slots.", bound)
    else:
        log.info("No FHIR overlays applied - dashboard running on mock data.")
    # apply_overlays clears the profile cache, so (re)apply the live-Garmin patient's
    # synthetic profile after it, exactly as data.py does at import time.
    fhir_source.apply_featured_profile(data.PATIENTS, wearable_source.REAL_PATIENT_ID)

    # Re-apply dashboard-edited phone numbers last, so they win over seed and FHIR.
    applied = patient_overrides.apply(data.PATIENTS)
    if applied:
        log.info("Applied %d saved phone-number override(s).", applied)

    # Reload persisted call history + uploaded care plans so they survive restarts.
    calls = call_store.load_persisted()
    if calls:
        log.info("Loaded %d persisted call record(s).", calls)
    plans = care_plan_store.load_persisted()
    if plans:
        log.info("Loaded %d persisted care plan(s).", plans)
    derived_checkins = checkin_store.load_persisted()
    if derived_checkins:
        log.info("Loaded %d persisted call-derived check-in(s).", derived_checkins)
