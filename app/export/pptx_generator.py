"""Presentation-ready PowerPoint deck generated with python-pptx."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List

from pptx import Presentation
from pptx.chart.data import CategoryChartData
from pptx.dml.color import RGBColor
from pptx.enum.chart import XL_CHART_TYPE, XL_LEGEND_POSITION
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.util import Inches, Pt

from app.config import settings

logger = logging.getLogger("meridian.export.pptx")

NAVY = RGBColor(0x0A, 0x16, 0x28)
NAVY2 = RGBColor(0x11, 0x1C, 0x32)
CARD = RGBColor(0x1A, 0x27, 0x44)
GOLD = RGBColor(0xC9, 0xA8, 0x4C)
IVORY = RGBColor(0xED, 0xE4, 0xD3)
WHITE = RGBColor(0xF8, 0xFA, 0xFC)
SLATE = RGBColor(0x94, 0xA3, 0xB8)
GREEN = RGBColor(0x05, 0x96, 0x69)

W, H = Inches(13.333), Inches(7.5)


def _blank(prs):
    return prs.slides.add_slide(prs.slide_layouts[6])


def _rect(slide, x, y, w, h, color, line=None):
    from pptx.enum.shapes import MSO_SHAPE
    shp = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, x, y, w, h)
    shp.fill.solid()
    shp.fill.fore_color.rgb = color
    if line:
        shp.line.color.rgb = line
        shp.line.width = Pt(0.8)
    else:
        shp.line.fill.background()
    shp.adjustments[0] = 0.08
    return shp


def _text(slide, x, y, w, h, text, size=18, bold=False, color=WHITE,
          align=PP_ALIGN.LEFT, font="Arial"):
    box = slide.shapes.add_textbox(x, y, w, h)
    tf = box.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    p = tf.paragraphs[0]
    p.alignment = align
    r = p.add_run()
    r.text = text
    r.font.size = Pt(size)
    r.font.bold = bold
    r.font.name = font
    r.font.color.rgb = color
    return box


def _chrome(slide, title: str, subtitle: str = "", number: int = 2):
    bg = slide.background.fill
    bg.solid()
    bg.fore_color.rgb = NAVY
    _rect(slide, Inches(0), Inches(0), W, Inches(0.09), GOLD)
    _text(slide, Inches(0.55), Inches(0.22), Inches(5), Inches(0.4),
          "◆  MERIDIAN", 14, True, GOLD)
    _text(slide, Inches(9.0), Inches(0.22), Inches(3.8), Inches(0.4),
          "MARKET INTELLIGENCE, REDEFINED.", 9, False, SLATE, PP_ALIGN.RIGHT)
    _text(slide, Inches(0.55), Inches(0.75), Inches(12), Inches(0.6),
          title, 28, True, WHITE)
    if subtitle:
        _text(slide, Inches(0.58), Inches(1.38), Inches(12), Inches(0.35),
              subtitle, 12, False, SLATE)
    _text(slide, Inches(0.55), Inches(7.05), Inches(8), Inches(0.3),
          f"Developed by {settings.developer}", 8, False, SLATE)
    _text(slide, Inches(11.6), Inches(7.05), Inches(1.2), Inches(0.3),
          f"{number:02d}", 9, False, GOLD, PP_ALIGN.RIGHT)


def _kpi(slide, x, label, value, delta="", accent=GOLD):
    _rect(slide, x, Inches(1.95), Inches(2.85), Inches(1.25), CARD,
          RGBColor(0x2A, 0x3B, 0x5C))
    _text(slide, x + Inches(0.2), Inches(2.02), Inches(2.5), Inches(0.3),
          label.upper(), 9, True, SLATE)
    _text(slide, x + Inches(0.2), Inches(2.33), Inches(2.5), Inches(0.55),
          value, 25, True, accent)
    if delta:
        _text(slide, x + Inches(0.2), Inches(2.85), Inches(2.5), Inches(0.25),
              delta, 9, False, GREEN)


def _bullets(slide, x, y, w, h, items: List[str], size=14):
    box = slide.shapes.add_textbox(x, y, w, h)
    tf = box.text_frame
    tf.word_wrap = True
    for i, item in enumerate(items):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.text = "•  " + item
        p.space_after = Pt(12)
        for r in p.runs:
            r.font.size = Pt(size)
            r.font.color.rgb = WHITE
            r.font.name = "Arial"
    return box


def generate_pptx(report: Dict[str, Any], out_path: str | Path) -> str:
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    d = (report.get("researcher_output") or {}).get("dataset") or {}
    a = report.get("analyst_output") or {}
    f = report.get("forecast_output") or {}
    fc = report.get("factcheck_output") or {}
    w = report.get("writer_output") or {}
    company = d.get("company") or report.get("company") or "Market Intelligence"
    sector = d.get("sector", "Market")
    region = d.get("region", report.get("region", "Global"))

    prs = Presentation()
    prs.slide_width, prs.slide_height = W, H

    # 1 — Cover
    s = _blank(prs)
    bg = s.background.fill
    bg.solid(); bg.fore_color.rgb = NAVY
    _rect(s, Inches(0), Inches(0), Inches(0.14), H, GOLD)
    _rect(s, Inches(8.6), Inches(0), Inches(4.75), H, NAVY2)
    _text(s, Inches(0.8), Inches(0.75), Inches(7), Inches(0.5),
          "◆  MERIDIAN", 20, True, GOLD)
    _text(s, Inches(0.8), Inches(2.05), Inches(7.4), Inches(1.5),
          company[:60], 40, True, WHITE)
    _text(s, Inches(0.85), Inches(3.55), Inches(7.2), Inches(0.5),
          f"{sector}", 20, False, GOLD)
    _text(s, Inches(0.85), Inches(4.2), Inches(7.2), Inches(0.5),
          f"{region}  ·  {d.get('period', '3Y')} review  ·  {d.get('as_of', '')}",
          12, False, SLATE)
    _text(s, Inches(9.1), Inches(2.0), Inches(3.8), Inches(0.4),
          "MARKET SNAPSHOT", 11, True, GOLD)
    for i, (label, value) in enumerate([
        ("MARKET SIZE", f"${d.get('market_size_usd_b', 0):,.1f}B"),
        ("CAGR", f"{d.get('cagr_pct', 0):.1f}%"),
        ("SOURCES", str(len(d.get("sources", [])))),
        ("RELIABILITY", f"{fc.get('reliability_score', 0)}/100"),
    ]):
        y = 2.65 + i * 0.92
        _text(s, Inches(9.1), Inches(y), Inches(3.7), Inches(0.25), label, 9, True, SLATE)
        _text(s, Inches(9.1), Inches(y + 0.25), Inches(3.7), Inches(0.5), value, 22, True, IVORY)
    _text(s, Inches(0.85), Inches(6.85), Inches(8), Inches(0.3),
          f"Developed by {settings.developer}  ·  {settings.tagline}", 9, False, SLATE)

    # 2 — Executive summary
    s = _blank(prs)
    _chrome(s, "Executive Summary", f"{company} · {sector} · {region}", 2)
    metrics = a.get("key_metrics", [])
    for i, m in enumerate(metrics[:4]):
        _kpi(s, Inches(0.55 + i * 3.08), m.get("label", ""), m.get("value", ""),
             m.get("delta", ""), GREEN if m.get("tone") == "positive" else GOLD)
    summary = (w.get("executive_summary") or a.get("summary", ""))
    import re
    summary = re.sub(r"\*\*|\[S?\d+\]", "", summary)
    _rect(s, Inches(0.55), Inches(3.5), Inches(12.2), Inches(2.9), CARD)
    _text(s, Inches(0.85), Inches(3.65), Inches(11.6), Inches(0.35),
          "THE SITUATION", 10, True, GOLD)
    box = s.shapes.add_textbox(Inches(0.85), Inches(4.0), Inches(11.5), Inches(2.2))
    tf = box.text_frame; tf.word_wrap = True
    p = tf.paragraphs[0]; p.text = summary[:700]
    for r in p.runs:
        r.font.size = Pt(15); r.font.color.rgb = WHITE; r.font.name = "Arial"

    # 3 — Market trajectory chart
    s = _blank(prs)
    _chrome(s, "Market Trajectory", "Historic market size, USD billions", 3)
    hist = d.get("history", [])
    if hist:
        cd = CategoryChartData()
        cd.categories = [str(h["year"]) for h in hist]
        cd.add_series("Market size", [h["value"] for h in hist])
        gf = s.shapes.add_chart(XL_CHART_TYPE.COLUMN_CLUSTERED, Inches(0.6), Inches(1.9),
                                Inches(8.2), Inches(4.7), cd)
        chart = gf.chart
        chart.has_legend = False
        chart.value_axis.has_major_gridlines = True
        try:
            chart.series[0].format.fill.solid()
            chart.series[0].format.fill.fore_color.rgb = GOLD
            chart.category_axis.tick_labels.font.color.rgb = SLATE
            chart.value_axis.tick_labels.font.color.rgb = SLATE
        except Exception:
            pass
    siz = a.get("sizing", {})
    _rect(s, Inches(9.05), Inches(1.9), Inches(3.7), Inches(4.7), CARD)
    _text(s, Inches(9.3), Inches(2.05), Inches(3.2), Inches(0.35),
          "MARKET SIZING", 11, True, GOLD)
    for i, (k, v) in enumerate([("TAM", siz.get("TAM (USD B)", 0)),
                                ("SAM", siz.get("SAM (USD B)", 0)),
                                ("SOM", siz.get("SOM (USD B)", 0)),
                                ("CAGR", d.get("cagr_pct", 0))]):
        unit = "%" if k == "CAGR" else "B"
        _text(s, Inches(9.3), Inches(2.6 + i * 0.9), Inches(1.4), Inches(0.3),
              k, 11, True, SLATE)
        _text(s, Inches(10.6), Inches(2.55 + i * 0.9), Inches(2), Inches(0.45),
              f"${v:,.1f}{unit}" if unit == "B" else f"{v:.1f}%", 18, True, IVORY)

    # 4 — Competitive landscape
    s = _blank(prs)
    _chrome(s, "Competitive Landscape", "Estimated share by participant", 4)
    comps = d.get("competitors", [])
    if comps:
        cd = CategoryChartData()
        cd.categories = [c["name"] for c in comps]
        cd.add_series("Share", [c["share"] for c in comps])
        ch = s.shapes.add_chart(XL_CHART_TYPE.DOUGHNUT, Inches(0.55), Inches(1.85),
                                Inches(6.0), Inches(4.8), cd).chart
        ch.has_legend = True
        ch.legend.position = XL_LEGEND_POSITION.RIGHT
        try:
            ch.legend.font.size = Pt(9)
            ch.legend.font.color.rgb = SLATE
        except Exception:
            pass
    rows = len(comps) + 1
    tbl = s.shapes.add_table(rows, 3, Inches(6.9), Inches(1.95),
                             Inches(5.85), Inches(0.45 * rows)).table
    tbl.columns[0].width = Inches(3.0)
    tbl.columns[1].width = Inches(1.4)
    tbl.columns[2].width = Inches(1.45)
    for j, h in enumerate(["Company", "Share", "Revenue (B)"]):
        tbl.cell(0, j).text = h
        for p in tbl.cell(0, j).text_frame.paragraphs:
            for r in p.runs:
                r.font.size = Pt(11); r.font.bold = True; r.font.color.rgb = GOLD
    for i, c in enumerate(comps, start=1):
        for j, val in enumerate([c["name"], f"{c['share']:.1f}%",
                                 f"{c['revenue_usd_b']:,.1f}"]):
            cell = tbl.cell(i, j); cell.text = val
            for p in cell.text_frame.paragraphs:
                for r in p.runs:
                    r.font.size = Pt(10); r.font.color.rgb = WHITE
    # 5 — SWOT
    s = _blank(prs)
    _chrome(s, "SWOT Analysis", "Strengths · Weaknesses · Opportunities · Threats", 5)
    swot = a.get("swot", {})
    positions = [(0.55, 1.9), (6.85, 1.9), (0.55, 4.35), (6.85, 4.35)]
    for (x, y), (k, items) in zip(positions, list(swot.items())[:4]):
        _rect(s, Inches(x), Inches(y), Inches(5.9), Inches(2.25), CARD)
        _text(s, Inches(x + 0.25), Inches(y + 0.12), Inches(5.4), Inches(0.35),
              k.upper(), 12, True, GOLD)
        _bullets(s, Inches(x + 0.25), Inches(y + 0.5), Inches(5.4), Inches(1.65),
                 [i[:110] for i in items[:3]], 10)

    # 6 — Forecast
    s = _blank(prs)
    _chrome(s, "12-Month Forecast", "Base case with optimistic / pessimistic bands", 6)
    series = f.get("series", [])
    if series:
        cd = CategoryChartData()
        cd.categories = [r["month"] for r in series]
        cd.add_series("Optimistic", [r["optimistic"] for r in series])
        cd.add_series("Base", [r["base"] for r in series])
        cd.add_series("Pessimistic", [r["pessimistic"] for r in series])
        ch = s.shapes.add_chart(XL_CHART_TYPE.LINE, Inches(0.55), Inches(1.9),
                                Inches(8.6), Inches(4.8), cd).chart
        ch.has_legend = True
        ch.legend.position = XL_LEGEND_POSITION.BOTTOM
    for i, sc in enumerate(f.get("scenarios", [])):
        _rect(s, Inches(9.4), Inches(1.9 + i * 1.55), Inches(3.35), Inches(1.4), CARD)
        _text(s, Inches(9.6), Inches(2.0 + i * 1.55), Inches(3), Inches(0.3),
              f"{sc['name'].upper()}  ·  {sc['probability']}", 9, True, GOLD)
        _text(s, Inches(9.6), Inches(2.35 + i * 1.55), Inches(3), Inches(0.5),
              f"${sc['value']:,.1f}B", 21, True, IVORY)
        _text(s, Inches(9.6), Inches(2.82 + i * 1.55), Inches(3), Inches(0.35),
              sc["narrative"][:80], 8, False, SLATE)

    # 7 — Verification
    s = _blank(prs)
    _chrome(s, "Verification & Reliability", "Claim-level cross-checking", 7)
    _kpi(s, Inches(0.55), "Reliability score", f"{fc.get('reliability_score', 0)}/100")
    _kpi(s, Inches(3.63), "Verified claims", str(fc.get("verified_count", 0)), accent=GREEN)
    _kpi(s, Inches(6.71), "Flagged claims", str(fc.get("flagged_count", 0)), accent=GOLD)
    _kpi(s, Inches(9.79), "Sources", str(fc.get("source_count", 0)), accent=IVORY)
    claims = fc.get("claims", [])
    _rect(s, Inches(0.55), Inches(3.5), Inches(12.2), Inches(3.1), CARD)
    for i, c in enumerate(claims[:5]):
        y = 3.62 + i * 0.57
        _text(s, Inches(0.8), Inches(y), Inches(9.2), Inches(0.4),
              f"• {c['claim'][:110]}", 10, False, WHITE)
        _text(s, Inches(10.2), Inches(y), Inches(2.3), Inches(0.4),
              f"{c['status'].replace('_',' ').title()} · {c['score']}/100",
              9, True, GREEN if c["status"] == "verified" else GOLD, PP_ALIGN.RIGHT)

    # 8 — Recommendations + closing
    s = _blank(prs)
    _chrome(s, "Recommendations", "A three-horizon action plan", 8)
    recs = [
        "Defend the core: service-led differentiation over blanket discounting",
        "Scale mid-market and SMB cohorts with a repeatable product-led motion",
        "Dual-source critical inputs and index contracts to inflation",
        "Fund two measured adjacency bets with explicit stage-gates",
        "Re-run Meridian intelligence quarterly; track five leading indicators",
    ]
    _bullets(s, Inches(0.7), Inches(1.95), Inches(11.8), Inches(3.9), recs, 16)
    _rect(s, Inches(0.55), Inches(6.0), Inches(12.2), Inches(0.75), NAVY2)
    _text(s, Inches(0.8), Inches(6.05), Inches(11.7), Inches(0.6),
          f"Developed by {settings.developer}   ·   Meridian {settings.version}   ·   "
          f"{settings.tagline}", 12, True, GOLD, PP_ALIGN.CENTER)

    prs.save(str(out))
    return str(out.resolve())
