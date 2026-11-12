"""Export engine tests: real PDF, PPTX and XLSX files with charts."""
from __future__ import annotations

from pathlib import Path

import pytest

from app import services
from app.database import queries
from app.export.excel_generator import generate_excel
from app.export.pdf_generator import generate_pdf
from app.export.pptx_generator import generate_pptx


@pytest.fixture(scope="module")
def report(workspace: Path):
    """Build one complete report and export it three ways."""
    rid = services.start_report("Global semiconductor market 2026",
                                region="Asia Pacific", period="5Y")
    import time
    deadline = time.time() + 30
    while time.time() < deadline and services.job_status(rid)["status"] == "processing":
        time.sleep(.1)
    return services._report_to_export_dict(queries.get_report(rid)), workspace


def test_pdf_is_valid_and_complete(report):
    payload, tmp = report
    out = generate_pdf(payload, tmp / "test.pdf")
    p = Path(out)
    assert p.exists() and p.stat().st_size > 5000
    assert p.read_bytes()[:5] == b"%PDF-"
    assert b"%%EOF" in p.read_bytes()[-1024:]


def test_pptx_is_valid_and_has_slides(report):
    from pptx import Presentation
    payload, tmp = report
    out = generate_pptx(payload, tmp / "test.pptx")
    prs = Presentation(out)
    assert len(prs.slides) >= 7
    texts = " ".join(sh.text for sl in prs.slides for sh in sl.shapes if sh.has_text_frame)
    assert "MERIDIAN" in texts and "Mridul Sharma" in texts


def test_excel_is_valid_with_charts(report):
    from openpyxl import load_workbook
    payload, tmp = report
    out = generate_excel(payload, tmp / "test.xlsx")
    wb = load_workbook(out)
    assert {"Summary", "Market History", "Competitors", "Forecast", "Sources"} <= set(wb.sheetnames)
    assert len(wb["Forecast"]._charts) >= 1
    assert len(wb["Competitors"]._charts) >= 1
    assert wb["Summary"]["A23"].value.startswith("Developed by Mridul Sharma")


def test_export_service_regenerates_missing_files(report, workspace: Path):
    payload, tmp = report
    rid = queries.list_reports(search="semiconductor")[0]["id"]
    paths = services.generate_exports(rid)
    assert all(Path(p).exists() for p in paths.values())
    for fmt in ("pdf", "pptx", "excel"):
        assert Path(services.export_path(rid, fmt)).exists()
