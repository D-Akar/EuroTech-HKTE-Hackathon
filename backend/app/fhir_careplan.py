"""Parse FHIR CarePlan documents (JSON or XML) into human-readable context.

Pure functions, no I/O. Tolerant of FHIR R4 and R5 shapes and of slightly-off
real-world exports — we only extract the handful of fields a care agent needs,
never validate the whole resource.
"""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET

from .models import CarePlanActivity, CarePlanContext, CarePlanGoal


class CarePlanParseError(ValueError):
    """Raised when a document can't be parsed as a FHIR CarePlan."""


# --- Parsing: raw text -> JSON-shaped dict ----------------------------------


def parse_document(raw: str) -> dict:
    """Parse raw FHIR JSON or XML text into a JSON-shaped dict."""
    text = raw.strip()
    if not text:
        raise CarePlanParseError("Empty document.")
    if text[0] in "{[":
        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            raise CarePlanParseError(f"Invalid JSON: {e}") from e
    if text[0] == "<":
        try:
            root = ET.fromstring(text)
        except ET.ParseError as e:
            raise CarePlanParseError(f"Invalid XML: {e}") from e
        return _xml_to_dict(root)
    raise CarePlanParseError("Unrecognized format — expected FHIR JSON or XML.")


def _strip_ns(tag: str) -> str:
    return tag.split("}", 1)[1] if "}" in tag else tag


def _xml_to_dict(elem: ET.Element) -> dict:
    """Convert a FHIR XML resource element to its JSON representation."""
    node = _xml_element_to_value(elem)
    if not isinstance(node, dict):
        node = {}
    node["resourceType"] = _strip_ns(elem.tag)
    return node


def _xml_element_to_value(elem: ET.Element):
    """FHIR XML: primitives are ``<x value="..."/>``; repeats become arrays."""
    children = list(elem)
    value_attr = elem.get("value")
    if not children:
        return value_attr  # primitive (or None for empty elements)

    result: dict = {}
    if value_attr is not None:
        result["value"] = value_attr
    for child in children:
        key = _strip_ns(child.tag)
        child_value = _xml_element_to_value(child)
        if key in result:
            existing = result[key]
            if isinstance(existing, list):
                existing.append(child_value)
            else:
                result[key] = [existing, child_value]
        else:
            result[key] = child_value
    return result


# --- Locating the CarePlan + reference lookup -------------------------------


def _as_list(value) -> list:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def _index(res: dict, refs: dict) -> None:
    rid = res.get("id")
    rtype = res.get("resourceType")
    if rid and rtype:
        refs[f"{rtype}/{rid}"] = res


def locate_care_plan(resource: dict) -> tuple[dict, dict]:
    """Return ``(care_plan, refs)``.

    Accepts a bare CarePlan or a Bundle containing one. ``refs`` maps both
    ``'ResourceType/id'`` and contained ``'#id'`` keys to their resource dicts
    so goals/conditions/activities can be dereferenced during extraction.
    """
    refs: dict[str, dict] = {}
    care_plan: dict | None = None

    rtype = resource.get("resourceType")
    if rtype == "Bundle":
        for entry in _as_list(resource.get("entry")):
            res = entry.get("resource") if isinstance(entry, dict) else None
            if not isinstance(res, dict):
                continue
            _index(res, refs)
            if res.get("resourceType") == "CarePlan" and care_plan is None:
                care_plan = res
    elif rtype == "CarePlan":
        care_plan = resource
    else:
        raise CarePlanParseError(
            f"Expected a CarePlan or Bundle, got {rtype or 'unknown resource'}."
        )

    if care_plan is None:
        raise CarePlanParseError("No CarePlan found in the document.")

    for contained in _as_list(care_plan.get("contained")):
        if isinstance(contained, dict) and contained.get("id"):
            cid = contained["id"]
            refs[f"#{cid}"] = contained
            _index(contained, refs)
    return care_plan, refs


# --- Field extraction -------------------------------------------------------


def _codeable_text(cc) -> str | None:
    """Best human label from a CodeableConcept."""
    if not isinstance(cc, dict):
        return None
    if cc.get("text"):
        return cc["text"]
    for coding in _as_list(cc.get("coding")):
        if isinstance(coding, dict) and coding.get("display"):
            return coding["display"]
    return None


def _resolve(ref, refs: dict) -> dict | None:
    return refs.get(ref) if isinstance(ref, str) else None


def _reference_label(node: dict, refs: dict) -> str | None:
    """Resolve a Reference / R5 CodeableReference to a human label."""
    ref = node.get("reference")
    if isinstance(ref, dict):  # R5 CodeableReference
        target = _resolve(ref.get("reference"), refs)
        return _codeable_text((target or {}).get("code")) or ref.get("display")
    if isinstance(ref, str):  # R4 Reference
        target = _resolve(ref, refs)
        return _codeable_text((target or {}).get("code")) or node.get("display")
    return node.get("display")


def _period_text(period) -> tuple[str | None, str | None]:
    if not isinstance(period, dict):
        return None, None
    return period.get("start"), period.get("end")


def _addresses(care_plan: dict, refs: dict) -> list[str]:
    out: list[str] = []
    for addr in _as_list(care_plan.get("addresses")):
        if not isinstance(addr, dict):
            continue
        label = _reference_label(addr, refs) or _codeable_text(addr.get("concept"))
        if label:
            out.append(label)
    return out


def _goal_target(goal: dict) -> str | None:
    for t in _as_list(goal.get("target")):
        if not isinstance(t, dict):
            continue
        measure = _codeable_text(t.get("measure"))
        detail = t.get("detailString") or _codeable_text(t.get("detailCodeableConcept"))
        quantity = t.get("detailQuantity")
        if isinstance(quantity, dict) and quantity.get("value") is not None:
            unit = quantity.get("unit") or quantity.get("code") or ""
            detail = f"{quantity['value']} {unit}".strip()
        if measure and detail:
            return f"{measure}: {detail}"
        return detail or measure
    return None


def _goals(care_plan: dict, refs: dict) -> list[CarePlanGoal]:
    out: list[CarePlanGoal] = []
    for g in _as_list(care_plan.get("goal")):
        if not isinstance(g, dict):
            continue
        target = _resolve(g.get("reference"), refs)
        if isinstance(target, dict):
            desc = _codeable_text(target.get("description")) or g.get("display")
            tgt = _goal_target(target)
        else:
            desc, tgt = g.get("display"), None
        if desc:
            out.append(CarePlanGoal(description=desc, target=tgt))
    return out


def _scheduled_text(detail: dict) -> str | None:
    if detail.get("scheduledString"):
        return detail["scheduledString"]
    period = detail.get("scheduledPeriod")
    if isinstance(period, dict) and (period.get("start") or period.get("end")):
        return f"{period.get('start') or '?'} to {period.get('end') or '?'}"
    timing = detail.get("scheduledTiming")
    if isinstance(timing, dict):
        repeat = timing.get("repeat")
        if isinstance(repeat, dict):
            freq, per, unit = (
                repeat.get("frequency"),
                repeat.get("period"),
                repeat.get("periodUnit"),
            )
            if freq and per and unit:
                return f"{freq}x per {per} {unit}"
        return _codeable_text(timing.get("code"))
    return None


def _activity_ref_label(a: dict, refs: dict) -> str | None:
    planned = a.get("plannedActivityReference")
    if isinstance(planned, dict):
        target = _resolve(planned.get("reference"), refs)
        label = _codeable_text((target or {}).get("code")) or planned.get("display")
        if label:
            return label
    for perf in _as_list(a.get("performedActivity")):
        if isinstance(perf, dict):
            label = _codeable_text(perf.get("concept"))
            if label:
                return label
    return None


def _activities(care_plan: dict, refs: dict) -> list[CarePlanActivity]:
    out: list[CarePlanActivity] = []
    for a in _as_list(care_plan.get("activity")):
        if not isinstance(a, dict):
            continue
        detail = a.get("detail")
        if isinstance(detail, dict):  # R4
            desc = _codeable_text(detail.get("code")) or detail.get("description")
            status = detail.get("status")
            scheduled = _scheduled_text(detail)
        else:  # R5 planned/performed
            desc, status, scheduled = _activity_ref_label(a, refs), None, None
        if desc:
            out.append(
                CarePlanActivity(description=desc, status=status, scheduled=scheduled)
            )
    return out


def extract_care_plan(care_plan: dict, refs: dict) -> CarePlanContext:
    """Pull human-relevant fields and render prose."""
    categories = [c for c in (_codeable_text(c) for c in _as_list(care_plan.get("category"))) if c]
    title = care_plan.get("title") or (categories[0] if categories else None)
    start, end = _period_text(care_plan.get("period"))
    subject = care_plan.get("subject")
    subject_display = subject.get("display") if isinstance(subject, dict) else None
    notes = [
        n["text"]
        for n in _as_list(care_plan.get("note"))
        if isinstance(n, dict) and n.get("text")
    ]

    ctx = CarePlanContext(
        title=title,
        status=care_plan.get("status"),
        intent=care_plan.get("intent"),
        description=care_plan.get("description"),
        categories=categories,
        subject_display=subject_display,
        period_start=start,
        period_end=end,
        addresses=_addresses(care_plan, refs),
        goals=_goals(care_plan, refs),
        activities=_activities(care_plan, refs),
        notes=notes,
        rendered_text="",
    )
    ctx.rendered_text = render_care_plan_text(ctx)
    return ctx


def render_care_plan_text(ctx: CarePlanContext) -> str:
    """Deterministic prose block for the agent; omits absent sections."""
    lines: list[str] = []
    meta = []
    if ctx.status:
        meta.append(f"status: {ctx.status}")
    if ctx.intent:
        meta.append(f"intent: {ctx.intent}")
    suffix = f" ({', '.join(meta)})" if meta else ""
    lines.append(f'Care plan: "{ctx.title or "Care plan"}"{suffix}.')

    if ctx.description:
        lines.append(ctx.description)
    if ctx.period_start or ctx.period_end:
        lines.append(f"Covers {ctx.period_start or 'unknown'} to {ctx.period_end or 'ongoing'}.")
    if ctx.categories:
        lines.append(f"Category: {', '.join(ctx.categories)}.")
    if ctx.addresses:
        lines.append(f"Addresses: {', '.join(ctx.addresses)}.")
    if ctx.goals:
        lines.append("Goals:")
        for g in ctx.goals:
            target = f" (target: {g.target})" if g.target else ""
            lines.append(f"- {g.description}{target}")
    if ctx.activities:
        lines.append("Planned activities:")
        for a in ctx.activities:
            status = f"[{a.status}] " if a.status else ""
            sched = f" — {a.scheduled}" if a.scheduled else ""
            lines.append(f"- {status}{a.description}{sched}")
    if ctx.notes:
        lines.append("Notes: " + " ".join(ctx.notes))
    return "\n".join(lines)
