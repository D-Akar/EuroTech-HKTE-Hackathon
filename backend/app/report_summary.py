"""Turn a patient's raw history into a clinician-readable summary.

This is the *mock brain* of the PDF report: it derives short narrative strings and
per-metric trends from the existing check-in and wearable data using simple,
deterministic rules. There is no I/O and no PDF dependency here, so the logic can be
unit-tested on its own — and later swapped for real data or an LLM-written narrative
without touching the renderer or the endpoint.

Check-ins and wearables arrive newest-first (see ``data._build_history``); we reverse
into oldest→newest order before reasoning about trends.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from .models import CheckIn, WearableReading
from .summary import compute_summary

Direction = Literal["improving", "worsening", "stable"]


class Trend(BaseModel):
    """How one metric is moving across the recent window."""

    label: str
    unit: str
    current: float
    direction: Direction  # clinical interpretation
    arrow: str  # "↑" / "↓" / "→" — actual movement of the value
    series: list[float]  # oldest→newest, for the mini chart


class VitalCard(BaseModel):
    """A pre-formatted "current status" snapshot card for the report's first page."""

    label: str
    value: str
    unit: str


class ReportSummary(BaseModel):
    headline: str  # one-line, plain-language "what matters right now"
    snapshot_vitals: list[VitalCard]
    checkins_narrative: str
    status_narrative: str
    trends: list[Trend]
    careplan_progress: str | None = None  # only set when a care plan exists


def _classify(series: list[float], higher_is_better: bool) -> tuple[Direction, str]:
    """Compare the older half of a series to the newer half.

    Returns the clinical direction and an arrow showing the raw value movement.
    """
    if len(series) < 2:
        return "stable", "→"

    mid = len(series) // 2
    older = series[:mid] or series[:1]
    newer = series[mid:] or series[-1:]
    older_avg = sum(older) / len(older)
    newer_avg = sum(newer) / len(newer)
    delta = newer_avg - older_avg

    # Significant if the move exceeds 5% of the older average (with a small floor so
    # near-zero baselines like pain=0 don't make every wobble look significant).
    threshold = max(abs(older_avg) * 0.05, 0.5)
    if abs(delta) < threshold:
        return "stable", "→"

    went_up = delta > 0
    arrow = "↑" if went_up else "↓"
    improving = went_up if higher_is_better else not went_up
    return ("improving" if improving else "worsening"), arrow


def _trend(
    label: str,
    unit: str,
    series: list[float],
    *,
    higher_is_better: bool,
) -> Trend:
    direction, arrow = _classify(series, higher_is_better)
    current = series[-1] if series else 0.0
    return Trend(
        label=label,
        unit=unit,
        current=round(current, 1),
        direction=direction,
        arrow=arrow,
        series=[round(v, 1) for v in series],
    )


def _checkins_narrative(checkins: list[CheckIn]) -> str:
    if not checkins:
        return "No check-in calls recorded in the recent window."

    answered = [c for c in checkins if c.answered]
    n = len(checkins)
    parts = [f"Answered {len(answered)} of the last {n} check-in call{'s' if n != 1 else ''}."]

    latest = checkins[0]  # newest-first
    if latest.answered:
        parts.append(
            f"Most recent call ({latest.date:%d %b}): mood “{latest.mood}”, "
            f"pain {latest.pain_level}/10."
        )
        if latest.notes:
            parts.append(f"Note: “{latest.notes}”")
    else:
        parts.append(f"Most recent call ({latest.date:%d %b}) went unanswered.")

    missed = n - len(answered)
    if missed and latest.answered:
        parts.append(f"{missed} call{'s' if missed != 1 else ''} unanswered in this window.")

    return " ".join(parts)


def _status_narrative(trends: list[Trend]) -> str:
    worsening = [t.label.lower() for t in trends if t.direction == "worsening"]
    improving = [t.label.lower() for t in trends if t.direction == "improving"]

    clauses: list[str] = []
    if worsening:
        clauses.append(f"{_join(worsening)} {'is' if len(worsening) == 1 else 'are'} worsening")
    if improving:
        clauses.append(f"{_join(improving)} {'is' if len(improving) == 1 else 'are'} improving")

    if not clauses:
        return "Health indicators are broadly stable across the recent window."
    return "Recent trend: " + "; ".join(clauses) + "."


def _join(items: list[str]) -> str:
    if len(items) == 1:
        return items[0]
    return ", ".join(items[:-1]) + " and " + items[-1]


def _headline(trends: list[Trend], alerts: list[dict] | None) -> str:
    """The single "what matters right now" line that opens the report."""
    critical = [a for a in (alerts or []) if a.get("severity") == "critical"]
    if critical:
        return f"{critical[0].get('message', 'Critical alert')} — needs attention."

    worsening = [t.label.lower() for t in trends if t.direction == "worsening"]
    improving = [t.label.lower() for t in trends if t.direction == "improving"]
    if worsening:
        tail = f" {_join(improving)} improving." if improving else ""
        return f"{_join(worsening).capitalize()} worsening.{tail}"
    if improving:
        return f"{_join(improving).capitalize()} improving; no metrics worsening."
    return "Indicators broadly stable across the recent window."


def _snapshot_vitals(
    wearables: list[WearableReading],
    vitals: list[dict] | None,
) -> list[VitalCard]:
    """Latest dailies (HR/sleep/steps) plus rich-vital averages (SpO2/stress) when present."""
    cards: list[VitalCard] = []
    if wearables:
        latest = wearables[0]  # newest-first
        cards.append(VitalCard(label="Heart rate", value=str(latest.heart_rate), unit="bpm"))
        cards.append(VitalCard(label="Sleep", value=f"{latest.sleep_hours:g}", unit="h"))
        cards.append(VitalCard(label="Steps", value=f"{latest.steps:,}", unit=""))

    stats = compute_summary(wearables, vitals or [])
    spo2 = stats.get("spo2")
    if spo2:
        cards.append(VitalCard(label="SpO2 (avg)", value=f"{spo2['avg']:g}", unit="%"))
    stress = stats.get("stress")
    if stress:
        cards.append(VitalCard(label="Stress (avg)", value=f"{stress['avg']:g}", unit=""))
    return cards


def _careplan_progress(trends: list[Trend], alerts: list[dict] | None) -> str:
    """A transparent heuristic read of whether monitoring supports the care-plan goals.

    Not a clinical determination — it weighs how the monitored metrics are moving and
    whether any vital crossed a critical threshold.
    """
    critical = [a for a in (alerts or []) if a.get("severity") == "critical"]
    worsening = [t.label.lower() for t in trends if t.direction == "worsening"]
    improving = [t.label.lower() for t in trends if t.direction == "improving"]

    if critical or (len(worsening) >= 2 and not improving):
        detail = (
            f"{_join(worsening)} moving the wrong way"
            if worsening
            else "active critical alerts"
        )
        return (
            "Based on recent monitoring, the patient appears off track relative to "
            f"care-plan goals ({detail})."
        )
    if improving and len(improving) >= len(worsening):
        return (
            "Based on recent monitoring, the patient appears on track relative to "
            f"care-plan goals ({_join(improving)} improving)."
        )
    return (
        "Based on recent monitoring, the patient is showing mixed progress relative to "
        "care-plan goals."
    )


def build_summary(
    checkins: list[CheckIn],
    wearables: list[WearableReading],
    vitals: list[dict] | None = None,
    *,
    care_plan: object | None = None,
    alerts: list[dict] | None = None,
) -> ReportSummary:
    """Derive narratives + trends from a patient's recent history (newest-first input).

    ``vitals`` are the rich Garmin samples (SpO2/stress) used for the snapshot; ``alerts``
    and ``care_plan`` feed the headline and care-plan progress read when available.
    """
    # Oldest→newest for trend reasoning and charts.
    checkins_old_to_new = list(reversed(checkins))
    wearables_old_to_new = list(reversed(wearables))

    pain = [float(c.pain_level) for c in checkins_old_to_new]
    answer = [1.0 if c.answered else 0.0 for c in checkins_old_to_new]
    hr = [float(w.heart_rate) for w in wearables_old_to_new]
    sleep = [w.sleep_hours for w in wearables_old_to_new]
    steps = [float(w.steps) for w in wearables_old_to_new]

    trends: list[Trend] = []
    if pain:
        trends.append(_trend("Pain level", "/10", pain, higher_is_better=False))
    if hr:
        trends.append(_trend("Heart rate", "bpm", hr, higher_is_better=False))
    if sleep:
        trends.append(_trend("Sleep", "h", sleep, higher_is_better=True))
    if steps:
        trends.append(_trend("Steps", "/day", steps, higher_is_better=True))
    if answer:
        trends.append(_trend("Call answer rate", "", answer, higher_is_better=True))

    return ReportSummary(
        headline=_headline(trends, alerts),
        snapshot_vitals=_snapshot_vitals(wearables, vitals),
        checkins_narrative=_checkins_narrative(checkins),
        status_narrative=_status_narrative(trends),
        trends=trends,
        careplan_progress=(
            _careplan_progress(trends, alerts) if care_plan is not None else None
        ),
    )
