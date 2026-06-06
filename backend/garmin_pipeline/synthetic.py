"""Synthetic vitals source behind the same Sample interface (clearly labeled)."""

from __future__ import annotations

import random
from datetime import date, datetime, timedelta
from typing import Optional
from zoneinfo import ZoneInfo

from .models import (
    BODY_BATTERY,
    BP_DIASTOLIC,
    BP_SYSTOLIC,
    DEFAULT_TZ,
    HEART_RATE,
    RESPIRATION,
    RESTING_HEART_RATE,
    SLEEP_DURATION,
    SLEEP_STAGE,
    SPO2,
    STEPS,
    STRESS,
    Sample,
    get_tz,
    make_sample,
)

SOURCE = "synthetic"


def _dt(d: date, hour: int, minute: int, tz: ZoneInfo) -> datetime:
    return datetime(d.year, d.month, d.day, hour, minute, tzinfo=tz)


def generate(
    days: int = 7,
    end: Optional[date] = None,
    tz: Optional[ZoneInfo] = None,
    *,
    seed: int = 42,
    include_bp: bool = True,
    include_abnormal: bool = True,
) -> list[Sample]:
    """Deterministic ~month of plausible vitals. The most recent day carries anomalies."""
    rng = random.Random(seed)
    tz = tz or get_tz(DEFAULT_TZ)
    end = end or date.today()
    out: list[Sample] = []
    day_list = [end - timedelta(days=i) for i in range(days)][::-1]
    abnormal_day = day_list[-1] if include_abnormal else None

    def emit(kind, value, dt, **kw):
        out.append(make_sample(kind, value, dt, source=SOURCE, **kw))

    for idx, d in enumerate(day_list):
        # Resting HR: gentle upward trend, spike on the abnormal day.
        rhr = 52 + idx * 0.3 + rng.uniform(-1, 1)
        if d == abnormal_day:
            rhr += 12
        emit(RESTING_HEART_RATE, round(rhr), _dt(d, 7, 0, tz))

        # Steps: declining; the abnormal day is near-immobile (inactivity signal).
        steps = max(0, int(4000 - idx * 120 + rng.uniform(-500, 500)))
        if d == abnormal_day:
            steps = 180
        emit(STEPS, steps, _dt(d, 23, 0, tz))

        # Intraday HR every 30 min (lower overnight).
        for h in range(24):
            for m in (0, 30):
                base = 58 if h < 6 else 70 + 8 * rng.random()
                emit(HEART_RATE, int(base + rng.uniform(-4, 5)), _dt(d, h, m, tz))
        # Bradycardia window (HR ~42-47) early morning on the abnormal day.
        if d == abnormal_day:
            for m in (0, 15, 30, 45):
                emit(HEART_RATE, rng.randint(42, 47), _dt(d, 4, m, tz))

        # Stress hourly; high-stress window on the abnormal day.
        for h in range(6, 24):
            emit(STRESS, int(20 + 25 * rng.random()), _dt(d, h, 15, tz))
        if d == abnormal_day:
            for h in (14, 15, 16):
                emit(STRESS, rng.randint(82, 95), _dt(d, h, 30, tz))

        # Body battery: morning high, evening low.
        emit(BODY_BATTERY, rng.randint(60, 90), _dt(d, 7, 30, tz))
        emit(BODY_BATTERY, rng.randint(15, 40), _dt(d, 22, 30, tz))

        # Overnight SpO2 + respiration (00:00-05:00); a desaturation event on the abnormal day.
        for h in range(6):
            spo2 = rng.randint(94, 99)
            if d == abnormal_day and h == 3:
                spo2 = rng.randint(86, 89)
            emit(SPO2, spo2, _dt(d, h, 0, tz), meta={"window": "sleep"})
            emit(RESPIRATION, round(rng.uniform(12, 16), 1), _dt(d, h, 0, tz))

        # Sleep summary (recorded at wake ~06:30); poor sleep on the abnormal day.
        total = int(4.0 * 3600) if d == abnormal_day else int(rng.uniform(5.5, 7.5) * 3600)
        deep = int(total * 0.2)
        rem = int(total * 0.18)
        awake = int(total * 0.05)
        light = total - deep - rem - awake
        sleep_ts = _dt(d, 6, 30, tz)
        epoch = int(sleep_ts.timestamp())
        emit(SLEEP_DURATION, total, sleep_ts)
        for stage, secs in (("deep", deep), ("light", light), ("rem", rem), ("awake", awake)):
            emit(SLEEP_STAGE, secs, sleep_ts, meta={"stage": stage}, sample_id=f"{SOURCE}-{SLEEP_STAGE}-{stage}-{epoch}")

        # Blood pressure stand-in (real Garmin watches rarely produce BP); hypertensive spike on abnormal day.
        if include_bp:
            sys, dia = (rng.randint(150, 165), rng.randint(92, 100)) if d == abnormal_day else (rng.randint(118, 132), rng.randint(76, 86))
            bp_ts = _dt(d, 8, 0, tz)
            emit(BP_SYSTOLIC, sys, bp_ts)
            emit(BP_DIASTOLIC, dia, bp_ts)

    return out
