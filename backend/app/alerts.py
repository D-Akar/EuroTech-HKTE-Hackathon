"""Threshold alerts over a patient's wearable readings and rich vitals.

Thresholds are illustrative defaults; tune them per practice. Works on the daily
WearableReading for every patient, and additionally on rich Garmin vitals (SpO2, stress)
when they are available for the real patient.
"""

from __future__ import annotations

from typing import Optional

from .models import WearableReading

HR_LOW = 50          # bpm, bradycardia
HR_HIGH = 100        # bpm, tachycardia
SLEEP_LOW_HOURS = 5.0
STEPS_LOW = 600
SPO2_LOW = 90        # %
STRESS_HIGH = 80     # 0-100 score


def _alert(patient_id, kind, severity, message, value, unit, at):
    return {
        "patient_id": patient_id,
        "kind": kind,
        "severity": severity,
        "message": message,
        "value": value,
        "unit": unit,
        "at": at,
    }


def _extreme(vitals, kind, pick):
    vals = [v for v in vitals if v.get("kind") == kind and isinstance(v.get("value"), (int, float))]
    if not vals:
        return None
    return pick(vals, key=lambda v: v["value"])


def alerts_for(
    patient_id: int,
    readings: list[WearableReading],
    vitals: Optional[list[dict]] = None,
) -> list[dict]:
    out: list[dict] = []

    if readings:
        latest = readings[0]
        at = latest.timestamp.isoformat()
        hr = latest.heart_rate
        if hr and hr < HR_LOW:
            out.append(_alert(patient_id, "bradycardia", "warning", f"Resting heart rate {hr} bpm is below {HR_LOW}", hr, "bpm", at))
        elif hr and hr > HR_HIGH:
            out.append(_alert(patient_id, "tachycardia", "warning", f"Heart rate {hr} bpm is above {HR_HIGH}", hr, "bpm", at))
        if latest.sleep_hours and latest.sleep_hours < SLEEP_LOW_HOURS:
            out.append(_alert(patient_id, "poor_sleep", "warning", f"Only {latest.sleep_hours} h sleep last night", latest.sleep_hours, "h", at))
        if latest.steps is not None and latest.steps < STEPS_LOW:
            out.append(_alert(patient_id, "inactivity", "info", f"Low activity: {latest.steps} steps", latest.steps, "steps", at))

    if vitals:
        low_spo2 = _extreme(vitals, "spo2", min)
        if low_spo2 and low_spo2["value"] < SPO2_LOW:
            out.append(_alert(patient_id, "low_spo2", "critical", f"Blood oxygen dropped to {low_spo2['value']}%", low_spo2["value"], "%", low_spo2.get("recorded_at")))
        high_stress = _extreme(vitals, "stress", max)
        if high_stress and high_stress["value"] >= STRESS_HIGH:
            out.append(_alert(patient_id, "high_stress", "info", f"High stress reading ({int(high_stress['value'])})", high_stress["value"], "score", high_stress.get("recorded_at")))

    return out


def worst_severity(alert_list: list[dict]) -> Optional[str]:
    order = {"info": 1, "warning": 2, "critical": 3}
    if not alert_list:
        return None
    return max((a.get("severity", "info") for a in alert_list), key=lambda s: order.get(s, 0))


# Live (current-reading) escalation thresholds. A sustained high heart rate or a
# blood-oxygen drop on a resting elderly patient is the signal that turns the map
# marker red and prompts a check-in call.
HR_LIVE_URGENT = 120     # bpm
HR_LIVE_ELEVATED = 100   # bpm
SPO2_WATCH = 94          # %

_STATUS_BY_SEVERITY = {"critical": "urgent", "warning": "attention", "info": "stable"}


def _live_metric(snapshot: dict, key: str):
    m = snapshot.get(key)
    if isinstance(m, dict) and isinstance(m.get("value"), (int, float)):
        return float(m["value"]), m.get("unit"), m.get("at")
    return None


def live_assessment(patient_id: int, snapshot: dict) -> dict:
    """Turn a current-reading snapshot into a live status and alert list.

    Lets the dashboard recolor a patient and fire an escalation the moment a live
    vital crosses a threshold, rather than waiting on the daily export.
    """
    out: list[dict] = []

    hr = _live_metric(snapshot, "heart_rate")
    if hr:
        v, unit, at = hr
        if v >= HR_LIVE_URGENT:
            out.append(_alert(patient_id, "high_heart_rate", "critical", f"Heart rate {int(v)} bpm is critically high", v, unit, at))
        elif v >= HR_LIVE_ELEVATED:
            out.append(_alert(patient_id, "elevated_heart_rate", "warning", f"Heart rate {int(v)} bpm is elevated", v, unit, at))
        elif v < HR_LOW:
            out.append(_alert(patient_id, "bradycardia", "warning", f"Heart rate {int(v)} bpm is below {HR_LOW}", v, unit, at))

    spo2 = _live_metric(snapshot, "spo2")
    if spo2:
        v, unit, at = spo2
        if v < SPO2_LOW:
            out.append(_alert(patient_id, "low_spo2", "critical", f"Blood oxygen {int(v)}% is critically low", v, unit, at))
        elif v < SPO2_WATCH:
            out.append(_alert(patient_id, "low_spo2", "warning", f"Blood oxygen {int(v)}% is below normal", v, unit, at))

    stress = _live_metric(snapshot, "stress")
    if stress:
        v, unit, at = stress
        if v >= STRESS_HIGH:
            out.append(_alert(patient_id, "high_stress", "warning", f"High stress reading ({int(v)})", v, unit, at))

    sev = worst_severity(out)
    return {"status": _STATUS_BY_SEVERITY.get(sev, "stable"), "alerts": out}
