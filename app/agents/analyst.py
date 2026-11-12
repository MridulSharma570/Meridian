"""Agent 2 — Analyst: SWOT, PESTLE, Porter, sizing, trends."""
from __future__ import annotations

from typing import Any, Dict

from app.agents.base import BaseAgent, compact


class AnalystAgent(BaseAgent):
    name = "analyst"
    slot = "analyst"
    icon = "📊"
    description = "Runs SWOT, PESTLE, Porter's Five Forces and market sizing"

    def local_run(self, ctx: Dict[str, Any]) -> Dict[str, Any]:
        d = ctx.get("dataset") or ctx.get("researcher", {}).get("dataset", {})
        if not d:
            from app.data_sources.collector import collect_market_data
            d = collect_market_data(ctx.get("query", ""), ctx.get("region", "Global"),
                                    ctx.get("period", "3Y"))
            ctx["dataset"] = d
        company, sector, region = d["company"], d["sector"], d["region"]
        size, cagr = d["market_size_usd_b"], d["cagr_pct"]
        leader = d["competitors"][0]
        avg_sent = sum(c["score"] for c in d["sentiment"]) / max(1, len(d["sentiment"]))

        swot = {
            "Strengths": [
                f"{company} holds an estimated {leader['share']:.1f}% share of the {region} market",
                f"{sector} is compounding at {cagr:.1f}% CAGR, above the broad-market average",
                f"Cross-channel sentiment averages {avg_sent*100:.0f}/100, indicating healthy brand equity",
            ],
            "Weaknesses": [
                "Concentration in mature segments limits near-term margin expansion",
                "Dependence on a small number of suppliers raises input-cost exposure",
                f"Estimated revenue of ${leader['revenue_usd_b']:.1f}B trails the largest global incumbents",
            ],
            "Opportunities": [
                f"Under-penetrated mid-market and SMB segments represent ~"
                f"{sum(s['value'] for s in d['segments'][1:3]):.0f}% of demand",
                "Adjacent product bundles can lift average revenue per customer by 12–18%",
                f"Policy tailwinds and {d['macro'].get('Digital Penetration (%)', 70):.0f}% digital "
                "penetration accelerate adoption curves",
            ],
            "Threats": [
                f"Aggressive pricing from {d['competitors'][1]['name']} and "
                f"{d['competitors'][2]['name']}",
                "Regulatory shifts could raise compliance costs within 12–24 months",
                "Macro sensitivity: inflation and policy rates remain above historical averages",
            ],
        }
        pestle = [
            {"factor": "Political", "impact": "Medium", "score": 3,
             "note": f"Industrial policy in {region} favours domestic capacity build-out."},
            {"factor": "Economic", "impact": "High", "score": 4,
             "note": f"GDP growth of {d['macro'].get('GDP Growth (%)', 4):.1f}% supports demand; "
                     f"inflation near {d['macro'].get('Inflation (%)', 4):.1f}% pressures costs."},
            {"factor": "Social", "impact": "Medium", "score": 3,
             "note": "Buyers increasingly prioritise sustainability, service quality and transparency."},
            {"factor": "Technological", "impact": "High", "score": 5,
             "note": "Automation and data-driven distribution are resetting cost curves."},
            {"factor": "Legal", "impact": "Medium", "score": 3,
             "note": "Data-localisation, competition and disclosure rules are tightening."},
            {"factor": "Environmental", "impact": "Medium", "score": 3,
             "note": "Carbon reporting and circular-supply commitments influence procurement."},
        ]
        porter = [
            {"force": "Competitive rivalry", "intensity": 4,
             "note": f"{len(d['competitors'])} scaled players compete on price and feature velocity."},
            {"force": "Threat of new entrants", "intensity": 3,
             "note": "Capital requirements are moderate; distribution is the real moat."},
            {"force": "Bargaining power of buyers", "intensity": 4,
             "note": "Low switching costs and transparent pricing strengthen buyers."},
            {"force": "Bargaining power of suppliers", "intensity": 2,
             "note": "Multiple qualified suppliers, though specialised inputs remain concentrated."},
            {"force": "Threat of substitutes", "intensity": 3,
             "note": "Adjacent models and in-house alternatives cap pricing power."},
        ]
        sizing = {
            "TAM (USD B)": round(size * 3.4, 2), "SAM (USD B)": round(size * 1.35, 2),
            "SOM (USD B)": round(size * leader["share"] / 100, 2),
            "Base Year": d["history"][-1]["year"],
            "CAGR (%)": cagr, "Forecast CAGR (%)": d["forecast_growth_pct"],
            "Market Concentration": "Moderately fragmented" if leader["share"] < 28 else "Leader-led",
        }
        trends = [
            {"trend": "Premiumisation of core offerings", "direction": "Accelerating",
             "confidence": 0.82, "horizon": "0–12 months"},
            {"trend": "Shift to digital / direct channels", "direction": "Accelerating",
             "confidence": 0.88, "horizon": "0–24 months"},
            {"trend": "Consolidation among mid-tier players", "direction": "Emerging",
             "confidence": 0.64, "horizon": "12–36 months"},
            {"trend": "Sustainability-linked procurement", "direction": "Steady",
             "confidence": 0.71, "horizon": "12–36 months"},
            {"trend": "Regional supply-chain localisation", "direction": "Accelerating",
             "confidence": 0.77, "horizon": "0–24 months"},
        ]
        key_metrics = [
            {"label": "Market size", "value": f"${size:.1f}B", "delta": f"+{cagr:.1f}% CAGR",
             "tone": "positive"},
            {"label": "Leader share", "value": f"{leader['share']:.1f}%", "delta": "▲ 1.4 pp YoY",
             "tone": "positive"},
            {"label": "Avg. sentiment", "value": f"{avg_sent*100:.0f}/100", "delta": "▲ 4 pts",
             "tone": "positive"},
            {"label": "Competitive intensity", "value": "4.0 / 5", "delta": "High rivalry",
             "tone": "negative"},
        ]
        return {
            "swot": swot, "pestle": pestle, "porter": porter, "sizing": sizing,
            "trends": trends, "key_metrics": key_metrics,
            "opportunities": swot["Opportunities"], "threats": swot["Threats"],
            "growth_drivers": [t["trend"] for t in trends[:3]],
            "risk_events": d.get("risk_events", []),
            "market_share": d["competitors"], "segments": d["segments"],
            "summary": (f"{sector} in {region} is a ${size:.1f}B market growing at "
                        f"{cagr:.1f}% CAGR. {company} leads at {leader['share']:.1f}% share, "
                        "but rivalry and buyer power keep margins contested."),
        }

    def llm_prompt(self, ctx: Dict[str, Any]) -> str:
        d = ctx.get("dataset", {})
        return (
            "As the Analyst agent, sharpen the strategic interpretation of this dataset.\n"
            "Return JSON with keys: summary (2 sentences), additional_trends (array of 2 objects "
            "with trend/direction/confidence), strategic_priorities (array of 3 short strings). "
            "Stay strictly grounded in the supplied numbers.\n\nDATA:\n" + compact({
                "company": d.get("company"), "sector": d.get("sector"),
                "region": d.get("region"), "market_size_usd_b": d.get("market_size_usd_b"),
                "cagr_pct": d.get("cagr_pct"), "competitors": d.get("competitors"),
                "sentiment": d.get("sentiment"), "macro": d.get("macro"),
            })
        )

    def merge(self, local: Dict[str, Any], remote: Any) -> Dict[str, Any]:
        if isinstance(remote, dict):
            if isinstance(remote.get("summary"), str) and remote["summary"]:
                local["summary"] = remote["summary"][:600]
            if isinstance(remote.get("additional_trends"), list):
                local["trends"] = (local["trends"] + [
                    {"trend": t.get("trend", ""), "direction": t.get("direction", "Emerging"),
                     "confidence": float(t.get("confidence", 0.6) or 0.6), "horizon": "12–36 months"}
                    for t in remote["additional_trends"] if isinstance(t, dict)
                ])[:7]
            if isinstance(remote.get("strategic_priorities"), list):
                local["strategic_priorities"] = remote["strategic_priorities"][:5]
        return local
