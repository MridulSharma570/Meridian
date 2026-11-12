"""Agent 1 — Researcher: live signal collection and source curation."""
from __future__ import annotations

from typing import Any, Dict

from app.agents.base import BaseAgent, compact
from app.data_sources.collector import collect_market_data
from app.data_sources.demo_data import split_comparison


class ResearcherAgent(BaseAgent):
    name = "researcher"
    slot = "researcher"
    icon = "🔍"
    description = "Collects live market signals, financials, news and verified sources"

    def local_run(self, ctx: Dict[str, Any]) -> Dict[str, Any]:
        query = ctx.get("query", "")
        region = ctx.get("region", "Global")
        period = ctx.get("period", "3Y")
        dataset = collect_market_data(query, region, period)
        ctx["dataset"] = dataset  # shared downstream state
        comparison = split_comparison(query)
        return {
            "query": query, "company": dataset["company"], "sector": dataset["sector"],
            "region": region, "period": period, "as_of": dataset["as_of"],
            "dataset": dataset,
            "sources": dataset["sources"],
            "source_count": len(dataset["sources"]),
            "headlines": dataset["news"],
            "statistics": {
                "market_size_usd_b": dataset["market_size_usd_b"],
                "cagr_pct": dataset["cagr_pct"],
                "history": dataset["history"],
                "competitors": dataset["competitors"],
                "macro": dataset["macro"],
                "quarters": dataset["quarters"],
            },
            "sentiment": dataset["sentiment"],
            "signals": [
                f"{dataset['sector']} valued at ${dataset['market_size_usd_b']:.1f}B in {region}",
                f"Trailing CAGR of {dataset['cagr_pct']:.1f}% across {period}",
                f"{len(dataset['competitors'])} tracked competitors; leader holds "
                f"{dataset['competitors'][0]['share']:.1f}% share",
                f"{len(dataset['news'])} recent news items, "
                f"{len(dataset['sources'])} citable sources",
            ],
            "comparison_request": list(comparison) if comparison else None,
            "data_mode": dataset["data_mode"],
            "connectors": dataset.get("connectors", {}),
            "confidence_note": dataset["confidence_note"],
        }

    def llm_prompt(self, ctx: Dict[str, Any]) -> str:
        d = ctx.get("dataset", {})
        return (
            "As the Researcher agent, refine this market research brief.\n"
            "Return JSON with keys: executive_signals (array of 4 short, specific, "
            "quantified strings), source_notes (array of 3 strings on evidence quality), "
            "data_gaps (array of 3 short strings describing what a human analyst should verify).\n"
            "Do NOT invent figures outside the supplied data.\n\n"
            "DATA:\n" + compact({
                "query": d.get("query"), "sector": d.get("sector"),
                "region": d.get("region"), "market_size_usd_b": d.get("market_size_usd_b"),
                "cagr_pct": d.get("cagr_pct"), "history": d.get("history"),
                "competitors": d.get("competitors"), "news": [n["title"] for n in d.get("news", [])],
            })
        )

    def merge(self, local: Dict[str, Any], remote: Any) -> Dict[str, Any]:
        if isinstance(remote, dict):
            if isinstance(remote.get("executive_signals"), list) and remote["executive_signals"]:
                local["signals"] = remote["executive_signals"][:6]
            for k in ("source_notes", "data_gaps"):
                if isinstance(remote.get(k), list):
                    local[k] = remote[k][:5]
        return local
