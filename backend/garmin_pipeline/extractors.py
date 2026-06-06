"""Parse garminconnect / garminexport JSON into Sample objects.

Field names follow arpanghosh8453/garmin-grafana (BSD-3-Clause). Parsing is defensive:
bad entries are skipped and a missing/None response yields an empty list.
"""

from __future__ import annotations

from typing import Any, Optional
from zoneinfo import ZoneInfo

from .models import (
    BODY_BATTERY,
    BP_DIASTOLIC,
    BP_SYSTOLIC,
    HEART_RATE,
    RESPIRATION,
    RESTING_HEART_RATE,
    SLEEP_DURATION,
    SLEEP_STAGE,
    SPO2,
    STEPS,
    STRESS,
    Sample,
    from_epoch_ms,
    make_sample,
    parse_gmt,
)


def _num(x: Any) -> Optional[float]:
    if isinstance(x, bool):
        return None
    if isinstance(x, (int, float)):
        return x
    return None


def _pair(entry: Any) -> bool:
    return isinstance(entry, (list, tuple)) and len(entry) >= 2


def extract_heart_rate(hr_json: Optional[dict], tz: ZoneInfo, source: str = "garmin") -> list[Sample]:
    """Intraday heart rate from get_heart_rates: heartRateValues = [[ts_ms, bpm], ...]."""
    out: list[Sample] = []
    for entry in (hr_json or {}).get("heartRateValues") or []:
        if not _pair(entry):
            continue
        ts_ms, bpm = entry[0], entry[1]
        if _num(ts_ms) is None or _num(bpm) is None or bpm <= 0:
            continue
        out.append(make_sample(HEART_RATE, int(bpm), from_epoch_ms(ts_ms, tz), source=source))
    return out


def extract_daily_stats(stats_json: Optional[dict], tz: ZoneInfo, source: str = "garmin") -> list[Sample]:
    """Resting HR and daily steps from get_stats (one reading per day)."""
    out: list[Sample] = []
    j = stats_json or {}
    ts = parse_gmt(j.get("wellnessStartTimeGmt"), tz)
    if ts is None and isinstance(j.get("calendarDate"), str):
        ts = parse_gmt(j["calendarDate"] + "T00:00:00", tz)
    if ts is None:
        return out
    rhr = j.get("restingHeartRate")
    if _num(rhr) is not None and rhr > 0:
        out.append(make_sample(RESTING_HEART_RATE, int(rhr), ts, source=source))
    steps = j.get("totalSteps")
    if _num(steps) is not None and steps >= 0:
        out.append(make_sample(STEPS, int(steps), ts, source=source))
    return out


def extract_stress(stress_json: Optional[dict], tz: ZoneInfo, source: str = "garmin") -> list[Sample]:
    """Intraday stress from get_stress_data: stressValuesArray = [[ts_ms, level], ...]."""
    out: list[Sample] = []
    for entry in (stress_json or {}).get("stressValuesArray") or []:
        if not _pair(entry):
            continue
        ts_ms, level = entry[0], entry[1]
        # Garmin uses negative sentinels (-1/-2) for "no reading".
        if _num(ts_ms) is None or _num(level) is None or level < 0:
            continue
        out.append(make_sample(STRESS, int(level), from_epoch_ms(ts_ms, tz), source=source))
    return out


def extract_body_battery(stress_json: Optional[dict], tz: ZoneInfo, source: str = "garmin") -> list[Sample]:
    """Body battery from get_stress_data: bodyBatteryValuesArray = [[ts_ms, status, level], ...]."""
    out: list[Sample] = []
    for entry in (stress_json or {}).get("bodyBatteryValuesArray") or []:
        if not (isinstance(entry, (list, tuple)) and len(entry) >= 3):
            continue
        ts_ms, level = entry[0], entry[2]
        if _num(ts_ms) is None or _num(level) is None or level < 0:
            continue
        out.append(make_sample(BODY_BATTERY, int(level), from_epoch_ms(ts_ms, tz), source=source))
    return out


_STAGE_FIELDS = {
    "deep": "deepSleepSeconds",
    "light": "lightSleepSeconds",
    "rem": "remSleepSeconds",
    "awake": "awakeSleepSeconds",
}


def _sleep_start(dto: dict, tz: ZoneInfo):
    start_ms = dto.get("sleepStartTimestampGMT")
    if _num(start_ms) is not None:
        return from_epoch_ms(start_ms, tz)
    if isinstance(dto.get("calendarDate"), str):
        return parse_gmt(dto["calendarDate"] + "T00:00:00", tz)
    return None


def extract_sleep_summary(sleep_json: Optional[dict], tz: ZoneInfo, source: str = "garmin") -> list[Sample]:
    """Total + per-stage sleep durations and avg/lowest SpO2 from get_sleep_data's dailySleepDTO."""
    out: list[Sample] = []
    dto = (sleep_json or {}).get("dailySleepDTO") or {}
    ts = _sleep_start(dto, tz)
    if ts is None:
        return out
    epoch = int(ts.timestamp())

    total = dto.get("sleepTimeSeconds")
    if _num(total) is not None and total > 0:
        out.append(make_sample(SLEEP_DURATION, int(total), ts, source=source))

    for stage, field in _STAGE_FIELDS.items():
        secs = dto.get(field)
        if _num(secs) is not None and secs >= 0:
            out.append(
                make_sample(
                    SLEEP_STAGE, int(secs), ts, source=source,
                    meta={"stage": stage},
                    sample_id=f"{source}-{SLEEP_STAGE}-{stage}-{epoch}",
                )
            )

    avg = dto.get("averageSpO2Value")
    if _num(avg) is not None and avg > 0:
        out.append(
            make_sample(
                SPO2, round(float(avg), 1), ts, source=source,
                meta={"agg": "avg", "window": "sleep"},
                sample_id=f"{source}-{SPO2}-avg-{epoch}",
            )
        )
    low = dto.get("lowestSpO2Value")
    if _num(low) is not None and low > 0:
        out.append(
            make_sample(
                SPO2, int(low), ts, source=source,
                meta={"agg": "lowest", "window": "sleep"},
                sample_id=f"{source}-{SPO2}-low-{epoch}",
            )
        )
    return out


def extract_sleep_spo2(sleep_json: Optional[dict], tz: ZoneInfo, source: str = "garmin") -> list[Sample]:
    """Intraday sleep SpO2 from wellnessEpochSPO2DataDTOList: {spo2Reading, epochTimestamp}."""
    out: list[Sample] = []
    for entry in (sleep_json or {}).get("wellnessEpochSPO2DataDTOList") or []:
        if not isinstance(entry, dict):
            continue
        val = entry.get("spo2Reading")
        if _num(val) is None or val <= 0:
            continue
        ts = parse_gmt(entry.get("epochTimestamp"), tz)
        if ts is None:
            continue
        out.append(make_sample(SPO2, int(val), ts, source=source, meta={"window": "sleep"}))
    return out


def extract_sleep_respiration(sleep_json: Optional[dict], tz: ZoneInfo, source: str = "garmin") -> list[Sample]:
    """Intraday respiration from wellnessEpochRespirationDataDTOList: {respirationValue, startTimeGMT}."""
    out: list[Sample] = []
    for entry in (sleep_json or {}).get("wellnessEpochRespirationDataDTOList") or []:
        if not isinstance(entry, dict):
            continue
        val = entry.get("respirationValue")
        ts_ms = entry.get("startTimeGMT")
        if _num(val) is None or val <= 0 or _num(ts_ms) is None:
            continue
        out.append(make_sample(RESPIRATION, round(float(val), 1), from_epoch_ms(ts_ms, tz), source=source))
    return out


def extract_sleep(sleep_json: Optional[dict], tz: ZoneInfo, source: str = "garmin") -> list[Sample]:
    """All sleep-derived samples: duration, stages, summary + intraday SpO2, respiration."""
    return (
        extract_sleep_summary(sleep_json, tz, source)
        + extract_sleep_spo2(sleep_json, tz, source)
        + extract_sleep_respiration(sleep_json, tz, source)
    )


def extract_spo2_allday(spo2_json: Optional[dict], tz: ZoneInfo, source: str = "garmin") -> list[Sample]:
    """All-day SpO2 from get_spo2_data (present only if all-day PulseOx is enabled)."""
    out: list[Sample] = []
    j = spo2_json or {}
    arr = j.get("spo2ValuesArray") or j.get("spO2ValuesArray") or []
    for entry in arr:
        if not _pair(entry):
            continue
        ts_ms, val = entry[0], entry[1]
        if _num(ts_ms) is None or _num(val) is None or val <= 0:
            continue
        out.append(make_sample(SPO2, int(val), from_epoch_ms(ts_ms, tz), source=source, meta={"window": "all_day"}))
    return out


def extract_activity_details(
    details_json: Optional[dict],
    tz: ZoneInfo,
    source: str = "garmin_activity",
    downsample: int = 1,
) -> list[Sample]:
    """In-workout HR time series from a garminexport activity *_details.json.

    metricDescriptors map a metric key to its column index in each activityDetailMetrics
    row; the indices vary per file so they are read, never hardcoded.
    """
    out: list[Sample] = []
    j = details_json or {}
    idx = {
        m["key"]: m["metricsIndex"]
        for m in (j.get("metricDescriptors") or [])
        if isinstance(m, dict) and "key" in m and "metricsIndex" in m
    }
    hi, ti = idx.get("directHeartRate"), idx.get("directTimestamp")
    if hi is None or ti is None:
        return out
    activity_id = j.get("activityId")
    step = downsample if isinstance(downsample, int) and downsample > 0 else 1
    for n, row in enumerate(j.get("activityDetailMetrics") or []):
        if step > 1 and (n % step):
            continue
        metrics = row.get("metrics") if isinstance(row, dict) else None
        if not isinstance(metrics, (list, tuple)) or hi >= len(metrics) or ti >= len(metrics):
            continue
        hr, ts_ms = metrics[hi], metrics[ti]
        if _num(hr) is None or hr <= 0 or _num(ts_ms) is None:
            continue
        meta = {"context": "activity"}
        if activity_id is not None:
            meta["activity_id"] = activity_id
        out.append(make_sample(HEART_RATE, int(hr), from_epoch_ms(ts_ms, tz), source=source, meta=meta))
    return out


def extract_blood_pressure(bp_json: Optional[dict], tz: ZoneInfo, source: str = "garmin") -> list[Sample]:
    """Blood pressure from get_blood_pressure. Usually empty: Garmin watches have no BP sensor."""
    out: list[Sample] = []
    j = bp_json or {}
    summaries = j.get("measurementSummaries") or j.get("bloodPressureMeasurements") or []
    for summary in summaries:
        if not isinstance(summary, dict):
            continue
        measurements = summary.get("measurements")
        if measurements is None and "systolic" in summary:
            measurements = [summary]
        for m in measurements or []:
            if not isinstance(m, dict):
                continue
            ts = parse_gmt(m.get("measurementTimestampGMT") or m.get("timestampGMT"), tz)
            if ts is None and _num(m.get("measurementTimestamp")) is not None:
                ts = from_epoch_ms(m["measurementTimestamp"], tz)
            if ts is None:
                continue
            sys = m.get("systolic")
            if _num(sys) is not None and sys > 0:
                out.append(make_sample(BP_SYSTOLIC, int(sys), ts, source=source))
            dia = m.get("diastolic")
            if _num(dia) is not None and dia > 0:
                out.append(make_sample(BP_DIASTOLIC, int(dia), ts, source=source))
    return out
