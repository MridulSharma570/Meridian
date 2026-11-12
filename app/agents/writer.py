"""Agent 3 — Writer: board-ready research report with cited sources."""
from __future__ import annotations

import re
import textwrap
from typing import Any, Dict, List

from app.agents.base import BaseAgent, compact
from app.api import answer_policy
from app.config import settings


def _table(headers: List[str], rows: List[List[Any]]) -> str:
    out = ["| " + " | ".join(headers) + " |",
           "| " + " | ".join(["---"] * len(headers)) + " |"]
    for row in rows:
        out.append("| " + " | ".join(str(c).replace("|", "\\|") for c in row) + " |")
    return "\n".join(out)


class WriterAgent(BaseAgent):
    name = "writer"
    slot = "writer"
    icon = "✍️"
    description = "Composes the executive market research report"
    verified_fields = ("markdown", "sections", "citations", "executive_summary",
                       "recommendations", "headline")
    strict_max_tokens = 4096
    strict_retry_guidance = (
        "The markdown must remain a complete report with a Sources section, "
        "but aim for 500–700 words and finish the JSON object.")

    def local_run(self, ctx: Dict[str, Any]) -> Dict[str, Any]:
        if answer_policy.strict_mode():
            return self._verified_scaffold(ctx)
        d = ctx.get("dataset", {})
        r = ctx.get("researcher", {})
        a = ctx.get("analyst", {})
        company, sector, region = d.get("company", "The Market"), d.get("sector", "Market"), d.get("region", "Global")
        size = d.get("market_size_usd_b", 0)
        cagr = d.get("cagr_pct", 0)
        sources = r.get("sources") or d.get("sources", [])
        cite = " ".join(f"[{s['id']}]" for s in sources[:4]) or "[S01]"
        swot = a.get("swot", {})
        sizing = a.get("sizing", {})

        exec_summary = (
            f"**{company}** operates in the **{sector}** market in **{region}**, currently "
            f"estimated at **${size:,.1f}B** and expanding at a **{cagr:.1f}% CAGR** over the "
            f"{d.get('period', '3Y')} review window. Demand is being reshaped by digital "
            "distribution, premiumisation and regional supply-chain localisation, while buyer "
            "power and aggressive pricing from scaled incumbents keep margins contested. "
            f"The leading participant holds approximately **{d['competitors'][0]['share']:.1f}%** "
            "share. We recommend a focused three-horizon strategy: defend the core, scale "
            "under-penetrated mid-market segments, and build optionality in adjacent offerings. "
            f"{cite}"
        )

        parts: List[str] = []
        parts.append(f"# {company} — {sector} Market Intelligence Report")
        parts.append(
            f"*{region} · {d.get('period', '3Y')} review · Generated {d.get('as_of', '')} "
            "by the Meridian multi-agent engine*  ")
        parts.append(f"**Data mode:** {d.get('data_mode', 'sample')} · "
                     f"**Sources:** {len(sources)} · **Language:** English\n")
        parts.append("## 1. Executive Summary\n\n" + exec_summary)
        parts.append(
            "### Key Takeaways\n\n"
            + "\n".join(f"- {s}" for s in r.get("signals", a.get("growth_drivers", []))[:5])
        )
        parts.append(
            "## 2. Market Overview\n\n"
            f"The {sector.lower()} category in {region} reached an estimated **${size:,.1f}B** "
            f"in {d['history'][-1]['year']}, up from **${d['history'][0]['value']:,.1f}B** in "
            f"{d['history'][0]['year']}. The category compounds at **{cagr:.1f}%** and is "
            f"projected to grow at **{d.get('forecast_growth_pct', cagr):.1f}%** over the next "
            "12 months. Enterprise buyers remain the largest segment, though mid-market and SMB "
            "adoption is the fastest-growing cohort. "
            f"{cite}\n\n"
            "### Market Sizing\n\n"
            + _table(["Metric", "Estimate", "Basis"], [
                ["Total Addressable Market", f"${sizing.get('TAM (USD B)', 0):,.1f}B", "Top-down category envelope"],
                ["Serviceable Available Market", f"${sizing.get('SAM (USD B)', 0):,.1f}B", "Region + segment filter"],
                ["Serviceable Obtainable Market", f"${sizing.get('SOM (USD B)', 0):,.1f}B", "Current share × SAM"],
                ["Base-year market size", f"${size:,.1f}B", "Modelled from trailing series"],
                ["Trailing CAGR", f"{cagr:.1f}%", d.get("period", "3Y") + " historical window"],
            ])
        )
        parts.append(
            "### Historical Trajectory\n\n"
            + _table(["Year", "Market size (USD B)", "YoY change"], [
                [h["year"], f"{h['value']:,.2f}",
                 f"{(h['value'] / d['history'][i-1]['value'] - 1) * 100:+.1f}%" if i else "—"]
                for i, h in enumerate(d["history"])
            ]) + f"\n\n{cite}"
        )
        parts.append(
            "## 3. Competitive Landscape\n\n"
            f"The category contains {len(d['competitors'])} scaled participants. "
            f"Concentration is **{sizing.get('Market Concentration', 'moderate')}**.\n\n"
            + _table(["Company", "Share", "Est. revenue (USD B)", "Growth", "Sentiment"], [
                [c["name"], f"{c['share']:.1f}%", f"{c['revenue_usd_b']:,.1f}",
                 f"{c['growth_pct']:+.1f}%", f"{c['sentiment']*100:.0f}/100"]
                for c in d["competitors"]
            ]) + f"\n\n{cite}"
        )
        parts.append(
            "## 4. Trend Analysis\n\n"
            + _table(["Trend", "Direction", "Confidence", "Horizon"], [
                [t["trend"], t["direction"], f"{t['confidence']*100:.0f}%", t["horizon"]]
                for t in a.get("trends", [])
            ])
            + "\n\nCross-channel sentiment is summarised below.\n\n"
            + _table(["Channel", "Sentiment", "Volume", "Trend"], [
                [s["channel"], f"{s['score']*100:.0f}/100", f"{s['volume']:,}",
                 f"{s['trend']*100:+.1f} pp"] for s in d.get("sentiment", [])
            ])
        )
        parts.append(
            "## 5. SWOT Analysis\n\n"
            + _table(["Dimension", "Findings"], [
                [k, "<br>".join(f"• {v}" for v in vals)] for k, vals in swot.items()
            ])
        )
        parts.append(
            "## 6. PESTLE Analysis\n\n"
            + _table(["Factor", "Impact", "Score (1–5)", "Assessment"], [
                [p["factor"], p["impact"], p["score"], p["note"]] for p in a.get("pestle", [])
            ])
        )
        parts.append(
            "## 7. Porter's Five Forces\n\n"
            + _table(["Force", "Intensity (1–5)", "Assessment"], [
                [p["force"], p["intensity"], p["note"]] for p in a.get("porter", [])
            ])
        )
        parts.append(
            "## 8. Recommendations\n\n"
            + "\n".join([
                f"1. **Defend the core.** Protect the {d['competitors'][0]['share']:.1f}% share "
                "with disciplined pricing and service-level differentiation rather than broad discounting.",
                "2. **Scale the mid-market.** Build a repeatable, product-led motion for mid-market "
                "and SMB cohorts, the fastest-growing demand pools in the model.",
                "3. **De-risk the supply chain.** Dual-source critical inputs and index contracts "
                "to inflation to defend gross margin against cost shocks.",
                "4. **Invest in adjacencies.** Fund two option-value bets in adjacent categories "
                "with measured stage-gates rather than a single large bet.",
                "5. **Institutionalise intelligence.** Re-run this Meridian report quarterly and "
                "track the five leading indicators listed in the Trend Analysis section.",
            ])
        )
        parts.append(
            "## 9. Risks & Assumptions\n\n"
            + _table(["Risk", "Probability", "Impact"], [
                [x["event"], f"{x['probability']*100:.0f}%", x["impact"]]
                for x in d.get("risk_events", [])
            ])
            + f"\n\n> **Assumption notice:** {d.get('confidence_note','')}\n"
        )
        parts.append(
            "## 10. Sources\n\n"
            + _table(["Ref", "Source", "Type", "Reliability"], [
                [s["id"], f"[{s['publisher']}]({s['url']})", s["type"],
                 f"{s['reliability']}/100"] for s in sources
            ])
        )
        parts.append(f"\n---\n*Developed by {settings.developer} · Meridian {settings.version} · "
                     "Market Intelligence, Redefined.*")

        markdown = "\n\n".join(parts)
        sections = []
        for block in markdown.split("\n## "):
            if not block.strip():
                continue
            title_line, _, body = block.partition("\n")
            title = title_line.lstrip("# ").strip() if block.startswith("# ") else "## " + title_line.strip()
            sections.append({"title": title, "body": body.strip() or title_line.strip()})
        return {
            "markdown": markdown, "sections": sections,
            "executive_summary": exec_summary,
            "recommendations": a.get("strategic_priorities", [])[:5],
            "citations": [f"[{s['id']}] {s['publisher']} — {s['title']}" for s in sources],
            "word_count": len(markdown.split()),
            "title": f"{company} — {sector} Market Intelligence Report",
        }

    @staticmethod
    def _verified_scaffold(ctx: Dict[str, Any]) -> Dict[str, Any]:
        """Neutral placeholder; the LLM must author the actual report."""
        d = ctx.get("dataset", {}) or {}
        sources = d.get("verified_sources") or []
        lines = [f"# {d.get('company', 'Market')} — Intelligence Report",
                 "", "## 1. Executive Summary", "",
                 "Report text is generated by the configured LLM from the live "
                 "sources listed below. No figures are invented.", "",
                 "## 2. Sources", ""]
        lines += [f"- [{s['id']}] {s['title']} — {s['publisher']} — {s['url']}"
                  for s in sources] or ["- No live sources were supplied."]
        md = "\n".join(lines)
        return {
            "markdown": md, "sections": [{"title": "## 1. Executive Summary",
                                          "body": "Awaiting verified narrative."}],
            "executive_summary": "Awaiting verified narrative.",
            "recommendations": [], "citations": [f"[{s['id']}]" for s in sources],
            "word_count": len(md.split()),
            "title": f"{d.get('company', 'Market')} — Intelligence Report",
            "unverified_metrics": True,
        }

    def llm_prompt(self, ctx: Dict[str, Any]) -> str:
        a, d, r = ctx.get("analyst", {}), ctx.get("dataset", {}), ctx.get("researcher", {})
        return (
            "As the Writer agent, produce a sharper executive summary and three additional "
            "recommendations grounded in the analysis.\n"
            "Return JSON with keys: executive_summary (string, <=110 words), "
            "recommendations (array of 3 strings), headline (string <= 12 words). "
            "No markdown fences. Do not invent numbers.\n\nANALYSIS:\n" + compact({
                "company": d.get("company"), "sector": d.get("sector"),
                "region": d.get("region"), "summary": a.get("summary"),
                "sizing": a.get("sizing"), "swot": a.get("swot"),
                "signals": r.get("signals"),
            }, 5200)
        )

    def strict_prompt(self, ctx: Dict[str, Any], scaffold: Dict[str, Any]) -> str:
        """In verified mode the model authors the whole report, not a patch."""
        d = ctx.get("dataset", {}) or {}
        a = ctx.get("analyst", {}) or {}
        r = ctx.get("researcher", {}) or {}
        sources = d.get("verified_sources") or []
        return (
            "Write a complete, board-ready market-intelligence report in markdown. "
            "Return JSON with keys: markdown (the FULL report, at least 700 words, "
            "with ## numbered sections and a Sources section), executive_summary "
            "(<=110 words), citations (array of real source ids only), "
            "recommendations (array of 3 strings), headline (<=12 words).\n\n"
            "CRITICAL: every number, share, CAGR, headline and 'source' in the "
            "CONTEXT below came from a placeholder generator and is FABRICATED. "
            "Do not restate or cite any of them as fact. Use ONLY the VERIFIED "
            "SOURCES; cite them as [L01] where they genuinely support a claim. "
            "If a figure is not in the sources, write 'not available' and explain "
            "the gap. Never invent a publisher, URL or citation.\n\n"
            f"QUERY: {compact(ctx.get('query', ''), 300)}\n"
            f"REGION: {ctx.get('region', 'Global')} · PERIOD: {ctx.get('period', '3Y')}\n\n"
            f"VERIFIED SOURCES:\n{compact(sources, 4200)}\n\n"
            "CONTEXT (placeholder values — do not quote as facts):\n" + compact({
                "company": d.get("company"), "sector": d.get("sector"),
                "analyst_summary": a.get("summary"), "signals": r.get("signals"),
                "data_gaps": r.get("data_gaps"),
            }, 2600)
        )

    def strict_merge(self, local: Dict[str, Any], parsed: Any) -> Dict[str, Any]:
        md = parsed.get("markdown") if isinstance(parsed, dict) else None
        if not isinstance(md, str) or len(md) < 300:
            raise answer_policy.AnswerUnavailable(
                "The provider did not return a complete report; Meridian will "
                "not publish a template in its place.",
                "Try a model with a larger output limit in Settings → API Keys.",
                "unusable_output")
        merged = super().strict_merge(local, parsed)
        if isinstance(parsed, dict) and isinstance(parsed.get("markdown"), str) \
                and len(parsed["markdown"]) > 300:
            md = parsed["markdown"]
            merged["markdown"] = md
            merged["word_count"] = len(md.split())
            sections = []
            for block in md.split("\n## "):
                if not block.strip():
                    continue
                title_line, _, body = block.partition("\n")
                sections.append({"title": "## " + title_line.strip(),
                                 "body": body.strip() or title_line.strip()})
            if sections:
                merged["sections"] = sections
        # Never let the model mint a citation: keep only ids that came from
        # live sources, and scrub unknown bracketed refs out of the prose.
        allowed = set()
        for c in local.get("citations", []):
            allowed.update(re.findall(r"([A-Z]\d{2})", str(c)))
        merged["citations"] = [f"[{i}]" for i in sorted(allowed)]
        if isinstance(merged.get("markdown"), str):
            merged["markdown"] = re.sub(
                r"\[([A-Z]\d{2})\]",
                lambda m: m.group(0) if m.group(1) in allowed else "[unverified]",
                merged["markdown"])
            merged["word_count"] = len(merged["markdown"].split())
        merged["verified_answer"] = True
        merged["data_mode"] = "verified"
        return merged

    def merge(self, local: Dict[str, Any], remote: Any) -> Dict[str, Any]:
        if isinstance(remote, dict):
            summary = remote.get("executive_summary")
            if isinstance(summary, str) and len(summary) > 60:
                local["executive_summary"] = textwrap.shorten(summary, width=900,
                                                              placeholder="…")
                md = local["markdown"]
                marker = "## 1. Executive Summary\n\n"
                start = md.find(marker)
                if start != -1:
                    head = start + len(marker)
                    end = md.find("\n\n### Key Takeaways", head)
                    if end != -1:
                        local["markdown"] = md[:head] + local["executive_summary"] + md[end:]
            recs = remote.get("recommendations")
            if isinstance(recs, list) and recs:
                local["recommendations"] = [str(x)[:240] for x in recs[:5]]
            headline = remote.get("headline")
            if isinstance(headline, str) and headline:
                local["headline"] = headline[:80]
        return local
