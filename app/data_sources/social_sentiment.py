"""Cross-channel social sentiment aggregation."""
from __future__ import annotations

from typing import Any, Dict

from app.data_sources.reddit_scraper import get_reddit_sentiment


def aggregate(dataset: Dict[str, Any]) -> Dict[str, Any]:
    """Merge live Reddit signals into the offline sentiment channels."""
    live = get_reddit_sentiment(dataset.get("company", "")) if dataset.get("company") else {"live": False}
    channels = [dict(c) for c in dataset.get("sentiment", [])]
    if live.get("live") and live.get("average") is not None:
        for c in channels:
            if c["channel"] == "Reddit":
                c["score"] = live["average"]
                c["volume"] = len(live.get("posts", [])) * 37 + 400
    overall = round(sum(c["score"] * c["volume"] for c in channels) /
                    max(1, sum(c["volume"] for c in channels)), 3)
    return {"channels": channels, "overall": overall,
            "live": bool(live.get("live")), "reddit_posts": live.get("posts", []),
            "label": "Positive" if overall >= 0.6 else ("Neutral" if overall >= 0.45 else "Cautious")}
