# Changelog

All notable changes to **Meridian — Market Intelligence, Redefined.** are documented
here. Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

**Developed by Mridul Sharma**

## [1.0.0] — 2026-11-12

### Added — Core platform
- Complete multi-agent pipeline: Researcher, Analyst, Writer, Chat, Forecast,
  Fact-Checker and Translator, coordinated by a LangGraph-style state graph with
  parallel fan-out and per-agent failure isolation.
- Seven independent, Fernet-encrypted API key slots with 16 free/paid providers,
  per-slot model selection, live **Test Connection**, quota-header capture and
  "apply one key to all slots" quick setup.
- Deterministic, query-aware offline analytical engine so the entire product is
  fully functional with zero API keys. Every figure is labelled
  `simulated` / `hybrid` / `live` and modelled claims are flagged ⚠️.
- Live connectors: Tavily / DuckDuckGo, Yahoo Finance (+ optional yfinance),
  NewsAPI, Reddit sentiment, World Bank macro indicators — all parallel,
  time-boxed and failure-isolated.
- Interactive dashboard: market trajectory, share donut, revenue trend,
  sentiment heatmap, segment bars, macro indicators, 12-month forecast with
  confidence bands — all hand-built SVG with hover tooltips and togglable series.
- Region / period / competitor filters that recompute every chart.
- Comparison mode for two companies and two saved reports.
- Report history with search, status/region filters, reopen, delete and compare.
- Grounded follow-up chat with suggested prompts and persisted history.
- Full-report translation into 14 languages preserving markdown and tables.
- Professional exports: paginated PDF (ReportLab), 8-slide PowerPoint
  (python-pptx) and 10-sheet Excel workbook with native charts (openpyxl).
- Real-time Agent Activity mission-control panel over Server-Sent Events.
- PostgreSQL + Redis support with automatic SQLite fallback; encrypted key vault.

### Added — Design & frontend
- Ultra-premium dark-only design system: Deep Navy `#0A1628`, Champagne Gold
  `#C9A84C`, Ivory Platinum `#EDE4D3`, with restrained sapphire/violet gradients.
- Satoshi Bold headings, Inter body, JetBrains Mono data type; 4px type grid,
  8px spacing grid, 16px glassmorphic cards, layered shadows, mesh gradients,
  blurred blobs, shimmer skeletons and micro-interactions.
- Fully custom dependency-free SPA plus a complete Streamlit frontend with a
  CSS override of every default widget.

### Added — Documentation & operations
- README, MIT LICENSE, CONTRIBUTING, CODE_OF_CONDUCT, SECURITY, CHANGELOG,
  `.env.example`, six docs files, Dockerfile, docker-compose (app + Postgres +
  Redis), pinned `requirements.txt`, `pyproject.toml`, three operational scripts.
- 23-test pytest suite covering agents, router, endpoints, exports and database.

### Fixed
- ReportLab `pie.slices` infinite loop during PDF generation (indexed by range).
- Lazy schema initialisation so no import order can produce "no such table".
- Graceful handling of missing keys, provider timeouts, malformed JSON and
  blocked network — the pipeline always completes.

---

## [Unreleased]

_No changes yet. Add your entries here before opening a PR._
