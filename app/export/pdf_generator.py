"""Board-ready PDF reports generated with ReportLab (charts drawn natively)."""
from __future__ import annotations

import html
import logging
import re
from pathlib import Path
from typing import Any, Dict, List

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (BaseDocTemplate, Frame, KeepTogether, PageBreak,
                                PageTemplate, Paragraph, Spacer, Table, TableStyle)
from reportlab.graphics.shapes import Drawing
from reportlab.graphics.charts.linecharts import HorizontalLineChart
from reportlab.graphics.charts.piecharts import Pie

from app.config import settings

logger = logging.getLogger("meridian.export.pdf")

NAVY = colors.HexColor("#0A1628")
NAVY2 = colors.HexColor("#111C32")
GOLD = colors.HexColor("#C9A84C")
IVORY = colors.HexColor("#EDE4D3")
SLATE = colors.HexColor("#64748B")
LIGHT = colors.HexColor("#F8FAFC")
GREEN = colors.HexColor("#059669")
RED = colors.HexColor("#E11D48")


def _styles():
    ss = getSampleStyleSheet()
    return {
        "title": ParagraphStyle("MeridianTitle", parent=ss["Title"], fontName="Helvetica-Bold",
                                fontSize=24, leading=29, textColor=NAVY, spaceAfter=6),
        "subtitle": ParagraphStyle("MeridianSub", parent=ss["Normal"], fontName="Helvetica",
                                   fontSize=10.5, leading=15, textColor=GOLD, spaceAfter=14),
        "h1": ParagraphStyle("MeridianH1", parent=ss["Heading1"], fontName="Helvetica-Bold",
                             fontSize=15, leading=19, textColor=NAVY, spaceBefore=14, spaceAfter=8),
        "h2": ParagraphStyle("MeridianH2", parent=ss["Heading2"], fontName="Helvetica-Bold",
                             fontSize=11.5, leading=15, textColor=NAVY2, spaceBefore=10, spaceAfter=5),
        "body": ParagraphStyle("MeridianBody", parent=ss["Normal"], fontName="Helvetica",
                               fontSize=9.2, leading=13.6, textColor=NAVY2,
                               alignment=TA_LEFT, spaceAfter=5),
        "small": ParagraphStyle("MeridianSmall", parent=ss["Normal"], fontName="Helvetica",
                                fontSize=7.6, leading=10.2, textColor=SLATE),
        "cell": ParagraphStyle("MeridianCell", parent=ss["Normal"], fontName="Helvetica",
                               fontSize=7.8, leading=10, textColor=NAVY2),
        "cellh": ParagraphStyle("MeridianCellH", parent=ss["Normal"], fontName="Helvetica-Bold",
                                fontSize=8, leading=10, textColor=colors.white),
        "center": ParagraphStyle("MeridianCenter", parent=ss["Normal"],
                                 fontName="Helvetica", fontSize=9, alignment=TA_CENTER,
                                 textColor=SLATE),
    }


def _clean(text: str) -> str:
    """Convert a small markdown subset into ReportLab-safe markup."""
    t = html.escape(text or "")
    t = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", t)
    t = re.sub(r"\*(.+?)\*", r"<i>\1</i>", t)
    t = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<link href="\2" color="#C9A84C">\1</link>', t)
    t = t.replace("&lt;br&gt;", "<br/>")
    return t


def _table(data: List[List[Any]], st, widths: List[float] | None = None) -> Table:
    body = [[Paragraph(_clean(str(c)), st["cellh"] if i == 0 else st["cell"])
             for c in row] for i, row in enumerate(data)]
    t = Table(body, colWidths=widths, repeatRows=1, hAlign="LEFT")
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.HexColor("#F4F6FA"), colors.white]),
        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#DCE3ED")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    return t


def _history_chart(history: List[dict]) -> Drawing:
    d = Drawing(460, 150)
    lc = HorizontalLineChart()
    lc.x, lc.y, lc.width, lc.height = 35, 22, 405, 112
    vals = [h["value"] for h in history[-8:]]
    lc.data = [vals]
    lc.categoryAxis.categoryNames = [str(h["year"]) for h in history[-8:]]
    lc.lines[0].strokeColor = GOLD
    lc.lines[0].strokeWidth = 2.4
    lc.lines[0].symbol = None
    lc.valueAxis.valueMin = 0
    lc.valueAxis.valueMax = max(vals) * 1.15 if vals else 1
    lc.categoryAxis.labels.fontSize = 7
    lc.valueAxis.labels.fontSize = 7
    d.add(lc)
    return d


def _share_pie(competitors: List[dict]) -> Drawing:
    d = Drawing(220, 150)
    pie = Pie()
    pie.x, pie.y, pie.width, pie.height = 20, 12, 120, 120
    pie.data = [c["share"] for c in competitors[:6]]
    pie.labels = [c["name"][:14] for c in competitors[:6]]
    pie.slices.strokeColor = colors.white
    pie.slices.strokeWidth = 1
    palette = [GOLD, NAVY2, colors.HexColor("#8B7CF6"), GREEN,
               colors.HexColor("#4C7BF3"), SLATE]
    # NOTE: pie.slices is a TypedPropertyCollection whose __getitem__ always
    # succeeds — iterating it directly never terminates. Index by a fixed range.
    for i in range(len(pie.data)):
        pie.slices[i].fillColor = palette[i % len(palette)]
    pie.sideLabels = 0
    d.add(pie)
    return d


def generate_pdf(report: Dict[str, Any], out_path: str | Path) -> str:
    """Write a complete, styled PDF. Returns the absolute path."""
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    st = _styles()
    d = report.get("researcher_output", {}).get("dataset") or {}
    a = report.get("analyst_output", {}) or {}
    f = report.get("forecast_output", {}) or {}
    fc = report.get("factcheck_output", {}) or {}
    w = report.get("writer_output", {}) or {}
    company = d.get("company") or report.get("company") or "Market Intelligence"
    sector = d.get("sector", "Market")
    region = d.get("region", report.get("region", "Global"))

    def _page(canvas, doc):
        canvas.saveState()
        w_, h_ = A4
        canvas.setFillColor(NAVY)
        canvas.rect(0, h_ - 18 * mm, w_, 18 * mm, stroke=0, fill=1)
        canvas.setFillColor(GOLD)
        canvas.setFont("Helvetica-Bold", 11)
        canvas.drawString(18 * mm, h_ - 12 * mm, "◆  MERIDIAN")
        canvas.setFillColor(IVORY)
        canvas.setFont("Helvetica", 8)
        canvas.drawRightString(w_ - 18 * mm, h_ - 12 * mm, "MARKET INTELLIGENCE, REDEFINED.")
        canvas.setStrokeColor(colors.HexColor("#DCE3ED"))
        canvas.line(18 * mm, 14 * mm, w_ - 18 * mm, 14 * mm)
        canvas.setFillColor(SLATE)
        canvas.setFont("Helvetica", 7.5)
        canvas.drawString(18 * mm, 9 * mm, f"Developed by {settings.developer}  ·  Meridian {settings.version}")
        canvas.drawRightString(w_ - 18 * mm, 9 * mm, f"Page {doc.page}")
        canvas.restoreState()

    doc = BaseDocTemplate(str(out), pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm,
                          topMargin=24 * mm, bottomMargin=18 * mm,
                          title=f"Meridian — {company} {sector} Report",
                          author=settings.developer)
    frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="main")
    doc.addPageTemplates([PageTemplate(id="meridian", frames=[frame], onPage=_page)])

    story: List[Any] = []
    story.append(Paragraph("MERIDIAN MARKET INTELLIGENCE", st["subtitle"]))
    story.append(Paragraph(f"{html.escape(company)}", st["title"]))
    story.append(Paragraph(f"{html.escape(sector)} · {html.escape(region)} · "
                           f"{d.get('period', report.get('period', '3Y'))} review",
                           st["subtitle"]))
    story.append(_table([
        ["Metric", "Value", "Metric", "Value"],
        ["Market size", f"${d.get('market_size_usd_b', 0):,.1f}B", "CAGR",
         f"{d.get('cagr_pct', 0):.1f}%"],
        ["Sources", str(len(d.get("sources", []))), "Reliability",
         f"{fc.get('reliability_score', 0)}/100"],
        ["Data mode", str(d.get("data_mode", "simulated")).title(), "Generated",
         str(d.get("as_of", ""))],
    ], st, [42 * mm, 44 * mm, 42 * mm, 44 * mm]))
    story.append(Spacer(1, 8))
    story.append(Paragraph("Executive Summary", st["h1"]))
    story.append(Paragraph(_clean(re.sub(r"\[S?\d+\]", "", w.get("executive_summary", ""))),
                           st["body"]))
    story.append(Spacer(1, 6))
    story.append(Paragraph("Market Trajectory (USD B)", st["h2"]))
    if d.get("history"):
        story.append(_history_chart(d["history"]))
    story.append(Paragraph("Competitive Share", st["h2"]))
    if d.get("competitors"):
        story.append(_share_pie(d["competitors"]))
    story.append(PageBreak())

    story.append(Paragraph("1. Market Overview & Sizing", st["h1"]))
    s = a.get("sizing", {})
    story.append(_table([["Metric", "Estimate"],
                         ["TAM", f"${s.get('TAM (USD B)', 0):,.1f}B"],
                         ["SAM", f"${s.get('SAM (USD B)', 0):,.1f}B"],
                         ["SOM", f"${s.get('SOM (USD B)', 0):,.1f}B"],
                         ["Base-year size", f"${d.get('market_size_usd_b', 0):,.1f}B"],
                         ["Trailing CAGR", f"{d.get('cagr_pct', 0):.1f}%"]],
                        st, [80 * mm, 92 * mm]))
    story.append(Paragraph("2. Competitive Landscape", st["h1"]))
    comp_rows = [["Company", "Share", "Revenue (USD B)", "Growth", "Sentiment"]]
    comp_rows += [[c["name"], f"{c['share']:.1f}%", f"{c['revenue_usd_b']:,.1f}",
                   f"{c['growth_pct']:+.1f}%", f"{c['sentiment']*100:.0f}/100"]
                  for c in d.get("competitors", [])]
    story.append(_table(comp_rows, st, [52 * mm, 22 * mm, 36 * mm, 30 * mm, 32 * mm]))
    story.append(Paragraph("3. SWOT", st["h1"]))
    swot_rows = [["Dimension", "Findings"]]
    swot_rows += [[k, "  •  ".join(v)] for k, v in (a.get("swot") or {}).items()]
    story.append(_table(swot_rows, st, [36 * mm, 136 * mm]))
    story.append(Paragraph("4. PESTLE", st["h1"]))
    story.append(_table([["Factor", "Impact", "Score", "Assessment"]] +
                        [[p["factor"], p["impact"], str(p["score"]), p["note"]]
                         for p in a.get("pestle", [])], st,
                        [26 * mm, 22 * mm, 16 * mm, 108 * mm]))
    story.append(Paragraph("5. Porter's Five Forces", st["h1"]))
    story.append(_table([["Force", "Intensity", "Assessment"]] +
                        [[p["force"], f"{p['intensity']}/5", p["note"]]
                         for p in a.get("porter", [])], st,
                        [48 * mm, 22 * mm, 102 * mm]))
    story.append(PageBreak())

    story.append(Paragraph("6. Twelve-Month Forecast", st["h1"]))
    story.append(_table([["Month", "Base", "Optimistic", "Pessimistic", "Confidence"]] +
                        [[r["month"], f"{r['base']:.1f}", f"{r['optimistic']:.1f}",
                          f"{r['pessimistic']:.1f}", f"{r['confidence']*100:.0f}%"]
                         for r in f.get("series", [])], st,
                        [30 * mm, 34 * mm, 38 * mm, 38 * mm, 32 * mm]))
    story.append(Paragraph(f"Method: {_clean(f.get('method', ''))}", st["small"]))
    story.append(Paragraph("7. Fact-Check & Reliability", st["h1"]))
    story.append(_table([["Claim", "Status", "Score", "Sources"]] +
                        [[c["claim"][:95], c["status"].replace("_", " "),
                          f"{c['score']}/100", ", ".join(c["sources"])]
                         for c in fc.get("claims", [])], st,
                        [88 * mm, 32 * mm, 20 * mm, 32 * mm]))
    story.append(Paragraph(_clean(fc.get("disclaimer", "")), st["small"]))
    story.append(Paragraph("8. Recommendations", st["h1"]))
    story.append(Paragraph("1. Defend the core with service-led differentiation. "
                           "2. Scale mid-market and SMB cohorts. 3. Dual-source critical inputs. "
                           "4. Fund measured adjacency bets. 5. Re-run intelligence quarterly.",
                           st["body"]))
    story.append(Paragraph("9. Sources", st["h1"]))
    story.append(_table([["Ref", "Publisher", "Type", "Reliability"]] +
                        [[x["id"], x["publisher"], x["type"], f"{x['reliability']}/100"]
                         for x in d.get("sources", [])], st,
                        [18 * mm, 62 * mm, 62 * mm, 30 * mm]))
    story.append(Spacer(1, 10))
    story.append(Paragraph(f"<i>Developed by {settings.developer} · Meridian "
                           f"{settings.version} · {settings.tagline}</i>", st["center"]))

    try:
        doc.build(story)
    except Exception as exc:
        logger.exception("Rich PDF build failed; writing a safe minimal PDF")
        _fallback_pdf(out, company, sector, str(exc))
    return str(out.resolve())


def _fallback_pdf(out: Path, company: str, sector: str, reason: str) -> None:
    """Guaranteed-valid minimal PDF if the rich layout ever fails."""
    from reportlab.pdfgen import canvas
    c = canvas.Canvas(str(out), pagesize=A4)
    c.setFillColor(NAVY)
    c.rect(0, A4[1] - 60, A4[0], 60, fill=1, stroke=0)
    c.setFillColor(GOLD)
    c.setFont("Helvetica-Bold", 20)
    c.drawString(50, A4[1] - 40, "MERIDIAN")
    c.setFillColor(NAVY)
    c.setFont("Helvetica-Bold", 16)
    c.drawString(50, A4[1] - 110, f"{company[:60]} — {sector[:40]}")
    c.setFont("Helvetica", 10)
    c.drawString(50, A4[1] - 145, "Executive report generated by Meridian.")
    c.drawString(50, A4[1] - 165, "The full interactive report is available in the dashboard.")
    c.setFont("Helvetica", 8)
    c.drawString(50, 50, f"Developed by {settings.developer}")
    c.save()
