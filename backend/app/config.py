"""Runtime configuration loaded from environment variables.

Secrets live in ``backend/.env`` (gitignored). See ``backend/.env.example``.
Reads with ``python-dotenv`` so the values are available whether the app is run
via ``uvicorn`` or under pytest.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

# Load backend/.env (no-op if the file is missing — env vars may be set directly).
load_dotenv()

# Repo root = three levels up from this file (backend/app/config.py -> repo root).
_REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings:
    """Telephony credentials for the ElevenLabs Twilio outbound-call endpoint."""

    # --- MongoDB (real FHIR patient records) ---
    # Mirrors the importer defaults in backend/scripts/import_fhir_to_mongo.py.
    mongodb_uri: str = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
    mongodb_db: str = os.getenv("MONGODB_DB", "careloop")
    fhir_collection: str = os.getenv("FHIR_COLLECTION", "fhir_patients")
    # Dashboard-edited phone numbers, keyed by patient slot id. Overlaid on startup
    # (after the FHIR overlay) so an edited number survives restarts. See
    # app/patient_overrides.py.
    phone_overrides_collection: str = os.getenv(
        "PHONE_OVERRIDES_COLLECTION", "patient_phone_overrides"
    )
    # Markdown file listing the patient UUIDs to surface as real data on the dashboard.
    featured_patients_file: str = os.getenv(
        "FEATURED_PATIENTS_FILE", str(_REPO_ROOT / "featured_patients.md")
    )

    # --- Local infra bootstrap (run on `uvicorn` startup) ---
    # Repo root holding docker-compose.yml; `docker compose` runs from here.
    repo_root: str = str(_REPO_ROOT)
    # Auto-run `docker compose up -d` on app startup so MongoDB is ready before the
    # FHIR overlays apply. Set CARELOOP_AUTOSTART_MONGO=0 to skip (CI/tests/no Docker).
    autostart_mongo: bool = os.getenv("CARELOOP_AUTOSTART_MONGO", "1").lower() not in (
        "0",
        "false",
        "no",
    )
    # Max seconds to wait for `docker compose up` to return.
    mongo_autostart_timeout: int = int(os.getenv("CARELOOP_MONGO_AUTOSTART_TIMEOUT", "180"))
    # Max seconds to poll for Mongo to accept connections before applying overlays.
    mongo_ready_timeout: int = int(os.getenv("CARELOOP_MONGO_READY_TIMEOUT", "60"))

    elevenlabs_api_key: str = os.getenv("ELEVENLABS_API_KEY", "")
    # Outbound check-in agent — the one this backend dials with (see telephony.py).
    elevenlabs_agent_id: str = os.getenv("ELEVENLABS_AGENT_ID", "")
    # Inbound agent — answers patient call-backs. Stored for reference/parity;
    # inbound calls are handled by ElevenLabs' dashboard-configured agent, so the
    # backend never dials with this id (it only serves the patient-context tool).
    elevenlabs_inbound_agent_id: str = os.getenv("ELEVENLABS_INBOUND_AGENT_ID", "")
    elevenlabs_agent_phone_number_id: str = os.getenv(
        "ELEVENLABS_AGENT_PHONE_NUMBER_ID", ""
    )
    # Stored for completeness; the outbound-call endpoint dials via the Twilio
    # number already registered to the ElevenLabs agent, so it is not sent here.
    twilio_api_key: str = os.getenv("TWILIO_API_KEY", "")

    # ElevenLabs Twilio outbound-call endpoint (EU data-residency base URL).
    elevenlabs_outbound_url: str = (
        "https://api.eu.residency.elevenlabs.io/v1/convai/twilio/outbound-call"
    )
    # Conversation-detail endpoint (same residency base); {id} filled per call.
    elevenlabs_conversations_url: str = (
        "https://api.eu.residency.elevenlabs.io/v1/convai/conversations"
    )

    # API key for ElevenLabs server-tool callbacks into this service.
    elevenlabs_tool_api_key: str = os.getenv("ELEVENLABS_TOOL_API_KEY", "")

    # Nurse on call — dialled when a patient is escalated to urgent.
    nurse_phone_number: str = os.getenv("NURSE_PHONE_NUMBER", "")

    @property
    def is_configured(self) -> bool:
        """True when the minimum needed to place a call is present."""
        return bool(
            self.elevenlabs_api_key
            and self.elevenlabs_agent_id
            and self.elevenlabs_agent_phone_number_id
        )


settings = Settings()
