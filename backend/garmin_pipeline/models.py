"""Sample model and timestamp helpers."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from typing import Any, Optional
from zoneinfo import ZoneInfo

# Vital kinds (sample dict "kind" values)
HEART_RATE = "heart_rate"
RESTING_HEART_RATE = "resting_heart_rate"
STEPS = "steps"
STRESS = "stress"
BODY_BATTERY = "body_battery"
SLEEP_DURATION = "sleep_duration"
SLEEP_STAGE = "sleep_stage"
SPO2 = "spo2"
RESPIRATION = "respiration"
BP_SYSTOLIC = "blood_pressure_systolic"
BP_DIASTOLIC = "blood_pressure_diastolic"

# Default UCUM-ish units per kind (the FHIR teammate maps these to UCUM codes / LOINC).
UNIT: dict[str, str] = {
    HEART_RATE: "/min",
    RESTING_HEART_RATE: "/min",
    STEPS: "count",
    STRESS: "{score}",
    BODY_BATTERY: "{score}",
    SLEEP_DURATION: "s",
    SLEEP_STAGE: "s",
    SPO2: "%",
    RESPIRATION: "/min",
    BP_SYSTOLIC: "mm[Hg]",
    BP_DIASTOLIC: "mm[Hg]",
}

DEFAULT_TZ = "Asia/Hong_Kong"
_GMT_FORMATS = ("%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S")


def get_tz(name: str = DEFAULT_TZ) -> ZoneInfo:
    """Resolve a timezone name to a ZoneInfo (falls back to UTC if unavailable)."""
    try:
        return ZoneInfo(name)
    except Exception:  # pragma: no cover - environment without the tz db
        return ZoneInfo("UTC")


def from_epoch_ms(ms: float, tz: ZoneInfo) -> datetime:
    """Garmin epoch-millis (UTC) -> tz-aware datetime in `tz`."""
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).astimezone(tz)


def parse_gmt(value: str, tz: ZoneInfo) -> Optional[datetime]:
    """Parse a Garmin naive-GMT string (e.g. '2026-05-30T03:14:00.0') as UTC -> `tz`.

    Returns None on any malformed input (defensive: external data is never trusted).
    """
    if not isinstance(value, str):
        return None
    for fmt in _GMT_FORMATS:
        try:
            naive = datetime.strptime(value, fmt)
            return naive.replace(tzinfo=timezone.utc).astimezone(tz)
        except (ValueError, TypeError):
            continue
    return None


@dataclass(frozen=True)
class Sample:
    """One normalized wearable reading."""

    kind: str
    value: Any
    unit: str
    recorded_at: datetime
    source: str = "garmin"
    sample_id: str = ""
    meta: Optional[dict[str, Any]] = None

    def with_id(self) -> "Sample":
        """Return a copy with a deterministic sample_id if one is not already set.

        Determinism makes re-runs idempotent (the store upserts on sample_id).
        """
        if self.sample_id:
            return self
        epoch = int(self.recorded_at.timestamp())
        sid = f"{self.source}-{self.kind}-{epoch}"
        return replace(self, sample_id=sid)

    def to_dict(self) -> dict[str, Any]:
        s = self.with_id()
        out: dict[str, Any] = {
            "kind": s.kind,
            "value": s.value,
            "unit": s.unit,
            "recorded_at": s.recorded_at.isoformat(),
            "sample_id": s.sample_id,
            "source": s.source,
        }
        if s.meta:
            out["meta"] = dict(s.meta)
        return out


def make_sample(
    kind: str,
    value: Any,
    recorded_at: datetime,
    *,
    source: str = "garmin",
    unit: Optional[str] = None,
    meta: Optional[dict[str, Any]] = None,
    sample_id: Optional[str] = None,
) -> Sample:
    """Build a Sample with the default unit for `kind` and a deterministic id."""
    resolved_unit = unit if unit is not None else UNIT.get(kind, "")
    sample = Sample(
        kind=kind,
        value=value,
        unit=resolved_unit,
        recorded_at=recorded_at,
        source=source,
        meta=meta,
        sample_id=sample_id or "",
    )
    return sample.with_id()
