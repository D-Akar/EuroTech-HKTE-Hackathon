"""Serve the real Garmin export as the platform's WearableReading model."""

from __future__ import annotations

import json
import os
import statistics
from datetime import datetime
from functools import lru_cache
from pathlib import Path

from .models import WearableReading

_BACKEND = Path(__file__).resolve().parent.parent
_REAL = _BACKEND / "data" / "garmin_samples.json"  # real 30-day export, committed to the repo

# The one featured patient whose wearables come from the real Garmin device.
# Configurable via GARMIN_PATIENT_ID; defaults to 7 (patient 1 stays seeded so the
# upstream smoke test keeps passing).
REAL_PATIENT_ID = int(os.environ.get("GARMIN_PATIENT_ID", "7"))


# Where the loaded samples actually came from, resolved on first _load().
_loaded_source = "none"  # one of: mongo | real | none


def _samples_path() -> Path | None:
    env = os.environ.get("GARMIN_SAMPLES")
    if env and Path(env).is_file():
        return Path(env)
    if _REAL.is_file():
        return _REAL
    return None


def _load_from_mongo() -> list[dict] | None:
    """Read sample dicts from MongoDB when MONGODB_URI is configured and reachable.

    Returns None (so the caller falls back to the JSON export) when Mongo is not
    configured, the driver is missing, the server is unreachable, or it is empty.
    """
    uri = os.environ.get("MONGODB_URI")
    if not uri:
        return None
    try:
        from pymongo import MongoClient
    except ImportError:
        return None
    db = os.environ.get("MONGODB_DB", "careloop")
    coll = os.environ.get("MONGODB_COLLECTION", "garmin_samples")
    try:
        client = MongoClient(uri, serverSelectionTimeoutMS=1500)
        docs = list(client[db][coll].find({}).sort("recorded_at", 1))
        client.close()
    except Exception:
        return None
    if not docs:
        return None
    rows: list[dict] = []
    for d in docs:
        row = {
            "kind": d.get("kind"),
            "value": d.get("value"),
            "unit": d.get("unit"),
            "recorded_at": d.get("recorded_at"),
            "sample_id": d.get("_id"),
            "source": d.get("source"),
        }
        if d.get("patient_id"):
            row["patient_id"] = d["patient_id"]
        if d.get("meta"):
            row["meta"] = d["meta"]
        rows.append(row)
    return rows


@lru_cache(maxsize=1)
def _load() -> list[dict]:
    global _loaded_source
    mongo_rows = _load_from_mongo()
    if mongo_rows:
        _loaded_source = "mongo"
        return mongo_rows
    path = _samples_path()
    if path is None:
        _loaded_source = "none"
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        _loaded_source = "none"
        return []
    rows = data if isinstance(data, list) else []
    _loaded_source = "real"  # any loaded export (env path or the committed file) is real
    return rows


def is_real() -> bool:
    """True when backed by MongoDB or the real Garmin export."""
    _load()  # resolves _loaded_source on first call
    return _loaded_source in ("mongo", "real")


def reload() -> None:
    """Drop the cached samples so the next read reflects a fresh backfill.

    Lets an operator run one Garmin pull before the demo and have the report/trends pick
    it up without restarting the server. The daily rollup cache is cleared too.
    """
    _load.cache_clear()
    _daily.cache_clear()


def raw_samples(kind: str | None = None, limit: int | None = None) -> list[dict]:
    rows = _load()
    if kind:
        rows = [r for r in rows if r.get("kind") == kind]
    if limit is not None:
        rows = rows[:limit]
    return rows


def _num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


@lru_cache(maxsize=1)
def _daily() -> list[tuple]:
    """Collapse the samples into one (day, heart_rate, steps, sleep_hours) row per day."""
    by_day: dict[str, dict] = {}
    for r in _load():
        ts = r.get("recorded_at")
        if not ts:
            continue
        agg = by_day.setdefault(ts[:10], {"hr": [], "resting_hr": None, "steps": None, "sleep_s": None})
        kind, val, source = r.get("kind"), r.get("value"), r.get("source")
        if kind == "heart_rate" and source != "garmin_activity":
            v = _num(val)
            if v is not None:
                agg["hr"].append(v)
        elif kind == "resting_heart_rate":
            agg["resting_hr"] = _num(val)
        elif kind == "steps":
            agg["steps"] = _num(val)
        elif kind == "sleep_duration":
            agg["sleep_s"] = _num(val)

    rows: list[tuple] = []
    for day, agg in sorted(by_day.items(), reverse=True):
        hr = agg["resting_hr"]
        if hr is None and agg["hr"]:
            hr = round(statistics.mean(agg["hr"]))
        sleep_hours = round(agg["sleep_s"] / 3600, 1) if agg["sleep_s"] else None
        if hr is None and agg["steps"] is None and sleep_hours is None:
            continue
        rows.append((day, hr, agg["steps"], sleep_hours))
    return rows


def daily_readings(patient_id: int) -> list[WearableReading]:
    """Real Garmin daily readings, stamped for the requested patient, most-recent first."""
    out: list[WearableReading] = []
    for i, (day, hr, steps, sleep_hours) in enumerate(_daily()):
        out.append(
            WearableReading(
                id=patient_id * 100000 + i,
                patient_id=patient_id,
                timestamp=datetime.fromisoformat(f"{day}T09:00:00"),
                heart_rate=int(hr) if hr is not None else 0,
                steps=int(steps) if steps is not None else 0,
                sleep_hours=float(sleep_hours) if sleep_hours is not None else 0.0,
            )
        )
    return out
