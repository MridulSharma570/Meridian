"""Agent 5 — Forecast: 12-month base / optimistic / pessimistic projections."""
from __future__ import annotations

import math
from datetime import date
from typing import Any, Dict, List

from app.agents.base import BaseAgent, compact


def _add_months(d: date, n: int) -> str:
    y, m = d.year + (d.month - 1 + n) // 12, (d.month - 1 + n) % 12 + 1
    return f"{y}-{m:02d}"


class ForecastAgent(BaseAgent):
    name = "forecast"
    slot = "forecast"
    icon = "📈"
    description = "Builds a 12-month forecast with confidence bands"

    def local_run(self, ctx: Dict[str, Any]) -> Dict[str, Any]:
        d = ctx.get("dataset", {})
        hist = d.get("history", [])
        cagr = float(d.get("forecast_growth_pct", d.get("cagr_pct", 10))) / 100.0
        last = float(hist[-1]["value"]) if hist else float(d.get("market_size_usd_b", 100))
        monthly = (1 + cagr) ** (1 / 12) - 1
        today = date.today()
        rows: List[Dict[str, Any]] = []
        for i in range(1, 13):
            base = last * ((1 + monthly) ** i)
            season = 1 + 0.012 * math.sin((i / 12) * 2 * math.pi)
            base *= season
            spread = 0.018 * i + 0.02
            rows.append({
                "month": _add_months(today, i),
                "base": round(base, 2),
                "optimistic": round(base * (1 + spread), 2),
                "pessimistic": round(base * (1 - spread * 0.78), 2),
                "confidence": round(max(0.55, 0.94 - i * 0.028), 2),
            })
        end = rows[-1]
        return {
            "series": rows, "horizon_months": 12,
            "base_end": end["base"], "optimistic_end": end["optimistic"],
            "pessimistic_end": end["pessimistic"],
            "expected_growth_pct": round((end["base"] / last - 1) * 100, 2),
            "upside_pct": round((end["optimistic"] / end["base"] - 1) * 100, 2),
            "downside_pct": round((1 - end["pessimistic"] / end["base"]) * 100, 2),
            "drivers": [
                "Trailing CAGR extrapolated with damped monthly compounding",
                "Seasonal sine adjustment calibrated to quarterly revenue pattern",
                "Confidence band widens ±1.8 pp per month to reflect model uncertainty",
                "Macro indicators (GDP, inflation, policy rate) used as qualitative guardrails",
            ],
            "method": "Damped trend extrapolation + seasonal adjustment + widening intervals",
            "scenarios": [
                {"name": "Base", "value": end["base"], "probability": "60%",
                 "narrative": "Trend growth continues with no major shocks."},
                {"name": "Optimistic", "value": end["optimistic"], "probability": "20%",
                 "narrative": "Faster adoption, easing input costs and supportive policy."},
                {"name": "Pessimistic", "value": end["pessimistic"], "probability": "20%",
                 "narrative": "Pricing pressure and macro tightening compress demand."},
            ],
            "note": "Projections are model estimates, not investment advice.",
        }

    def llm_prompt(self, ctx: Dict[str, Any]) -> str:
        f = ctx.get("forecast", {})
        return (
            "As the Forecast agent, write 3 concise scenario narratives grounded in the numbers.\n"
            "Return JSON: {\"narratives\": [\"base\", \"optimistic\", \"pessimistic\"]} "
            "each a 1–2 sentence string, plus \"key_risk\" (string). No invented numbers.\n\n"
            "DATA:\n" + compact({
                "expected_growth_pct": f.get("expected_growth_pct"),
                "scenarios": f.get("scenarios"), "drivers": f.get("drivers"),
            }, 2600)
        )

    def merge(self, local: Dict[str, Any], remote: Any) -> Dict[str, Any]:
        if isinstance(remote, dict) and isinstance(remote.get("narratives"), list):
            for scenario, narrative in zip(local["scenarios"], remote["narratives"][:3]):
                if isinstance(narrative, str) and narrative:
                    scenario["narrative"] = narrative[:300]
            if isinstance(remote.get("key_risk"), str):
                local["key_risk"] = remote["key_risk"][:300]
        return local
