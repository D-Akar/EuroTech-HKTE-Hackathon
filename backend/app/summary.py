"""Summary statistics over a patient's wearable history and rich vitals."""

from __future__ import annotations

from typing import Optional

from .models import WearableReading


def _stat(values: list[float]) -> Optional[dict]:
    if not values:
        return None
    return {
        "min": round(min(values), 1),
        "max": round(max(values), 1),
        "avg": round(sum(values) / len(values), 1),
        "n": len(values),
    }


def _rich(vitals: list[dict], kind: str) -> list[float]:
    return [v["value"] for v in vitals if v.get("kind") == kind and isinstance(v.get("value"), (int, float))]


def compute_summary(readings: list[WearableReading], vitals: Optional[list[dict]] = None) -> dict:
    vitals = vitals or []
    out: dict = {
        "days": len(readings),
        "heart_rate": _stat([r.heart_rate for r in readings if r.heart_rate]),
        "sleep_hours": _stat([r.sleep_hours for r in readings if r.sleep_hours]),
        "steps": _stat([float(r.steps) for r in readings if r.steps is not None]),
    }

    spo2 = _rich(vitals, "spo2")
    if spo2:
        s = _stat(spo2)
        s["low_events"] = sum(1 for x in spo2 if x < 90)
        out["spo2"] = s

    stress = _rich(vitals, "stress")
    if stress:
        s = _stat(stress)
        s["high_events"] = sum(1 for x in stress if x >= 80)
        out["stress"] = s

    return out
