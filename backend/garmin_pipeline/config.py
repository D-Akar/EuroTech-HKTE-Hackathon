"""Configuration loaded from environment / .env."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

# Tunables with sane defaults. Rate-limit defaults mirror the proven garmin-grafana values
# (min interval between calls + long backoff on HTTP 429) to avoid per-account lockout.
DEFAULTS = {
    "LOCAL_TZ": "Asia/Hong_Kong",
    "FETCH_DAYS": "30",
    "DATA_DIR": "./data",
    "MONGODB_URI": "mongodb://localhost:27017",
    "MONGODB_DB": "careloop",
    "MONGODB_COLLECTION": "garmin_samples",
    "POLL_INTERVAL_SECONDS": "60",
    # Login is the rate-limit-sensitive call and is already cached after first success;
    # authenticated data getters tolerate a tighter cadence. Tuned for a one-time personal
    # backfill: ~2s between calls (~5 min for 30 days), modest backoff on the rare data 429.
    "MIN_CALL_INTERVAL_SECONDS": "2",
    "BACKOFF_SECONDS": "120",
    "MAX_RETRIES": "5",
}


def load_env_file(path: str | os.PathLike) -> None:
    """Minimal .env loader (no dependency). Existing env vars win; missing file is ignored."""
    p = Path(path)
    if not p.is_file():
        return
    for raw in p.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


@dataclass(frozen=True)
class Config:
    garmin_email: Optional[str]
    garmin_password: Optional[str]
    is_cn: bool
    token_store: str
    local_tz: str
    fetch_days: int
    data_dir: str
    mongodb_uri: str
    mongodb_db: str
    mongodb_collection: str
    patient_uuid: str
    poll_interval_seconds: float
    min_call_interval_seconds: float
    backoff_seconds: float
    max_retries: int

    @classmethod
    def from_env(cls, env: Optional[dict] = None) -> "Config":
        e = env if env is not None else os.environ

        def get(name: str) -> str:
            return e.get(name, DEFAULTS.get(name, ""))

        data_dir = get("DATA_DIR")
        token_store = e.get("GARMIN_TOKEN_STORE") or os.path.expanduser("~/.garminconnect")
        return cls(
            garmin_email=e.get("GARMIN_EMAIL") or None,
            garmin_password=e.get("GARMIN_PASSWORD") or None,
            is_cn=str(e.get("GARMIN_IS_CN", "")).lower() in ("1", "true", "yes"),
            token_store=token_store,
            local_tz=get("LOCAL_TZ"),
            fetch_days=int(get("FETCH_DAYS")),
            data_dir=data_dir,
            mongodb_uri=get("MONGODB_URI"),
            mongodb_db=get("MONGODB_DB"),
            mongodb_collection=get("MONGODB_COLLECTION"),
            patient_uuid=e.get("GARMIN_PATIENT_UUID", ""),
            poll_interval_seconds=float(get("POLL_INTERVAL_SECONDS")),
            min_call_interval_seconds=float(get("MIN_CALL_INTERVAL_SECONDS")),
            backoff_seconds=float(get("BACKOFF_SECONDS")),
            max_retries=int(get("MAX_RETRIES")),
        )
