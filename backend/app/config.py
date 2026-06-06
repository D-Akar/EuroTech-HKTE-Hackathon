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
    # Markdown file listing the patient UUIDs to surface as real data on the dashboard.
    featured_patients_file: str = os.getenv(
        "FEATURED_PATIENTS_FILE", str(_REPO_ROOT / "featured_patients.md")
    )

    elevenlabs_api_key: str = os.getenv("ELEVENLABS_API_KEY", "")
    elevenlabs_agent_id: str = os.getenv("ELEVENLABS_AGENT_ID", "")
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

    @property
    def is_configured(self) -> bool:
        """True when the minimum needed to place a call is present."""
        return bool(
            self.elevenlabs_api_key
            and self.elevenlabs_agent_id
            and self.elevenlabs_agent_phone_number_id
        )


settings = Settings()
