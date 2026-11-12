"""Parallel, failure-isolated collection of **real** evidence.

A deterministic dataset is still built so charts and exports have a stable
shape, but in production (``MERIDIAN_SAMPLE_MODE`` off) every fabricated
citation, headline and publisher is stripped. Only connectors that actually
returned data contribute to ``verified_sources``; ``answer_policy`` refuses a
report when that list is empty. Numeric series that no source supplied are
flagged ``unverified_metrics`` and must be presented as placeholders, never as
measurements.
"""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List

from app.api import answer_policy
from app.config import settings
from app.data_sources.demo_data import build_market_dataset
from app.data_sources.news_api import get_news
from app.data_sources.social_sentiment import aggregate
from app.data_sources.web_search import search_web
from app.data_sources.world_bank import get_macro
from app.data_sources.yahoo_finance import get_financials

logger = logging.getLogger("meridian.data.collector")


def _source(idx: str, item: Dict[str, Any], publisher: str, kind: str,
            reliability: int = 80) -> Dict[str, Any]:
    return {
        "id": idx, "title": str(item.get("title") or item.get("name") or "Untitled source")[:240],
        "publisher": publisher, "url": str(item.get("url") or ""),
        "type": kind, "reliability": reliability,
        "snippet": str(item.get("snippet") or "")[:400],
        "verified": True,
    }


def collect_market_data(query: str, region: str = "Global",
                        period: str = "3Y") -> Dict[str, Any]:
    data = build_market_dataset(query, region, period)
    strict = answer_policy.strict_mode()

    if strict:
        # Remove everything that merely *looks* like evidence, then neutralise
        # every invented figure while keeping the chart shapes intact. A zero
        # is displayed as "no verified figure"; it is never passed off as a
        # measurement. Real connectors overwrite these fields below.
        data["sources"] = []
        data["news"] = []
        data["data_mode"] = "unverified"
        data["verified_sources"] = []
        data["unverified_metrics"] = True
        data["sample"] = False
        data["market_size_usd_b"] = 0.0
        data["cagr_pct"] = 0.0
        data["forecast_growth_pct"] = 0.0
        data["history"] = [{"year": h["year"], "value": 0.0} for h in data["history"]]
        data["quarters"] = [{"label": q["label"], "revenue": 0.0,
                             "competitor_avg": 0.0} for q in data["quarters"]]
        data["competitors"] = [{"name": "No verified competitor data", "share": 0.0,
                                "revenue_usd_b": 0.0, "growth_pct": 0.0,
                                "sentiment": 0.0}]
        data["segments"] = [{"name": s["name"], "value": 0.0} for s in data["segments"]]
        data["sentiment"] = [{"channel": c["channel"], "score": 0.0,
                              "volume": 0, "trend": 0.0} for c in data["sentiment"]]
        data["heatmap"] = [[0.0 for _ in row] for row in data["heatmap"]]
        data["social_mentions"] = [{"label": m["label"], "value": 0}
                                   for m in data["social_mentions"]]
        data["macro"] = {}
        data["risk_events"] = []
        data["confidence_note"] = answer_policy.provenance_note(data)
    else:
        data["verified_sources"] = []

    def _news():
        return "news", get_news(f"{data['company']} {data['sector']} market")
    def _web():
        return "web", search_web(f"{data['sector']} {region} market size {data['history'][-1]['year']}")
    def _yahoo():
        return "yahoo", get_financials(data["company"])
    def _macro():
        return "macro", get_macro(region)
    def _social():
        return "social", aggregate(data)

    jobs = [_news, _web, _yahoo, _macro, _social]
    results: Dict[str, Any] = {}
    if not settings.enable_live_data:
        data["connectors"] = {name: "disabled" for name in
                              ("news", "web_search", "yahoo_finance",
                               "world_bank", "social_sentiment")}
        data["data_mode"] = "sample" if not strict else "unverified"
    else:
        try:
            with ThreadPoolExecutor(max_workers=len(jobs)) as pool:
                futures = {pool.submit(fn): fn for fn in jobs}
                for fut in as_completed(futures, timeout=6):
                    try:
                        name, value = fut.result()
                        results[name] = value
                    except Exception as exc:
                        logger.debug("Connector failed: %s", exc)
        except Exception as exc:
            logger.debug("Collection budget exceeded: %s", exc)

    live_flags: Dict[str, bool] = {}
    verified: List[Dict[str, Any]] = []

    news = results.get("news", {})
    if news.get("live") and news.get("articles"):
        articles = news["articles"][:10]
        data["news"] = articles
        live_flags["news"] = True
        for i, a in enumerate(articles):
            verified.append(_source(f"N{i+1:02d}",
                                    {"title": a.get("title"), "url": a.get("url")},
                                    str(a.get("source") or "NewsAPI"), "News", 88))

    web = results.get("web", {})
    if web.get("live") and web.get("results"):
        for i, item in enumerate(web["results"][:6]):
            verified.append(_source(f"L{i+1:02d}", item,
                                    str(item.get("source") or "Web search"),
                                    "Live Web Result", 82))
        live_flags["web"] = True

    yahoo = results.get("yahoo", {})
    if yahoo.get("live") and yahoo.get("series"):
        data["price_series"] = yahoo["series"]
        data["ticker"] = yahoo["ticker"]
        live_flags["yahoo"] = True
        verified.append(_source("F01", {"title": f"{yahoo['ticker']} market price history",
                                        "url": "https://finance.yahoo.com/"},
                                "Yahoo Finance", "Market data", 90))

    macro = results.get("macro", {})
    if macro.get("live") and macro.get("values"):
        data["macro"].update(macro["values"])
        data["verified_macro"] = dict(macro["values"])
        live_flags["macro"] = True
        verified.append(_source("M01", {"title": "World Bank open data indicators",
                                        "url": "https://data.worldbank.org/"},
                                "World Bank", "Macro indicator", 97))

    social = results.get("social", {})
    if social.get("channels"):
        data["sentiment"] = social["channels"]
        data["overall_sentiment"] = social["overall"]
        data["sentiment_label"] = social["label"]
        if social.get("reddit_posts"):
            data["reddit_posts"] = social["reddit_posts"]
            for i, post in enumerate(social["reddit_posts"][:4]):
                verified.append(_source(f"R{i+1:02d}", post,
                                        "Reddit", "Social signal", 55))
        live_flags["social"] = bool(social.get("live"))

    data["connectors"] = {
        "news": "live" if live_flags.get("news") else "offline",
        "web_search": "live" if live_flags.get("web") else "offline",
        "yahoo_finance": "live" if live_flags.get("yahoo") else "offline",
        "world_bank": "live" if live_flags.get("macro") else "offline",
        "social_sentiment": "live" if live_flags.get("social") else "offline",
    }
    data["verified_sources"] = verified
    data["verified"] = bool(verified)
    data["sources"] = list(verified) if strict else data["sources"] + verified
    live_names = [k for k, v in live_flags.items() if v]
    data["data_mode"] = (
        "sample" if not strict else
        "verified" if verified else "unverified")
    data["confidence_note"] = answer_policy.provenance_note(data)
    data["evidence"] = {
        "source_count": len(verified),
        "connectors": dict(data["connectors"]),
        "live_connectors": live_names,
        "verified_macro": data.get("verified_macro", {}),
        "price_series_verified": bool(live_flags.get("yahoo")),
    }
    return data
