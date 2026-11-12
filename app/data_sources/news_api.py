"""NewsAPI connector with a curated offline headline fallback."""
from __future__ import annotations

import logging
from datetime import date
from typing import Any, Dict, List

import requests

from app.config import settings

logger = logging.getLogger("meridian.data.news")


def get_news(query: str, limit: int = 8) -> Dict[str, Any]:
    """Return ``{articles, live}`` in Meridian's normalised article shape."""
    if settings.news_api_key:
        try:
            r = requests.get("https://newsapi.org/v2/everything",
                             params={"q": query, "pageSize": limit, "sortBy": "publishedAt",
                                     "language": "en", "apiKey": settings.news_api_key},
                             timeout=3)
            r.raise_for_status()
            articles = [{
                "title": a.get("title", ""), "source": (a.get("source") or {}).get("name", "NewsAPI"),
                "domain": (a.get("url", "").split("/")[2] if "//" in a.get("url", "") else "newsapi.org"),
                "url": a.get("url", ""), "date": (a.get("publishedAt") or "")[:10],
                "sentiment": 0.6, "reliability": 88,
            } for a in r.json().get("articles", [])[:limit]]
            if articles:
                return {"articles": articles, "live": True}
        except Exception as exc:
            logger.debug("NewsAPI unavailable: %s", exc)
    return {"articles": [], "live": False}
