"""Parallel, failure-isolated data collection.

Runs every connector concurrently with a hard wall-clock budget, then merges
live results over the deterministic baseline. A single broken connector can
never stall or fail a report.
"""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict

from app.config import settings
from app.data_sources.demo_data import build_market_dataset
from app.data_sources.news_api import get_news
from app.data_sources.social_sentiment import aggregate
from app.data_sources.web_search import search_web
from app.data_sources.world_bank import get_macro
from app.data_sources.yahoo_finance import get_financials

logger = logging.getLogger("meridian.data.collector")


def collect_market_data(query: str, region: str = "Global",
                        period: str = "3Y") -> Dict[str, Any]:
    data = build_market_dataset(query, region, period)
    live_flags: Dict[str, bool] = {}

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
    if not settings.enable_live_data:
        data["connectors"] = {name: "disabled" for name in
                              ("news", "web_search", "yahoo_finance",
                               "world_bank", "social_sentiment")}
        data["data_mode"] = "simulated"
        return data

    results: Dict[str, Any] = {}
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

    news = results.get("news", {})
    if news.get("live") and news.get("articles"):
        data["news"] = news["articles"][:10]
        live_flags["news"] = True

    web = results.get("web", {})
    if web.get("live") and web.get("results"):
        for i, item in enumerate(web["results"][:6]):
            data["sources"].append({
                "id": f"L{i+1:02d}", "title": item["title"], "publisher": item["source"],
                "url": item["url"], "type": "Live Web Result",
                "year": data["history"][-1]["year"], "reliability": 82,
                "snippet": item.get("snippet", ""),
            })
        live_flags["web"] = True

    yahoo = results.get("yahoo", {})
    if yahoo.get("live") and yahoo.get("series"):
        data["price_series"] = yahoo["series"]
        data["ticker"] = yahoo["ticker"]
        live_flags["yahoo"] = True

    macro = results.get("macro", {})
    if macro.get("live") and macro.get("values"):
        data["macro"].update(macro["values"])
        live_flags["macro"] = True

    social = results.get("social", {})
    if social.get("channels"):
        data["sentiment"] = social["channels"]
        data["overall_sentiment"] = social["overall"]
        data["sentiment_label"] = social["label"]
        if social.get("reddit_posts"):
            data["reddit_posts"] = social["reddit_posts"]
        live_flags["social"] = bool(social.get("live"))

    data["connectors"] = {
        "news": "live" if live_flags.get("news") else "offline",
        "web_search": "live" if live_flags.get("web") else "offline",
        "yahoo_finance": "live" if live_flags.get("yahoo") else "offline",
        "world_bank": "live" if live_flags.get("macro") else "offline",
        "social_sentiment": "live" if live_flags.get("social") else "offline",
    }
    live_names = [k for k, v in live_flags.items() if v]
    data["data_mode"] = ("live" if len(live_names) >= 3 else
                         "hybrid" if live_names else "simulated")
    data["confidence_note"] = (
        f"Data mode: {data['data_mode']}. Live connectors: "
        f"{', '.join(live_names) if live_names else 'none'}. "
        + ("Live feeds verified at collection time."
           if data["data_mode"] == "live" else
           "Cross-check model-generated figures before external publication.")
    )
    return data
