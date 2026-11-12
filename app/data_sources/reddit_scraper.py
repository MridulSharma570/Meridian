"""Public Reddit sentiment connector (no credentials required)."""
from __future__ import annotations

import logging
from typing import Any, Dict, List

import requests

logger = logging.getLogger("meridian.data.reddit")

POSITIVE = {"grow", "growth", "great", "best", "love", "strong", "bullish", "win",
            "innovative", "impressive", "profit", "demand", "leading", "solid"}
NEGATIVE = {"drop", "fall", "bad", "worst", "hate", "weak", "bearish", "risk",
            "concern", "decline", "overpriced", "scam", "delay", "loss"}


def score_text(text: str) -> float:
    words = {w.strip(".,!?").lower() for w in text.split()}
    pos = len(words & POSITIVE)
    neg = len(words & NEGATIVE)
    return round(min(0.95, max(0.05, 0.5 + (pos - neg) * 0.09)), 2)


def get_reddit_sentiment(query: str, limit: int = 12) -> Dict[str, Any]:
    try:
        r = requests.get("https://www.reddit.com/search.json",
                         params={"q": query, "limit": limit, "sort": "relevance", "t": "year"},
                         headers={"User-Agent": "Meridian/1.0 (market research)"}, timeout=3)
        r.raise_for_status()
        posts = (r.json().get("data", {}).get("children", []))
        items = []
        for p in posts[:limit]:
            d = p.get("data", {})
            title = d.get("title", "")
            if title:
                items.append({"title": title[:160], "subreddit": d.get("subreddit", "r/all"),
                              "score": d.get("score", 0), "sentiment": score_text(title),
                              "url": "https://reddit.com" + d.get("permalink", "")})
        if items:
            avg = round(sum(i["sentiment"] for i in items) / len(items), 3)
            return {"posts": items, "average": avg, "live": True}
    except Exception as exc:
        logger.debug("Reddit unavailable: %s", exc)
    return {"posts": [], "average": None, "live": False}
