"""Yahoo Finance connector for price / revenue proxies.

Tries the chart endpoint first, then ``yfinance``. Falls back to Meridian's
deterministic revenue series so charts always render.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import requests

from app.config import settings

logger = logging.getLogger("meridian.data.yahoo")


def _guess_ticker(company: str) -> Optional[str]:
    known = {"tesla": "TSLA", "nvidia": "NVDA", "apple": "AAPL", "microsoft": "MSFT",
             "amazon": "AMZN", "google": "GOOGL", "meta": "META", "intel": "INTC",
             "amd": "AMD", "paypal": "PYPL", "salesforce": "CRM", "walmart": "WMT",
             "tata motors": "TTM", "reliance": "RELIANCE.NS", "infosys": "INFY"}
    c = company.lower().strip()
    for name, ticker in known.items():
        if name in c:
            return ticker
    return None


def _chart(ticker: str) -> List[Dict[str, Any]]:
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
    r = requests.get(url, params={"range": "1y", "interval": "1mo"},
                     headers={"User-Agent": "Mozilla/5.0 (Meridian/1.0)"}, timeout=3)
    r.raise_for_status()
    result = (r.json().get("chart", {}).get("result") or [{}])[0]
    closes = result.get("indicators", {}).get("quote", [{}])[0].get("close", [])
    stamps = result.get("timestamp", [])
    out = []
    for ts, close in zip(stamps, closes):
        if close is not None:
            from datetime import datetime, timezone
            label = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%b'%y")
            out.append({"label": label, "price": round(float(close), 2)})
    return out


def get_financials(company: str) -> Dict[str, Any]:
    """Return ``{series, ticker, live, currency}``."""
    ticker = _guess_ticker(company)
    if ticker:
        try:
            series = _chart(ticker)
            if series:
                return {"series": series, "ticker": ticker, "live": True, "currency": "USD"}
        except Exception as exc:
            logger.debug("Yahoo chart unavailable for %s: %s", ticker, exc)
        # yfinance is a heavier fallback; enable explicitly when network is reliable.
        if getattr(settings, "use_yfinance", False):
            try:
                import yfinance as yf  # type: ignore
                hist = yf.Ticker(ticker).history(period="1y", interval="1mo")
                if not hist.empty:
                    return {"series": [{"label": d.strftime("%b'%y"),
                                        "price": round(float(v), 2)}
                                       for d, v in zip(hist.index, hist["Close"])],
                            "ticker": ticker, "live": True, "currency": "USD"}
            except Exception as exc:
                logger.debug("yfinance unavailable: %s", exc)
    return {"series": [], "ticker": ticker, "live": False, "currency": "USD"}
