"""World Bank open-data connector for macro indicators."""
from __future__ import annotations

import logging
from typing import Any, Dict

import requests

from app.config import settings

logger = logging.getLogger("meridian.data.worldbank")

INDICATORS = {
    "NY.GDP.MKTP.KD.ZG": "GDP Growth (%)",
    "FP.CPI.TOTL.ZG": "Inflation (%)",
    "IT.NET.USER.ZS": "Digital Penetration (%)",
}
COUNTRIES = {"India": "IN", "Global": "WLD", "North America": "US",
             "Europe": "EU", "Asia Pacific": "CN", "LATAM": "BR", "Middle East": "AE"}


def get_macro(region: str) -> Dict[str, Any]:
    code = COUNTRIES.get(region, "WLD")
    if not settings.world_bank_enabled:
        return {"values": {}, "live": False}
    values: Dict[str, float] = {}
    try:
        for ind, label in INDICATORS.items():
            url = f"https://api.worldbank.org/v2/country/{code}/indicator/{ind}"
            r = requests.get(url, params={"format": "json", "per_page": 5, "date": "2020:2025"},
                             timeout=3)
            r.raise_for_status()
            rows = r.json()
            if isinstance(rows, list) and len(rows) > 1 and isinstance(rows[1], list):
                for row in rows[1]:
                    if row.get("value") is not None:
                        values[label] = round(float(row["value"]), 2)
                        break
    except Exception as exc:
        logger.debug("World Bank unavailable: %s", exc)
    return {"values": values, "live": bool(values)}
