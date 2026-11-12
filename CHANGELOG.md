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

### Changed — Phone-first layout, bottom bar removed
- Removed the five-button bottom navigation bar completely (HTML, CSS, JS, docs and
  tests). On phones the whole viewport is content; a labelled **Menu** button
  in the top bar opens the off-canvas navigation drawer, which is now the only
  navigation. Added a skip link, 48px drawer items and `touch-action`.
- Tables reflow into stacked, labelled cards on phones: a `MutationObserver`
  on `#view` copies `<th>` text onto each `<td>` as `data-label`. Headerless
  label/value tables become two-column rows. No sideways table scrolling.
- The heatmap derives its columns from `--heat-cols` and shrinks its label
  gutter / cell height to fit the viewport. Line charts scale their gutter to
  the measured container width; bar charts switch to a stacked label-over-bar
  layout below 420px so long labels can never spill off a phone screen.
- All phone grids are single-column, all controls are 16px font and >=44px
  tall (no iOS auto-zoom), long IDs wrap, and footer / chat / toasts are
  safe-area aware. The Streamlit theme drops its reserved bottom-bar space and
  gains a 380px breakpoint.
- Responsive regression tests now assert the bar can never return plus the
  stacked-table, iOS-zoom, touch-target and fluid-chart contracts.

### Added — OpenRouter free-model auto-selection
- `OpenRouter (Free)` now defaults to **Auto — best free model (live)** instead
  of a hard-coded, retired `:free` slug. A new `app/api/openrouter_auto.py`
  queries the public `/api/v1/models` catalogue (no key, no credits), keeps
  zero-price text→text chat models, ranks them by context, output length,
  JSON/tool support, published benchmark scores, freshness and model size,
  and caches the result for 15 minutes.
- All-free `models` failover chains plus local re-resolution on 404/429/5xx;
  failed models are cooled down for five minutes and a 404 forces a catalogue
  refresh. Offline or disabled mode degrades to `openrouter/free` with no
  hard-coded, possibly retired slugs. `openrouter/auto` and paid fallbacks are
  never used.
- The router now reports OpenRouter's authoritative `response.model` (the free
  model that actually answered) instead of the requested sentinel, and omits
  `response_format` when the selected model does not support structured output.
- Settings gains a live ranking panel with a refresh action, friendly labels
  for the auto sentinels, and `GET /api/settings/openrouter/models`. The
  Streamlit settings page shows the same ranking. Any `:free` slug can be
  pinned; paid slugs are rejected on a free provider.
- Existing keys with the retired `llama-3-8b-instruct:free` /
  `mistral-7b-instruct:free` slugs are transparently upgraded to Auto.
- 26 new mocked regression tests (`tests/test_openrouter_auto.py`, including
  one against the real `/api/v1/models` payload shape); suite now 85 tests.
  New optional env vars: `MERIDIAN_OPENROUTER_AUTO`,
  `MERIDIAN_OPENROUTER_CATALOG_TTL`, `MERIDIAN_OPENROUTER_CATALOG_TIMEOUT`,
  `MERIDIAN_OPENROUTER_FALLBACKS`.

### Added — Responsive layout
- Complete breakpoint system (≤1500 / ≤1280 / ≤1100 / ≤700 / ≤480 / ≤380 /
  ≥1800 / short landscape / reduced motion), plus iOS safe-area insets and
  visible focus rings.
- Tablet/phone layout: full-width single column, off-canvas navigation and
  Agent Activity drawers with a scrim.
- The menu button now has a real function everywhere: collapse/expand the
  sidebar on desktop (persisted), open/close the navigation drawer on small
  screens (Escape, backdrop, ✕, focus trap and focus restore).
- New Activity button: hide/show the telemetry panel on desktop, open the
  telemetry drawer on small screens, with a live-pulse indicator.
- Phone-friendly forms (16px inputs to stop iOS zoom, fluid selectors,
  full-width actions), wrapping card headers, fluid charts, and compact chat +
  toast + footer placement.
- Equivalent responsive CSS for the secondary Streamlit frontend.

### Fixed
- No more clipped, off-screen or unusable content on narrow viewports.
- Charts reflow on resize, orientation change and sidebar/drawer transitions.
- Sidebar collapse no longer destroys navigation on tablet widths.
