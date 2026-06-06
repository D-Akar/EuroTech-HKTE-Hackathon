"""Best-effort LIVE Garmin reading for the featured patient.

Tries a live fetch via the vendored garmin_pipeline using the cached token; if that is
unavailable (no token, library missing, rate limited, or MFA needed) it falls back to the
latest values from the exported data. Results are cached briefly so repeated clicks during
a demo do not hammer Garmin. Never blocks on an interactive MFA prompt.
"""

from __future__ import annotations

import os
import time
from datetime import date
from typing import Optional

from . import wearable_source

# How long a fetched live reading is reused before we hit Garmin again. Kept short so the
# dashboard tracks the cloud closely during a demo; raise it (env) to spare Garmin's rate
# limit over a long-running session. The dominant freshness limit is Garmin's own
# watch->phone->cloud sync cadence, not this cache.
_TTL_SECONDS = float(os.environ.get("LIVE_TTL_SECONDS", "10"))
_cache: dict = {"at": 0.0, "value": None}


def _mfa_unavailable() -> str:
    raise RuntimeError("MFA prompt not available in server context")


def _latest(rows: list[dict], kind: str) -> Optional[dict]:
    cand = [r for r in rows if r.get("kind") == kind and isinstance(r.get("value"), (int, float))]
    if not cand:
        return None
    best = max(cand, key=lambda r: r.get("recorded_at", ""))
    return {"value": best["value"], "unit": best.get("unit"), "at": best.get("recorded_at")}


def _snapshot(rows: list[dict], source: str) -> dict:
    return {
        "source": source,
        "heart_rate": _latest(rows, "heart_rate"),
        "stress": _latest(rows, "stress"),
        "spo2": _latest(rows, "spo2"),
        "steps": _latest(rows, "steps"),
    }


def _attempt_live() -> Optional[dict]:
    try:
        from garmin_pipeline.client import GarminClient
        from garmin_pipeline.config import Config, load_env_file
        from garmin_pipeline.ratelimit import RateLimiter, RateLimitPolicy

        load_env_file(".env")
        load_env_file("../.env")
        # A snappy rate limit for an interactive click; the token is already cached.
        fast = RateLimiter(RateLimitPolicy(min_call_interval_seconds=0.4, backoff_seconds=5, max_retries=1))
        client = GarminClient(Config.from_env(), rate_limiter=fast, mfa_prompt=_mfa_unavailable)
        client.login()  # cached-token path only; raises rather than prompting
        rows = [s.to_dict() for s in client.fetch_day(date.today())]
        return _snapshot(rows, "live") if rows else None
    except Exception:
        return None


def live_vitals() -> dict:
    now = time.monotonic()
    cached = _cache["value"]
    if cached is not None and (now - _cache["at"]) < _TTL_SECONDS:
        return cached
    value = _attempt_live() or _snapshot(wearable_source.raw_samples(), "export-fallback")
    _cache["at"] = now
    _cache["value"] = value
    return value
