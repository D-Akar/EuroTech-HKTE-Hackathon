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
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from .models import CheckIn, Patient, WearableReading
from .report_summary import ReportSummary, Trend

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


def _vitals_row(wearables: list[WearableReading], styles: dict[str, ParagraphStyle]) -> Table | Paragraph:
    if not wearables:
        return Paragraph("No wearable data available.", styles["body"])
    latest = wearables[0]  # newest-first

    def card(value: str, label: str):
        return [
            Paragraph(f"<b>{value}</b>", ParagraphStyle("v", fontSize=16, textColor=_INK)),
            Paragraph(label, styles["meta"]),
        ]

    table = Table(
        [
            [
                card(f"{latest.heart_rate} bpm", "Heart rate"),
                card(f"{latest.steps:,}", "Steps (latest)"),
                card(f"{latest.sleep_hours} h", "Sleep"),
            ]
        ],
        colWidths=[57 * mm, 57 * mm, 56 * mm],
    )
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


def build_report_pdf(
    patient: Patient,
    summary: ReportSummary,
    checkins: list[CheckIn],
    wearables: list[WearableReading],
) -> bytes:
    """Assemble the report and return the PDF as bytes."""
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        topMargin=18 * mm,
        bottomMargin=16 * mm,
        leftMargin=20 * mm,
        rightMargin=20 * mm,
        title=f"Clinician report — {patient.name}",
    )
    styles = _styles()
    flow: list = []

    flow += _header(patient, styles)

    flow.append(Paragraph("Latest check-ins", styles["section"]))
    flow.append(Paragraph(summary.checkins_narrative, styles["body"]))
    flow.append(Spacer(1, 6))
    flow.append(_checkins_table(checkins, styles))

    flow.append(Paragraph("Health status — recent trend", styles["section"]))
    flow.append(Paragraph(summary.status_narrative, styles["body"]))
    flow.append(Spacer(1, 6))
    if summary.trends:
        flow.append(_trends_table(summary.trends, styles))

    flow.append(Paragraph("At-a-glance vitals", styles["section"]))
    flow.append(_vitals_row(wearables, styles))

    flow.append(Spacer(1, 16))
    flow.append(
        Paragraph(
            "Generated mock report — not for clinical use. "
            f"Generated {datetime.now():%d %b %Y %H:%M}.",
            styles["footer"],
        )
    )

    doc.build(flow)
    return buf.getvalue()
