"""Multi-sheet Excel workbook with native, editable charts (openpyxl)."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict

from openpyxl import Workbook
from openpyxl.chart import BarChart, LineChart, PieChart, Reference
from openpyxl.chart.marker import DataPoint
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from app.config import settings

logger = logging.getLogger("meridian.export.excel")

NAVY = "0A1628"
CARD = "1A2744"
GOLD = "C9A84C"
IVORY = "EDE4D3"
SLATE = "64748B"
WHITE = "F8FAFC"
GREEN = "059669"

HEAD_FILL = PatternFill("solid", fgColor=NAVY)
ALT_FILL = PatternFill("solid", fgColor="F1F4F9")
GOLD_FILL = PatternFill("solid", fgColor=GOLD)
THIN = Side(style="thin", color="DCE3ED")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)


def _header(ws, headers, row=1):
    for j, h in enumerate(headers, start=1):
        c = ws.cell(row=row, column=j, value=h)
        c.fill = HEAD_FILL
        c.font = Font(bold=True, color=WHITE, size=10, name="Calibri")
        c.alignment = Alignment(horizontal="left", vertical="center")
        c.border = BORDER
    ws.row_dimensions[row].height = 24
    ws.freeze_panes = f"A{row+1}"


def _write_rows(ws, rows, start=2):
    for i, row in enumerate(rows, start=start):
        for j, val in enumerate(row, start=1):
            c = ws.cell(row=i, column=j, value=val)
            c.border = BORDER
            c.font = Font(size=10, name="Calibri", color=NAVY)
            if i % 2 == 0:
                c.fill = ALT_FILL
            if isinstance(val, (int, float)):
                c.number_format = "#,##0.00"
                c.alignment = Alignment(horizontal="right")


def _widths(ws, widths):
    for i, w in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(i)].width = w


def generate_excel(report: Dict[str, Any], out_path: str | Path) -> str:
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    d = (report.get("researcher_output") or {}).get("dataset") or {}
    a = report.get("analyst_output") or {}
    f = report.get("forecast_output") or {}
    fc = report.get("factcheck_output") or {}
    w = report.get("writer_output") or {}
    company = d.get("company") or report.get("company") or "Market Intelligence"

    wb = Workbook()

    # --- Summary ------------------------------------------------------------ #
    ws = wb.active
    ws.title = "Summary"
    ws.sheet_view.showGridLines = False
    ws["A1"] = "◆  MERIDIAN — MARKET INTELLIGENCE"
    ws["A1"].font = Font(bold=True, size=18, color=NAVY)
    ws["A2"] = settings.tagline
    ws["A2"].font = Font(italic=True, size=11, color=GOLD)
    ws["A4"] = "Subject"; ws["B4"] = company
    ws["A5"] = "Sector"; ws["B5"] = d.get("sector", "")
    ws["A6"] = "Region"; ws["B6"] = d.get("region", "")
    ws["A7"] = "Period"; ws["B7"] = d.get("period", "")
    ws["A8"] = "Generated"; ws["B8"] = d.get("as_of", "")
    ws["A9"] = "Data mode"; ws["B9"] = d.get("data_mode", "")
    ws["A10"] = "Reliability"; ws["B10"] = f"{fc.get('reliability_score', 0)}/100"
    for r in range(4, 11):
        ws.cell(row=r, column=1).font = Font(bold=True, color=SLATE, size=10)
        ws.cell(row=r, column=2).font = Font(bold=True, color=NAVY, size=11)
    ws["A12"] = "HEADLINE METRICS"
    ws["A12"].font = Font(bold=True, size=11, color=NAVY)
    _header(ws, ["Metric", "Value", "Change"], row=13)
    _write_rows(ws, [[m.get("label", ""), m.get("value", ""), m.get("delta", "")]
                     for m in a.get("key_metrics", [])], start=14)
    ws["A20"] = "EXECUTIVE SUMMARY"
    ws["A20"].font = Font(bold=True, size=11, color=NAVY)
    ws["A21"] = (w.get("executive_summary") or "").replace("**", "")[:900]
    ws["A21"].alignment = Alignment(wrap_text=True, vertical="top")
    ws.row_dimensions[21].height = 90
    ws["A23"] = f"Developed by {settings.developer} · Meridian {settings.version}"
    ws["A23"].font = Font(italic=True, size=9, color=SLATE)
    _widths(ws, [26, 78, 22])

    # --- Market history ------------------------------------------------------ #
    ws = wb.create_sheet("Market History")
    ws.sheet_view.showGridLines = False
    _header(ws, ["Year", "Market size (USD B)", "YoY %"])
    hist = d.get("history", [])
    rows = []
    for i, h in enumerate(hist):
        yoy = (h["value"] / hist[i-1]["value"] - 1) * 100 if i else 0
        rows.append([h["year"], h["value"], round(yoy, 2)])
    _write_rows(ws, rows)
    _widths(ws, [12, 24, 14])
    if rows:
        ch = LineChart()
        ch.title = "Market size trajectory (USD B)"
        ch.style = 12
        ch.y_axis.title = "USD B"
        ch.x_axis.title = "Year"
        ch.add_data(Reference(ws, min_col=2, min_row=1, max_row=len(rows) + 1), titles_from_data=True)
        ch.set_categories(Reference(ws, min_col=1, min_row=2, max_row=len(rows) + 1))
        ch.height, ch.width = 8, 16
        ch.series[0].graphicalProperties.line.solidFill = GOLD
        ch.series[0].graphicalProperties.line.width = 28000
        ws.add_chart(ch, "E2")

    # --- Competitors --------------------------------------------------------- #
    ws = wb.create_sheet("Competitors")
    ws.sheet_view.showGridLines = False
    _header(ws, ["Company", "Share %", "Revenue (USD B)", "Growth %", "Sentiment /100"])
    comps = d.get("competitors", [])
    _write_rows(ws, [[c["name"], c["share"], c["revenue_usd_b"], c["growth_pct"],
                      round(c["sentiment"] * 100, 1)] for c in comps])
    _widths(ws, [28, 12, 20, 14, 18])
    if comps:
        pie = PieChart()
        pie.title = "Market share"
        pie.add_data(Reference(ws, min_col=2, min_row=1, max_row=len(comps) + 1),
                     titles_from_data=True)
        pie.set_categories(Reference(ws, min_col=1, min_row=2, max_row=len(comps) + 1))
        pie.height, pie.width = 9, 14
        ws.add_chart(pie, "G2")

    # --- Forecast ------------------------------------------------------------ #
    ws = wb.create_sheet("Forecast")
    ws.sheet_view.showGridLines = False
    _header(ws, ["Month", "Base", "Optimistic", "Pessimistic", "Confidence"])
    series = f.get("series", [])
    _write_rows(ws, [[r["month"], r["base"], r["optimistic"], r["pessimistic"],
                      r["confidence"]] for r in series])
    _widths(ws, [14, 14, 16, 16, 14])
    if series:
        ch = LineChart()
        ch.title = "12-month forecast with confidence bands"
        ch.style = 12
        ch.add_data(Reference(ws, min_col=2, max_col=4, min_row=1,
                              max_row=len(series) + 1), titles_from_data=True)
        ch.set_categories(Reference(ws, min_col=1, min_row=2, max_row=len(series) + 1))
        ch.height, ch.width = 9, 18
        for colour, s in zip((GOLD, GREEN, "E11D48"), ch.series):
            s.graphicalProperties.line.solidFill = colour
            s.graphicalProperties.line.width = 24000
        ws.add_chart(ch, "G2")

    # --- SWOT / PESTLE / Porter ---------------------------------------------- #
    ws = wb.create_sheet("SWOT")
    ws.sheet_view.showGridLines = False
    _header(ws, ["Dimension", "Finding"])
    rows = [[k, item] for k, items in (a.get("swot") or {}).items() for item in items]
    _write_rows(ws, rows)
    _widths(ws, [18, 110])

    ws = wb.create_sheet("PESTLE")
    ws.sheet_view.showGridLines = False
    _header(ws, ["Factor", "Impact", "Score (1-5)", "Assessment"])
    _write_rows(ws, [[p["factor"], p["impact"], p["score"], p["note"]]
                     for p in a.get("pestle", [])])
    _widths(ws, [18, 14, 16, 100])

    ws = wb.create_sheet("Porters Five Forces")
    ws.sheet_view.showGridLines = False
    _header(ws, ["Force", "Intensity (1-5)", "Assessment"])
    _write_rows(ws, [[p["force"], p["intensity"], p["note"]] for p in a.get("porter", [])])
    _widths(ws, [32, 18, 100])
    if a.get("porter"):
        ch = BarChart()
        ch.type = "bar"
        ch.title = "Competitive force intensity"
        ch.add_data(Reference(ws, min_col=2, min_row=1,
                              max_row=len(a["porter"]) + 1), titles_from_data=True)
        ch.set_categories(Reference(ws, min_col=1, min_row=2,
                                    max_row=len(a["porter"]) + 1))
        ch.height, ch.width = 7, 14
        ws.add_chart(ch, "E2")

    # --- Sentiment ----------------------------------------------------------- #
    ws = wb.create_sheet("Sentiment")
    ws.sheet_view.showGridLines = False
    _header(ws, ["Channel", "Score /100", "Volume", "Trend pp"])
    _write_rows(ws, [[s["channel"], round(s["score"] * 100, 1), s["volume"],
                      round(s["trend"] * 100, 1)] for s in d.get("sentiment", [])])
    _widths(ws, [22, 14, 14, 14])

    # --- Fact check ---------------------------------------------------------- #
    ws = wb.create_sheet("Fact Check")
    ws.sheet_view.showGridLines = False
    _header(ws, ["Claim", "Category", "Status", "Score /100", "Sources", "Note"])
    _write_rows(ws, [[c["claim"], c["category"], c["status"], c["score"],
                      ", ".join(c["sources"]), c["note"]] for c in fc.get("claims", [])])
    _widths(ws, [70, 20, 22, 14, 16, 70])

    # --- Sources ------------------------------------------------------------- #
    ws = wb.create_sheet("Sources")
    ws.sheet_view.showGridLines = False
    _header(ws, ["Ref", "Publisher", "Title", "Type", "Year", "Reliability", "URL"])
    _write_rows(ws, [[s["id"], s["publisher"], s["title"], s["type"], s["year"],
                      s["reliability"], s["url"]] for s in d.get("sources", [])])
    _widths(ws, [10, 26, 62, 22, 10, 14, 46])

    # --- Raw JSON ------------------------------------------------------------ #
    ws = wb.create_sheet("Raw Data")
    ws.sheet_view.showGridLines = False
    _header(ws, ["Section", "JSON"])
    import json
    for i, (k, v) in enumerate({
        "Researcher": report.get("researcher_output"),
        "Analyst": report.get("analyst_output"),
        "Forecast": report.get("forecast_output"),
        "Fact-Checker": report.get("factcheck_output"),
    }.items(), start=2):
        ws.cell(row=i, column=1, value=k).font = Font(bold=True, color=NAVY)
        cell = ws.cell(row=i, column=2,
                       value=json.dumps(v, ensure_ascii=False, default=str)[:32000])
        cell.alignment = Alignment(wrap_text=True, vertical="top")
    _widths(ws, [18, 130])

    wb.save(str(out))
    return str(out.resolve())
