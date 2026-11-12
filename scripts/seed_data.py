#!/usr/bin/env python3
"""Populate Meridian with a curated set of complete demo reports.

    python -m scripts.seed_data
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import services  # noqa: E402

SEEDS = [
    ("Global artificial intelligence platforms market 2026", "Global", "5Y", "en"),
    ("Indian electric vehicle market 2026 — Tesla vs BYD", "India", "3Y", "hi"),
    ("Fintech payments in India", "India", "3Y", "en"),
    ("European renewable energy outlook", "Europe", "10Y", "de"),
]


def main() -> None:
    print("◆  MERIDIAN — seeding demo intelligence reports")
    for query, region, period, lang in SEEDS:
        rid = services.start_report(query, region=region, period=period, language=lang)
        deadline = time.time() + 30
        while time.time() < deadline and services.job_status(rid)["status"] == "processing":
            time.sleep(.1)
        st = services.job_status(rid)
        print(f"   {st['status']:10s} {rid[:8]}  {query}")
    print(f"   Total reports: {services.overview_stats()['total_reports']}")
    print("   Developed by Mridul Sharma")


if __name__ == "__main__":
    main()
