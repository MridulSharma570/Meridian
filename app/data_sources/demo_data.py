"""Meridian's offline SAMPLE engine (explicit opt-in only).

Production Meridian never uses this module to answer a user. When
``MERIDIAN_SAMPLE_MODE`` is explicitly enabled for tests/UI demos, it produces
an internally consistent, *query-aware* sample dataset.
The output is deterministic (seeded by the query + filters) so a saved report
always reproduces its charts exactly. Live connectors overwrite pieces of this
dataset when they succeed; ``data_mode`` records which path was used.
"""
from __future__ import annotations

import hashlib
import math
import random
import re
from datetime import date, timedelta
from typing import Any, Dict, List, Tuple

SECTORS: Dict[str, Dict[str, Any]] = {
    "electric vehicles": {"label": "Electric Vehicles & Mobility", "base": 148.0, "cagr": 21.4,
        "rivals": ["Tesla", "BYD", "Hyundai / Kia", "Rivian", "Tata Motors", "Volkswagen Group"]},
    "semiconductor": {"label": "Semiconductors & Components", "base": 612.0, "cagr": 12.8,
        "rivals": ["NVIDIA", "TSMC", "Intel", "Samsung Electronics", "AMD", "Qualcomm"]},
    "fintech": {"label": "Financial Technology", "base": 224.0, "cagr": 18.9,
        "rivals": ["Stripe", "PayPal", "Razorpay", "Block", "Adyen", "Revolut"]},
    "saas": {"label": "Enterprise SaaS & Cloud", "base": 318.0, "cagr": 16.2,
        "rivals": ["Salesforce", "Microsoft", "Oracle", "SAP", "ServiceNow", "Adobe"]},
    "artificial intelligence": {"label": "Artificial Intelligence Platforms", "base": 196.0, "cagr": 34.6,
        "rivals": ["OpenAI", "Google DeepMind", "Anthropic", "Microsoft", "Meta", "NVIDIA"]},
    "e-commerce": {"label": "E-Commerce & Retail Tech", "base": 542.0, "cagr": 11.7,
        "rivals": ["Amazon", "Flipkart", "Alibaba", "Shopify", "Walmart", "Meesho"]},
    "healthcare": {"label": "Healthcare & Pharma", "base": 468.0, "cagr": 9.4,
        "rivals": ["Johnson & Johnson", "Novartis", "Pfizer", "Sun Pharma", "Roche", "AbbVie"]},
    "renewable energy": {"label": "Renewable Energy", "base": 286.0, "cagr": 19.1,
        "rivals": ["NextEra Energy", "Adani Green", "Vestas", "First Solar", "Ørsted", "Enphase"]},
    "food": {"label": "Food & Beverage", "base": 384.0, "cagr": 7.3,
        "rivals": ["Nestlé", "PepsiCo", "Coca-Cola", "Unilever", "Danone", "Britannia"]},
    "telecom": {"label": "Telecommunications", "base": 402.0, "cagr": 6.8,
        "rivals": ["Jio", "Airtel", "Verizon", "Vodafone", "T-Mobile", "China Mobile"]},
    "consumer": {"label": "Consumer Goods & Retail", "base": 296.0, "cagr": 8.6,
        "rivals": ["Procter & Gamble", "Unilever", "Nestlé", "L'Oréal", "Samsung", "Sony"]},
}

KEYWORDS = [
    ("artificial intelligence", ("ai ", "artificial intelligence", "llm", "genai", "machine learning")),
    ("electric vehicles", ("electric vehicle", " ev ", "ev market", "battery", "tesla", "mobility")),
    ("semiconductor", ("semiconductor", "chip", "gpu", "nvidia", "wafer", "foundry")),
    ("fintech", ("fintech", "payments", "upi", "banking", "digital lending", "neobank")),
    ("saas", ("saas", "cloud software", "enterprise software", "crm", "erp")),
    ("e-commerce", ("e-commerce", "ecommerce", "online retail", "quick commerce", "marketplace")),
    ("healthcare", ("healthcare", "pharma", "hospital", "medical", "biotech", "drug")),
    ("renewable energy", ("solar", "renewable", "wind energy", "green hydrogen", "clean energy")),
    ("food", ("food", "beverage", "fmcg", "snack", "qsr", "restaurant")),
    ("telecom", ("telecom", "5g", "broadband", "wireless", "spectrum")),
]

REGION_FACTOR = {
    "Global": 1.0, "North America": 0.34, "Europe": 0.26,
    "Asia Pacific": 0.38, "India": 0.11, "LATAM": 0.09, "Middle East": 0.07,
}
PERIOD_YEARS = {"12M": 1, "3Y": 3, "5Y": 5, "10Y": 10}

# SAMPLE PLACEHOLDERS ONLY. The offline engine must never attach a real
# publisher's name or a real domain to a headline it generated itself: that
# reads as a genuine citation and is exactly the misinformation we are
# removing. ``example.invalid`` is reserved by RFC 2606 and cannot resolve.
PUBLISHERS = [
    (f"SAMPLE SOURCE {i:02d} (not a real citation)", "example.invalid", 0)
    for i in range(1, 13)
]

_STOP = {"the", "a", "an", "of", "in", "for", "and", "vs", "versus", "market",
         "analysis", "report", "industry", "india", "global", "2024", "2025",
         "2026", "size", "share", "trends", "overview", "study", "research"}


def _seed(*parts: str) -> int:
    return int(hashlib.sha256("|".join(parts).encode()).hexdigest()[:12], 16)


def detect_sector(query: str) -> str:
    q = f" {query.lower()} "
    for name, hints in KEYWORDS:
        if any(h in q for h in hints):
            return name
    return "consumer"


def clean_company(query: str) -> str:
    """Extract a sensible subject name from a free-form research query."""
    q = re.sub(r"\b(vs\.?|versus)\b", " ", query, flags=re.I)
    q = re.sub(r"[^\w\s&./+-]", " ", q)
    tokens = [t for t in q.split() if t.lower() not in _STOP and len(t) > 1]
    if not tokens:
        return "The Market"
    if len(tokens) <= 3:
        return " ".join(t.strip().title() for t in tokens)
    return " ".join(t.strip().title() for t in tokens[:3])


def split_comparison(query: str) -> Tuple[str, str] | None:
    m = re.split(r"\s+(?:vs\.?|versus|compared?\s+(?:to|with))\s+", query, flags=re.I)
    if len(m) == 2 and all(x.strip() for x in m):
        return clean_company(m[0]), clean_company(m[1])
    return None


def _series(rng: random.Random, start: float, growth: float, n: int,
            noise: float = 0.035) -> List[float]:
    out = []
    v = start
    for i in range(n):
        v *= (1 + growth) * (1 + rng.uniform(-noise, noise))
        out.append(round(v, 2))
    return out


def build_market_dataset(query: str, region: str = "Global",
                         period: str = "3Y") -> Dict[str, Any]:
    """Return the full structured dataset used by every downstream agent."""
    region = region if region in REGION_FACTOR else "Global"
    period = period if period in PERIOD_YEARS else "3Y"
    sector_key = detect_sector(query)
    meta = SECTORS[sector_key]
    company = clean_company(query)
    rng = random.Random(_seed(query.lower().strip(), region, period))
    today = date.today()

    years_n = max(3, PERIOD_YEARS[period] + 2)
    base = meta["base"] * REGION_FACTOR[region]
    cagr = meta["cagr"] * rng.uniform(0.86, 1.14)
    growth = cagr / 100.0
    start = base / ((1 + growth) ** (years_n - 1))
    history = _series(rng, start, growth, years_n, 0.02)
    years = [today.year - years_n + 1 + i for i in range(years_n)]

    rivals = meta["rivals"][:]
    if company and company.lower() not in {r.lower() for r in rivals}:
        rivals = [company] + rivals[:5]
    else:
        rivals = rivals[:6]
    raw_shares = [rng.uniform(8, 34) for _ in rivals]
    # Give the queried company a defensible leading share.
    if company.lower() not in {r.lower() for r in meta["rivals"]}:
        raw_shares[0] = max(raw_shares) * rng.uniform(1.1, 1.5)
    total = sum(raw_shares)
    shares = [round(s / total * 100, 1) for s in raw_shares]
    diff = round(100 - sum(shares), 1)
    shares[-1] = round(shares[-1] + diff, 1)

    quarters = []
    qrev = base / 4 / max(1, len(rivals)) * rng.uniform(0.8, 1.4)
    for i in range(12):
        qrev *= (1 + growth / 4) * (1 + rng.uniform(-0.05, 0.07))
        quarters.append({
            "label": f"Q{(i % 4) + 1}'{str(today.year - 3 + i // 4)[-2:]}",
            "revenue": round(qrev, 2),
            "competitor_avg": round(qrev * rng.uniform(0.72, 0.98), 2),
        })

    channels = ["News", "Reddit", "X / Social", "Analyst Notes", "Review Sites"]
    sentiment = []
    for ch in channels:
        score = rng.uniform(0.38, 0.86)
        sentiment.append({"channel": ch, "score": round(score, 3),
                          "volume": rng.randint(420, 9800),
                          "trend": round(rng.uniform(-0.14, 0.19), 3)})
    heatmap = [[round(min(0.99, max(0.02, s["score"] + rng.uniform(-0.22, 0.22))), 2)
                for _ in range(8)] for s in sentiment]
    weeks = [f"W{i+1}" for i in range(8)]

    segments = ["Enterprise", "Mid-Market", "SMB", "Consumer", "Public Sector"]
    seg_values = [round(x, 1) for x in
                  [rng.uniform(20, 40), rng.uniform(15, 28), rng.uniform(10, 22),
                   rng.uniform(8, 20), rng.uniform(5, 14)]]
    seg_total = sum(seg_values)
    segment_share = [round(v / seg_total * 100, 1) for v in seg_values]

    macro = {
        "GDP Growth (%)": round(rng.uniform(2.2, 7.4), 2),
        "Inflation (%)": round(rng.uniform(2.0, 6.8), 2),
        "Digital Penetration (%)": round(rng.uniform(48, 89), 1),
        "Consumer Confidence": rng.randint(88, 132),
        "Policy Rate (%)": round(rng.uniform(2.5, 7.5), 2),
        "FDI Inflow (USD B)": round(rng.uniform(12, 96), 1),
    }

    headlines = [
        f"{company} expands {meta['label'].lower()} footprint across {region} as demand accelerates",
        f"{meta['label']} in {region} projected to reach ${base * (1+growth):.0f}B by {today.year + 1}",
        f"Analysts revise {meta['label'].lower()} CAGR to {cagr:.1f}% on stronger enterprise adoption",
        f"{rivals[1]} and {rivals[2]} intensify pricing pressure in {region}",
        f"Regulatory tailwinds reshape competitive dynamics for {company}",
        f"Supply-chain normalisation lifts margins across the {meta['label'].lower()} value chain",
        f"Investor sentiment turns cautious as {meta['label'].lower()} valuations stretch",
        f"{company} bets on product-led growth to defend a {shares[0]:.1f}% share",
    ]
    news = []
    for i, h in enumerate(headlines):
        pub, domain, rel = PUBLISHERS[i % len(PUBLISHERS)]
        news.append({
            "title": h, "source": pub, "domain": domain,
            "url": f"https://example.invalid/sample/headline/{i+1}",
            "sample": True, "verified": False,
            "date": (today - timedelta(days=rng.randint(1, 60))).isoformat(),
            "sentiment": round(rng.uniform(0.25, 0.94), 2),
            "reliability": rel,
        })

    sources = []
    for i in range(12):
        pub, domain, rel = PUBLISHERS[i % len(PUBLISHERS)]
        sources.append({
            "id": f"S{i+1:02d}", "title": f"SAMPLE — {meta['label']} {region} outlook (not a real source)",
            "publisher": pub, "url": f"https://example.invalid/sample/{i+1}", "type":
            ["Market Data", "News", "Financial Filing", "Macro Indicator", "Expert Analysis"][i % 5],
            "year": today.year - (i % 3), "reliability": rel,
            "sample": True, "verified": False,
        })

    return {
        "company": company, "sector": meta["label"], "sector_key": sector_key,
        "region": region, "period": period, "as_of": today.isoformat(),
        "query": query, "data_mode": "sample", "sample": True,
        "verified": False, "verified_sources": [], "unverified_metrics": True,
        "market_size_usd_b": round(base, 2), "cagr_pct": round(cagr, 2),
        "forecast_growth_pct": round(cagr * rng.uniform(0.9, 1.15), 2),
        "history": [{"year": y, "value": v} for y, v in zip(years, history)],
        "competitors": [{"name": n, "share": s,
                         "revenue_usd_b": round(base * s / 100, 2),
                         "growth_pct": round(cagr * rng.uniform(0.5, 1.6), 1),
                         "sentiment": round(rng.uniform(0.35, 0.9), 2)}
                        for n, s in zip(rivals, shares)],
        "quarters": quarters, "sentiment": sentiment, "heatmap": heatmap,
        "heatmap_weeks": weeks, "heatmap_channels": channels,
        "segments": [{"name": n, "value": v} for n, v in zip(segments, segment_share)],
        "macro": macro, "news": news, "sources": sources,
        "social_mentions": [{"label": f"W{i+1}", "value": rng.randint(300, 2600)}
                            for i in range(12)],
        "keywords": [w for w in re.findall(r"[A-Za-z]{4,}", query.lower()) if w not in _STOP][:8],
        "risk_events": [
            {"event": "Input-cost inflation", "probability": round(rng.uniform(.2, .7), 2),
             "impact": "Medium"},
            {"event": "Regulatory change", "probability": round(rng.uniform(.2, .6), 2),
             "impact": "High"},
            {"event": "New entrant disruption", "probability": round(rng.uniform(.25, .75), 2),
             "impact": "High"},
            {"event": "Currency volatility", "probability": round(rng.uniform(.15, .5), 2),
             "impact": "Low"},
        ],
        "confidence_note": (
            "SAMPLE MODE: every figure, headline and 'source' here is generated "
            "deterministically for UI testing. None of it is real research. "
            "Configure a provider API key and live data connectors for real answers."
        ),
    }


def build_comparison(company_a: str, company_b: str, region: str = "Global") -> Dict[str, Any]:
    """Deterministic head-to-head dataset for Compare mode."""
    a = build_market_dataset(company_a, region, "3Y")
    b = build_market_dataset(company_b, region, "3Y")
    metrics = [
        {"metric": "Market share", "a": a["competitors"][0]["share"],
         "b": b["competitors"][0]["share"], "unit": "%"},
        {"metric": "Est. revenue", "a": a["competitors"][0]["revenue_usd_b"],
         "b": b["competitors"][0]["revenue_usd_b"], "unit": "USD B"},
        {"metric": "Growth rate", "a": a["cagr_pct"], "b": b["cagr_pct"], "unit": "%"},
        {"metric": "Brand sentiment", "a": round(a["sentiment"][0]["score"] * 100, 1),
         "b": round(b["sentiment"][0]["score"] * 100, 1), "unit": "/100"},
        {"metric": "Source reliability", "a": 91, "b": 88, "unit": "/100"},
    ]
    return {"company_a": company_a, "company_b": company_b, "region": region,
            "metrics": metrics, "dataset_a": a, "dataset_b": b,
            "verdict": (f"{company_a} leads on {sum(1 for m in metrics if m['a'] >= m['b'])} "
                        f"of {len(metrics)} tracked dimensions; {company_b} retains an edge in "
                        f"the remaining {sum(1 for m in metrics if m['a'] < m['b'])}.")}
