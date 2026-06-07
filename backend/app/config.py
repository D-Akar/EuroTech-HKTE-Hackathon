"""Runtime configuration loaded from environment variables.

Secrets live in ``backend/.env`` (gitignored). See ``backend/.env.example``.
Reads with ``python-dotenv`` so the values are available whether the app is run
via ``uvicorn`` or under pytest.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

# Load backend/.env (no-op if the file is missing - env vars may be set directly).
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
    # Placed/attempted check-in calls, keyed by record id. Persisted so the call
    # history (shown under a patient's check-in data) survives restarts. See
    # app/call_store.py.
    call_history_collection: str = os.getenv(
        "CALL_HISTORY_COLLECTION", "patient_call_history"
    )
    # Uploaded FHIR care plans, keyed by patient slot id. Persisted so an uploaded
    # care plan survives restarts. See app/care_plan_store.py.
    care_plans_collection: str = os.getenv(
        "CARE_PLANS_COLLECTION", "patient_care_plans"
    )
    # Check-ins derived from completed AI calls, keyed by conversation id. Persisted
    # so a call-derived check-in survives restarts. See app/checkin_store.py.
    checkins_collection: str = os.getenv(
        "CHECKINS_COLLECTION", "patient_checkins"
    )
    # Per-call/patient consent records (PDPO DPP1/3, GDPR Art.9, PIPL). See app/consent_store.py.
    consent_collection: str = os.getenv("CONSENT_COLLECTION", "patient_consent")
    # Tamper-evident access/audit log (PDPO DPP4, GDPR Art.32). See app/audit.py.
    audit_collection: str = os.getenv("AUDIT_COLLECTION", "audit_log")
    # Durable right-to-erasure tombstones: patient slot ids whose FHIR-overlaid
    # identity/profile must stay redacted across restarts. See app/erasure_store.py.
    erasure_collection: str = os.getenv("ERASURE_COLLECTION", "erased_patients")

    # ---------------------------------------------------------------------------
    # Privacy & data-protection controls (see PRIVACY.md). Every control is
    # config-gated and OFF by default so the demo runs unchanged; switch them on in
    # backend/.env to get the real, enforced behaviour.
    # ---------------------------------------------------------------------------

    # --- Encryption at rest (AES-256-GCM) ---
    # When enabled, sensitive fields are encrypted before they touch MongoDB and
    # decrypted on read. Needs a 32-byte key (base64 or hex) and the `cryptography`
    # package; the app fails closed at startup if enabled without them.
    encrypt_at_rest: bool = os.getenv("CARELOOP_ENCRYPT_AT_REST", "0").lower() not in (
        "0", "false", "no", ""
    )
    data_encryption_key: str = os.getenv("CARELOOP_DATA_KEY", "")

    # --- Authentication + RBAC ---
    # When enabled, protected endpoints require a bearer token / X-API-Key mapped to
    # a role. Tokens are configured as "token:role,token:role" (roles: admin,
    # clinician, coordinator). Default OFF -> a synthetic admin principal, so the
    # open demo keeps working.
    auth_enabled: bool = os.getenv("CARELOOP_AUTH_ENABLED", "0").lower() not in (
        "0", "false", "no", ""
    )
    _auth_tokens_raw: str = os.getenv("CARELOOP_AUTH_TOKENS", "")

    # --- Consent enforcement (PDPO DPP1/3, GDPR Art.9) ---
    # When enabled, data-use endpoints (the patient-context handed to the voice
    # agent, the data export) refuse to release a patient's data unless an active
    # granted consent record exists. Default OFF so the demo runs without consent
    # capture; the voice consent gate (checkin_agent.py) still runs regardless.
    consent_enforcement: bool = os.getenv("CARELOOP_CONSENT_ENFORCEMENT", "0").lower() not in (
        "0", "false", "no", ""
    )

    # --- Per-client integration keys (ElevenLabs server-tool callbacks) ---
    # The callback auth accepts EITHER the single shared `elevenlabs_tool_api_key`
    # (back-compat) OR a per-client keyset configured as "key:client,key:client",
    # so each caller has its own rotatable key and the audit log records which one
    # called. See routers/integrations.py.
    _tool_api_keys_raw: str = os.getenv("CARELOOP_TOOL_API_KEYS", "")

    # --- Transport security ---
    # Redirect HTTP->HTTPS and emit HSTS + hardening headers. TLS itself is
    # terminated by the deployment (reverse proxy / platform); this enforces its use.
    force_https: bool = os.getenv("CARELOOP_FORCE_HTTPS", "0").lower() not in (
        "0", "false", "no", ""
    )
    security_headers: bool = os.getenv("CARELOOP_SECURITY_HEADERS", "1").lower() not in (
        "0", "false", "no", ""
    )

    # --- Data residency (declared region for HK/EU/local) ---
    data_residency: str = os.getenv("CARELOOP_DATA_RESIDENCY", "local")

    # --- Retention (days). 0 = keep forever. Purged daily + on demand. ---
    retention_checkins_days: int = int(os.getenv("CARELOOP_RETENTION_CHECKINS_DAYS", "0"))
    retention_calls_days: int = int(os.getenv("CARELOOP_RETENTION_CALLS_DAYS", "0"))
    retention_conversations_days: int = int(
        os.getenv("CARELOOP_RETENTION_CONVERSATIONS_DAYS", "0")
    )
    retention_audit_days: int = int(os.getenv("CARELOOP_RETENTION_AUDIT_DAYS", "0"))
    retention_consent_days: int = int(os.getenv("CARELOOP_RETENTION_CONSENT_DAYS", "0"))

    # Policy version stamped onto consent records, so a consent is tied to the exact
    # privacy terms the patient agreed to.
    privacy_policy_version: str = os.getenv("CARELOOP_PRIVACY_POLICY_VERSION", "2026-06-07")

    @property
    def auth_tokens(self) -> dict[str, str]:
        """Parse CARELOOP_AUTH_TOKENS ("tok:role,tok:role") into {token: role}."""
        out: dict[str, str] = {}
        for pair in self._auth_tokens_raw.split(","):
            pair = pair.strip()
            if not pair or ":" not in pair:
                continue
            token, role = pair.split(":", 1)
            token, role = token.strip(), role.strip().lower()
            if token and role:
                out[token] = role
        return out

    @property
    def tool_api_keys(self) -> dict[str, str]:
        """Parse CARELOOP_TOOL_API_KEYS ("key:client,...") into {key: client}.

        The single shared ``elevenlabs_tool_api_key`` is folded in (as client
        ``"shared"``) so existing single-key setups keep working.
        """
        out: dict[str, str] = {}
        for pair in self._tool_api_keys_raw.split(","):
            pair = pair.strip()
            if not pair or ":" not in pair:
                continue
            key, client = pair.split(":", 1)
            key, client = key.strip(), client.strip()
            if key and client:
                out[key] = client
        if self.elevenlabs_tool_api_key:
            out.setdefault(self.elevenlabs_tool_api_key, "shared")
        return out
    # Markdown file listing the patient UUIDs to surface as real data on the dashboard.
    featured_patients_file: str = os.getenv(
        "FEATURED_PATIENTS_FILE", str(_REPO_ROOT / "featured_patients.md")
    )
    # Markdown file holding the fixed opening question the outbound agent asks FIRST,
    # before the patient's personalised questions (injected as {{opening_question}}).
    # Read fresh on every call, so edits take effect without a restart.
    opening_question_file: str = os.getenv(
        "OPENING_QUESTION_FILE", str(_REPO_ROOT / "opening_question.md")
    )
    # Markdown file holding the verbatim privacy / data-security response the agent
    # speaks when the patient asks how their data is stored, whether it's safe,
    # encrypted, etc. (injected as {{privacy_response}}). Also read fresh per call.
    privacy_response_file: str = os.getenv(
        "PRIVACY_RESPONSE_FILE", str(_REPO_ROOT / "privacy_response.md")
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
    # Outbound check-in agent - the one this backend dials with (see telephony.py).
    elevenlabs_agent_id: str = os.getenv("ELEVENLABS_AGENT_ID", "")
    # Inbound agent - answers patient call-backs. Stored for reference/parity;
    # inbound calls are handled by ElevenLabs' dashboard-configured agent, so the
    # backend never dials with this id (it only serves the patient-context tool).
    elevenlabs_inbound_agent_id: str = os.getenv("ELEVENLABS_INBOUND_AGENT_ID", "")
    # Dedicated cognitive-screening agent (dementia voice-biomarker check). A
    # separate agent so its scripted Mini-Cog protocol and biomarker Data
    # Collection / Evaluation Criteria stay isolated from the check-in agent.
    # Created via scripts/create_screening_agent.py; dialled with kind="screening".
    elevenlabs_screening_agent_id: str = os.getenv("ELEVENLABS_SCREENING_AGENT_ID", "")
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

    # Nurse on call - dialled when a patient is escalated to urgent (and when the
    # patient does not answer their own emergency call).
    nurse_phone_number: str = os.getenv("NURSE_PHONE_NUMBER", "")

    # Override the featured (real-watch) patient's phone number, e.g. so the demo
    # operator can be the patient and receive the live escalation call themselves.
    garmin_patient_phone: str = os.getenv("GARMIN_PATIENT_PHONE", "")

    @property
    def is_configured(self) -> bool:
        """True when the minimum needed to place a call is present."""
        return bool(
            self.elevenlabs_api_key
            and self.elevenlabs_agent_id
            and self.elevenlabs_agent_phone_number_id
        )


settings = Settings()
