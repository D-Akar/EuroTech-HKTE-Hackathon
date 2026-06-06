"""Render a clinician-ready patient report to PDF bytes with reportlab.

Pure presentation: it receives a patient, a pre-computed ``ReportSummary`` and the raw
history, and returns PDF ``bytes``. No data access and no business logic live here, so
the layout can change without touching how summaries are derived.
"""

from __future__ import annotations

from datetime import datetime
from io import BytesIO

from reportlab.graphics.charts.lineplots import LinePlot
from reportlab.graphics.shapes import Drawing
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from .models import CarePlanContext, CheckIn, MedicalProfile, Patient, WearableReading
from .report_summary import ReportSummary, Trend, VitalCard

# Colorblind-safe-leaning status palette; always paired with the text label.
_STATUS_COLOR = {
    "stable": colors.HexColor("#2E7D32"),
    "attention": colors.HexColor("#B26A00"),
    "urgent": colors.HexColor("#C62828"),
}
_DIRECTION_COLOR = {
    "improving": colors.HexColor("#2E7D32"),
    "worsening": colors.HexColor("#C62828"),
    "stable": colors.HexColor("#5F6368"),
}
_SEVERITY_COLOR = {
    "critical": colors.HexColor("#C62828"),
    "warning": colors.HexColor("#B26A00"),
    "info": colors.HexColor("#5F6368"),
}
_INK = colors.HexColor("#1A1A1A")
_MUTED = colors.HexColor("#5F6368")
_RULE = colors.HexColor("#D7DBE0")


def _h(c: colors.Color) -> str:
    """A '#RRGGBB' string for use inside reportlab inline font markup."""
    return "#%02X%02X%02X" % (int(c.red * 255), int(c.green * 255), int(c.blue * 255))


def _styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "title", parent=base["Title"], fontSize=20, textColor=_INK, spaceAfter=2
        ),
        "meta": ParagraphStyle(
            "meta", parent=base["Normal"], fontSize=10, textColor=_MUTED
        ),
        "section": ParagraphStyle(
            "section",
            parent=base["Heading2"],
            fontSize=12,
            textColor=_INK,
            spaceBefore=14,
            spaceAfter=6,
        ),
        "body": ParagraphStyle(
            "body", parent=base["Normal"], fontSize=10, textColor=_INK, leading=14
        ),
        "cell": ParagraphStyle(
            "cell", parent=base["Normal"], fontSize=9, textColor=_INK, leading=12
        ),
        "footer": ParagraphStyle(
            "footer", parent=base["Normal"], fontSize=8, textColor=_MUTED
        ),
    }


def _sparkline(series: list[float], color: colors.Color) -> Drawing:
    """A tiny line chart of the metric over the window."""
    w, h = 42 * mm, 12 * mm
    d = Drawing(w, h)
    if len(series) < 2:
        return d
    plot = LinePlot()
    plot.x, plot.y = 2, 2
    plot.width, plot.height = w - 4, h - 4
    plot.data = [list(enumerate(series))]
    plot.lines[0].strokeColor = color
    plot.lines[0].strokeWidth = 1.5
    plot.joinedLines = 1
    lo, hi = min(series), max(series)
    pad = (hi - lo) * 0.15 or 1.0
    plot.yValueAxis.valueMin = lo - pad
    plot.yValueAxis.valueMax = hi + pad
    plot.xValueAxis.visible = 0
    plot.yValueAxis.visible = 0
    plot.xValueAxis.visibleGrid = 0
    plot.yValueAxis.visibleGrid = 0
    d.add(plot)
    return d


def _header(patient: Patient, styles: dict[str, ParagraphStyle]) -> list:
    status = patient.status.value if hasattr(patient.status, "value") else str(patient.status)
    status_color = _STATUS_COLOR.get(status, _MUTED)
    status_para = Paragraph(
        f'<font color="{_h(status_color)}"><b>{status.upper()}</b></font>',
        styles["meta"],
    )
    left = [
        Paragraph(patient.name, styles["title"]),
        Paragraph(
            f"Age {patient.age} &nbsp;·&nbsp; {patient.district} &nbsp;·&nbsp; {patient.practice}",
            styles["meta"],
        ),
        Spacer(1, 4),
        status_para,
    ]
    right = Paragraph(
        f"Clinician report<br/>{datetime.now():%d %b %Y}", styles["meta"]
    )
    table = Table([[left, right]], colWidths=[120 * mm, 50 * mm])
    table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("ALIGN", (1, 0), (1, 0), "RIGHT"),
                ("LINEBELOW", (0, 0), (-1, -1), 1, _RULE),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
            ]
        )
    )
    return [table]


def _checkins_table(checkins: list[CheckIn], styles: dict[str, ParagraphStyle]) -> Table:
    head = ["Date", "Answered", "Mood", "Pain", "Notes"]
    rows = [head]
    for c in checkins[:5]:  # newest-first, most recent five
        rows.append(
            [
                Paragraph(f"{c.date:%d %b}", styles["cell"]),
                Paragraph("Yes" if c.answered else "No", styles["cell"]),
                Paragraph(c.mood, styles["cell"]),
                Paragraph(f"{c.pain_level}/10", styles["cell"]),
                Paragraph(c.notes, styles["cell"]),
            ]
        )
    table = Table(rows, colWidths=[18 * mm, 18 * mm, 24 * mm, 14 * mm, 96 * mm])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F2F4F7")),
                ("TEXTCOLOR", (0, 0), (-1, 0), _INK),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, 0), 9),
                ("LINEBELOW", (0, 0), (-1, -1), 0.5, _RULE),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    return table


def _trends_table(trends: list[Trend], styles: dict[str, ParagraphStyle]) -> Table:
    rows = []
    for t in trends:
        color = _DIRECTION_COLOR[t.direction]
        current = f"{t.current:g}{(' ' + t.unit) if t.unit else ''}"
        movement = Paragraph(
            f'<font color="{_h(color)}"><b>{t.arrow} {t.direction}</b></font>',
            styles["cell"],
        )
        rows.append(
            [
                Paragraph(f"<b>{t.label}</b>", styles["cell"]),
                Paragraph(current, styles["cell"]),
                movement,
                _sparkline(t.series, color),
            ]
        )
    table = Table(rows, colWidths=[40 * mm, 30 * mm, 50 * mm, 50 * mm])
    table.setStyle(
        TableStyle(
            [
                ("LINEBELOW", (0, 0), (-1, -1), 0.5, _RULE),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    return table


def _vitals_cards(cards: list[VitalCard], styles: dict[str, ParagraphStyle]) -> Table | Paragraph:
    """A single row of equal-width "current value" cards (HR/Sleep/Steps + SpO2/Stress)."""
    if not cards:
        return Paragraph("No wearable data available.", styles["body"])

    def cell(c: VitalCard):
        value = f"{c.value}{(' ' + c.unit) if c.unit else ''}"
        return [
            Paragraph(f"<b>{value}</b>", ParagraphStyle("v", fontSize=15, textColor=_INK)),
            Paragraph(c.label, styles["meta"]),
        ]

    content_width = 170 * mm
    col = content_width / len(cards)
    table = Table([[cell(c) for c in cards]], colWidths=[col] * len(cards))
    table.setStyle(
        TableStyle(
            [
                ("BOX", (0, 0), (-1, -1), 0.5, _RULE),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, _RULE),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
            ]
        )
    )
    return table


def _snapshot(
    summary: ReportSummary,
    alerts: list[dict] | None,
    styles: dict[str, ParagraphStyle],
) -> list:
    """The page-1 "Current status" band: headline, active alerts, vital cards."""
    flow: list = [Paragraph("Current status", styles["section"])]
    flow.append(
        Paragraph(
            f"<b>{summary.headline}</b>",
            ParagraphStyle("headline", parent=styles["body"], fontSize=12, leading=16),
        )
    )

    active = [a for a in (alerts or []) if a.get("severity") in _SEVERITY_COLOR]
    if active:
        flow.append(Spacer(1, 4))
        for a in active:
            color = _SEVERITY_COLOR[a["severity"]]
            flow.append(
                Paragraph(
                    f'<font color="{_h(color)}"><b>{a["severity"].upper()}</b></font> '
                    f'{a.get("message", "")}',
                    styles["cell"],
                )
            )

    flow.append(Spacer(1, 8))
    flow.append(_vitals_cards(summary.snapshot_vitals, styles))
    return flow


def _clinical_context(
    profile: MedicalProfile, styles: dict[str, ParagraphStyle]
) -> list:
    """Chronic conditions, active medications and allergies from the FHIR record."""
    flow: list = [Paragraph("Clinical context", styles["section"])]

    if profile.chronic_conditions:
        items = ", ".join(
            f"{c.name}{f' (since {c.onset_date})' if c.onset_date else ''}"
            for c in profile.chronic_conditions
        )
        flow.append(Paragraph(f"<b>Chronic conditions:</b> {items}", styles["body"]))
    if profile.active_medications:
        items = ", ".join(
            f"{m.name}{f' — {m.frequency}' if m.frequency else ''}"
            for m in profile.active_medications
        )
        flow.append(Paragraph(f"<b>Active medications:</b> {items}", styles["body"]))
    if profile.allergies:
        items = ", ".join(
            f"{a.substance}{f' ({a.criticality})' if a.criticality else ''}"
            for a in profile.allergies
        )
        flow.append(Paragraph(f"<b>Allergies:</b> {items}", styles["body"]))

    # Heading only with no rows reads as an error; show an explicit empty state instead.
    if len(flow) == 1:
        flow.append(Paragraph("No clinical record details available.", styles["body"]))
    return flow


def _care_plan_section(
    care_plan: CarePlanContext,
    styles: dict[str, ParagraphStyle],
    progress: str | None = None,
) -> list:
    flow: list = [Paragraph("Care plan", styles["section"])]
    if progress:
        color = _DIRECTION_COLOR["worsening"] if "off track" in progress else (
            _DIRECTION_COLOR["improving"] if "on track" in progress else _MUTED
        )
        flow.append(
            Paragraph(f'<font color="{_h(color)}"><b>{progress}</b></font>', styles["body"])
        )
        flow.append(Spacer(1, 4))
    meta = []
    if care_plan.status:
        meta.append(f"status {care_plan.status}")
    if care_plan.intent:
        meta.append(f"intent {care_plan.intent}")
    title = care_plan.title or "Care plan"
    heading = f"<b>{title}</b>" + (f" ({', '.join(meta)})" if meta else "")
    flow.append(Paragraph(heading, styles["body"]))
    if care_plan.description:
        flow.append(Paragraph(care_plan.description, styles["body"]))
    if care_plan.period_start or care_plan.period_end:
        flow.append(Paragraph(
            f"Covers {care_plan.period_start or 'unknown'} to "
            f"{care_plan.period_end or 'ongoing'}.", styles["body"]))
    if care_plan.addresses:
        flow.append(Paragraph("Addresses: " + ", ".join(care_plan.addresses), styles["body"]))
    if care_plan.goals:
        flow.append(Paragraph("<b>Goals</b>", styles["body"]))
        for g in care_plan.goals:
            target = f" (target: {g.target})" if g.target else ""
            flow.append(Paragraph(f"• {g.description}{target}", styles["cell"]))
    if care_plan.activities:
        flow.append(Paragraph("<b>Planned activities</b>", styles["body"]))
        for a in care_plan.activities:
            status = f"[{a.status}] " if a.status else ""
            sched = f" - {a.scheduled}" if a.scheduled else ""
            flow.append(Paragraph(f"• {status}{a.description}{sched}", styles["cell"]))
    if care_plan.notes:
        flow.append(Paragraph("Notes: " + " ".join(care_plan.notes), styles["body"]))
    return flow


def build_report_pdf(
    patient: Patient,
    summary: ReportSummary,
    checkins: list[CheckIn],
    wearables: list[WearableReading],
    *,
    profile: MedicalProfile | None = None,
    alerts: list[dict] | None = None,
    care_plan: CarePlanContext | None = None,
) -> bytes:
    """Assemble the report and return the PDF as bytes.

    Page 1 leads with current status + trends; page 2 carries check-ins, clinical
    context and the care plan.
    """
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        topMargin=18 * mm,
        bottomMargin=16 * mm,
        leftMargin=20 * mm,
        rightMargin=20 * mm,
        title=f"Clinician report - {patient.name}",
    )
    styles = _styles()
    flow: list = []

    # --- Page 1: current status & trends --------------------------------------
    flow += _header(patient, styles)
    flow += _snapshot(summary, alerts, styles)

    flow.append(Paragraph("Health trends — recent window", styles["section"]))
    flow.append(Paragraph(summary.status_narrative, styles["body"]))
    flow.append(Spacer(1, 6))
    if summary.trends:
        flow.append(_trends_table(summary.trends, styles))

    flow.append(PageBreak())

    # --- Page 2: detail & context ---------------------------------------------
    flow.append(Paragraph("Recent check-ins", styles["section"]))
    flow.append(Paragraph(summary.checkins_narrative, styles["body"]))
    flow.append(Spacer(1, 6))
    flow.append(_checkins_table(checkins, styles))

    if profile is not None:
        flow += _clinical_context(profile, styles)

    if care_plan is not None:
        flow += _care_plan_section(care_plan, styles, progress=summary.careplan_progress)

    flow.append(Spacer(1, 16))
    flow.append(
        Paragraph(
            "Generated mock report - not for clinical use. "
            f"Generated {datetime.now():%d %b %Y %H:%M}.",
            styles["footer"],
        )
    )

    doc.build(flow)
    return buf.getvalue()
