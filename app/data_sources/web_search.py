"""Web search connector: Tavily (keyed) → DuckDuckGo HTML → offline corpus.

Every failure degrades quietly; Meridian never blocks a report on a network
call. Results always have the same shape.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List

import requests
from bs4 import BeautifulSoup

from app.config import settings

logger = logging.getLogger("meridian.data.web")


def _tavily(query: str, limit: int) -> List[Dict[str, Any]]:
    if not settings.tavily_api_key:
        return []
    r = requests.post("https://api.tavily.com/search",
                      json={"api_key": settings.tavily_api_key, "query": query,
                            "max_results": limit, "search_depth": "basic"}, timeout=3)
    r.raise_for_status()
    return [{"title": x.get("title", ""), "url": x.get("url", ""),
             "snippet": x.get("content", "")[:400], "source": "Tavily"}
            for x in r.json().get("results", [])][:limit]


def _duckduckgo(query: str, limit: int) -> List[Dict[str, Any]]:
    r = requests.get("https://html.duckduckgo.com/html/", params={"q": query},
                     headers={"User-Agent": "Mozilla/5.0 (Meridian/1.0)"}, timeout=3)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    out = []
    for node in soup.select(".result")[:limit]:
        a = node.select_one(".result__a")
        snippet = node.select_one(".result__snippet")
        if a:
            out.append({"title": a.get_text(" ", strip=True), "url": a.get("href", ""),
                        "snippet": snippet.get_text(" ", strip=True)[:400] if snippet else "",
                        "source": "DuckDuckGo"})
    return out


def search_web(query: str, limit: int = 8) -> Dict[str, Any]:
    """Return ``{results, live}`` — ``live`` is False when using the corpus."""
    for fn in (_tavily, _duckduckgo):
        try:
            results = fn(query, limit)
            if results:
                return {"results": results, "live": True, "engine": fn.__name__.lstrip("_")}
        except Exception as exc:
            logger.debug("Web search via %s unavailable: %s", fn.__name__, exc)
    return {"results": [], "live": False, "engine": "offline-corpus"}
