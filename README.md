<div align="center">

```
      ◆
     ◆ ◆
    ◆   ◆
   ◆  M  ◆
    ◆   ◆
     ◆ ◆
      ◆
```

# MERIDIAN

### *Market Intelligence, Redefined.*

**Six autonomous AI agents + one translator. One query. A board-ready market report.**

Deep Navy `#0A1628` · Champagne Gold `#C9A84C` · Ivory Platinum `#EDE4D3`

[![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![License: MIT](https://img.shields.io/badge/License-MIT-C9A84C)](LICENSE)
[![Version](https://img.shields.io/badge/version-1.0.0-C9A84C)](#changelog)

</div>

---

## 📸 Screenshots

> Replace these placeholders with screenshots from your live demo.

| Dashboard | Intelligence Report |
|-----------|---------------------|
| `docs/screenshots/dashboard.png` — navy hero, gold query composer, KPI cards, live agent activity rail | `docs/screenshots/report.png` — interactive charts, confidence-band forecast, verification scores |

| API Keys | Compare Mode |
|----------|--------------|
| `docs/screenshots/settings.png` — seven encrypted key slots, provider dropdowns, Test Connection | `docs/screenshots/compare.png` — head-to-head dimension scorecard |

---

## ⚡ Quick start

```bash
git clone https://github.com/MridulSharma570/Meridian.git
cd Meridian
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python run.py                      # → http://localhost:8000
```

That's it — **no API keys, no database setup, no Docker required**. On first boot
Meridian creates its SQLite schema, generates a `0600` Fernet key and seeds one
complete demo report so the dashboard is never empty. Interactive API docs:
**http://localhost:8000/docs**.

> **Deploying to Render and the site keeps shutting down?** Render **Free** spins
> services down after 15 minutes idle — no code can disable it. Switch to
> **Starter** for guaranteed always-on, or use the included external
> `/api/ping` keep-alive as a free workaround. This repo also fixes Render's
> `PORT=10000` binding and ephemeral-disk data loss.
> 👉 [docs/RENDER_DEPLOYMENT.md](docs/RENDER_DEPLOYMENT.md)

```bash
python run.py --streamlit           # optional Streamlit frontend on :8501
python -m scripts.seed_data         # four curated demo reports
pytest -q                          # 88 tests
docker compose up -d --build        # full stack: app + Postgres + Redis
```

---

## ✨ What it actually does

| Capability | Detail |
|------------|--------|
| **7-agent pipeline** | Researcher → Analyst → (Writer ‖ Forecast ‖ Fact-Checker) → Chat → Translator, orchestrated as a LangGraph-style typed state DAG with parallel fan-out |
| **Failure isolation** | A missing key, 401, 429, timeout or malformed JSON never stops a report — each agent falls back to the local analytical engine and logs a warning |
| **Independent API keys** | Six encrypted slots + optional translator, **16 free/paid providers**, per-slot model choice, real **Test Connection**, quota headers, "apply one key to all" |
| **Works with zero keys** | A deterministic, query-aware analytical engine produces consistent market sizing, SWOT, PESTLE, Porter's Five Forces, sentiment, sources and a 12-month forecast — clearly labelled `simulated` |
| **Live data** | Tavily / DuckDuckGo, Yahoo Finance, NewsAPI, Reddit sentiment, World Bank macro — parallel, time-boxed, failure-isolated; data mode becomes `hybrid` → `live` |
| **Interactive charts** | Market trajectory, share donut, revenue trend, sentiment heatmap, segment bars, macro indicators, forecast with confidence band. Hand-built SVG: hover tooltips, togglable series, live region/period/competitor filters |
| **Exports** | Paginated PDF with vector charts · 8-slide PowerPoint · 10-sheet Excel with native charts |
| **Follow-up chat** | Grounded Q&A over the report context with citation ids and saved history |
| **Translation** | 14 languages; full neural translation with a key, honest structural translation without one, markdown and tables preserved |
| **Compare** | Company vs company and report vs report, with verdicts and scorecards |
| **History** | Search, filter, reopen, delete and compare every past report |
| **Mission control** | Live agent status over Server-Sent Events, elapsed times, provider used, progress bar |
| **Responsive by design** | Desktop three-column grid with collapsible sidebar and toggleable telemetry; tablets/phones get a single full-width column, a labelled **Menu** button opening an off-canvas drawer with a scrim, and **no bottom bar**. Stacked tables, viewport-fitting charts/heatmap, 16px inputs and 44px touch targets. Breakpoints from 320px to 1800px+, iOS safe areas, reduced-motion support |
| **Persistence** | PostgreSQL + JSONB + Redis, with automatic SQLite/no-cache fallback |

---

## 🏛 Architecture (ASCII)

```
┌───────────────────────────────────────────────────────────────────────┐
│   MERIDIAN FRONTEND     Premium SPA (app/web)  +  Streamlit (app/ui)   │
│   Dashboard │ Report │ Compare │ History │ API Keys │ Agent Activity   │
└──────────────────────────────┬────────────────────────────────────────┘
                               │  REST /api  ·  SSE /events
┌──────────────────────────────▼────────────────────────────────────────┐
│   FastAPI (app/api/server.py)  →  services.py  →  Orchestrator         │
│                                                                        │
│   ┌──────────┐   ┌──────────┐   ┌────────────────────────────────┐   │
│   │Agent 1 🔍│──►│Agent 2 📊│──►│ Agent 3 ✍️ ‖ 5 📈 ‖ 6 ✅ (parallel)│   │
│   └──────────┘   └──────────┘   └───────────────┬────────────────┘   │
│         │                                       │                     │
│   Data sources: web · Yahoo · News · Reddit · World Bank               │
│                                       ┌─────────▼─────────┐            │
│                                       │ Agent 4 💬  Chat  │            │
│                                       │   🌐 Translator    │            │
│                                       └─────────┬─────────┘            │
└─────────────────────────────────────────────────┼──────────────────────┘
                                                  │
┌─────────────────────────────────────────────────▼──────────────────────┐
│  Key Vault (Fernet) · LLM Router (16 providers) · PDF/PPTX/XLSX         │
│  PostgreSQL + Redis  |  SQLite fallback                                 │
└────────────────────────────────────────────────────────────────────────┘
```

Full detail: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

---

## 📁 Folder structure

```
meridian/
├── README.md  LICENSE  CONTRIBUTING.md  CHANGELOG.md
├── CODE_OF_CONDUCT.md  SECURITY.md  .env.example  .gitignore
├── requirements.txt  pyproject.toml  Dockerfile  docker-compose.yml  run.py
├── render.yaml  docker-entrypoint.sh  .dockerignore  # Render Blueprint
├── deploy/      keep-alive-workflow.yml (GitHub Actions template)
├── docs/        ARCHITECTURE · API_REFERENCE · DEPLOYMENT · USER_GUIDE
│                API_KEYS_SETUP · TROUBLESHOOTING · RENDER_DEPLOYMENT
├── app/
│   ├── main.py            # Streamlit entry point
│   ├── config.py          # settings & constants
│   ├── services.py        # product behaviour (jobs, chat, exports, settings)
│   ├── agents/            # orchestrator + 6 agents + translator + base
│   ├── api/               # server.py, llm_router, providers, key_manager
│   ├── data_sources/      # web, yahoo, news, reddit, sentiment, world_bank,
│   │                      # collector, demo_data
│   ├── export/            # pdf_generator, pptx_generator, excel_generator
│   ├── database/          # connection, models, queries
│   ├── ui/                # theme, components, 5 Streamlit pages
│   ├── web/               # index.html, app.css, app.js, favicon.svg
│   └── assets/            # custom.css, fonts/, icons/, images/
├── scripts/     setup_db.py · seed_data.py · migrate.py · healthcheck.py
│                keepalive.py (external Render pinger)
└── tests/       test_agents · test_api_router · test_export · test_database
                 test_render_deployment · test_openrouter_auto
```

---

## 🔑 API keys — enter them here

Open **Settings → API Keys** in the app (or **API Keys** in Streamlit).

- Six independent agent slots + an optional translator slot.
- Provider dropdown grouped into **FREE** (Groq, Gemini, OpenRouter Free,
  Hugging Face, Cohere, Cerebras, Ollama) and **PAID** (OpenAI, Anthropic,
  Gemini Pro, Mistral, Perplexity, Together, Fireworks, DeepSeek, OpenRouter Paid).
- **Same key in every slot?** Use the **Quick setup** bar — one paste, all slots.
- **Mix providers?** Just pick a different provider per card.
- **Test Connection** makes a real minimal request and reports provider, latency
  and quota headers.
- **OpenRouter (Free) auto-selection:** the default model is
  **Auto — best free model (live)**. Meridian reads OpenRouter's public
  `GET /api/v1/models` catalogue, keeps only zero-price text→text chat models,
  ranks them (context window, output length, JSON/tool support, published
  benchmark scores, freshness) and attaches an **all-free** fallback chain. A retired or rate-limited `:free`
  model is replaced automatically; OpenRouter's `openrouter/auto` and paid
  models are never used, so the free tier stays free. Inspect the current
  ranking in **Settings → Auto-select the best available free model** or at
  `GET /api/settings/openrouter/models`. Retired hard-coded slugs in existing
  saved keys are upgraded automatically. See
  [docs/API_KEYS_SETUP.md](docs/API_KEYS_SETUP.md#3-openrouter-free).
- Keys are **Fernet-encrypted before storage**; only masked values are returned
  to the browser. They are never logged, exported or committed.

Step-by-step instructions for all 16 providers: [docs/API_KEYS_SETUP.md](docs/API_KEYS_SETUP.md).

> The platform is fully functional **without any key**. Add keys to upgrade from
> the deterministic local engine to live LLM-written analysis, neural
> translation and real-time data.

---

## 🎨 Design system

| Token | Value | Use |
|-------|-------|-----|
| Deep Navy | `#0A1628` | Primary background |
| Champagne Gold | `#C9A84C` | Accents, CTAs, highlights |
| Ivory Platinum | `#EDE4D3` | Premium type, logo, emphasis |
| Secondary Navy | `#111C32` | Panels |
| Card | `#1A2744` | Glassmorphism (`blur(20px)`, `1px rgba(255,255,255,.08)`) |
| Success / Danger | `#059669` / `#E11D48` | Trends, verification |

**Typography:** Satoshi Bold (headings, Fontshare) · Inter (body, Google Fonts) ·
JetBrains Mono (data). 4px type grid, 8px spacing, 16px radius, layered soft
shadows, mesh gradients, blurred blobs, shimmer loading states, micro-interactions.
Dark mode only. No CDN JavaScript, no build step.

---

## 🧰 Tech stack

Python 3.11 · FastAPI · Uvicorn · SQLAlchemy 2 · PostgreSQL/SQLite · Redis ·
Cryptography (Fernet) · Plotly · ReportLab · python-pptx · openpyxl ·
Streamlit · vanilla HTML/CSS/JS · pytest · Docker / Docker Compose.

---

## 📚 Documentation

| Document | Contents |
|----------|----------|
| [USER_GUIDE.md](docs/USER_GUIDE.md) | Every screen, every feature, screenshot descriptions |
| [API_REFERENCE.md](docs/API_REFERENCE.md) | All 34 endpoints with examples |
| [ARCHITECTURE.md](docs/ARCHITECTURE.md) | Agent graph, data flow, resilience, security |
| [DEPLOYMENT.md](docs/DEPLOYMENT.md) | Local, Docker, Compose, cloud, Nginx, backups |
| [RENDER_DEPLOYMENT.md](docs/RENDER_DEPLOYMENT.md) | **Fix Render shutting down** — Free spin-down, Starter plan, keep-alive, `PORT`, Postgres |
| [API_KEYS_SETUP.md](docs/API_KEYS_SETUP.md) | How to get keys from all 16 providers |
| [TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) | Errors and exact fixes |
| [CONTRIBUTING.md](CONTRIBUTING.md) | PR process and code style |
| [SECURITY.md](SECURITY.md) | Vulnerability reporting and key policy |

---

## ⚠️ Data honesty

When live feeds or LLM keys are unavailable, Meridian's deterministic engine
generates **model estimates**. These are explicitly labelled `SIMULATED` in the
data-mode badge, in the report, in the source appendix and by the Fact-Checker's
⚠️ flags. Confirm them against primary sources before external or investment use.
Add `TAVILY_API_KEY`, `NEWS_API_KEY` and provider keys to switch to `LIVE`.

---

## 📄 License

MIT — see [LICENSE](LICENSE). Contributions welcome via [CONTRIBUTING.md](CONTRIBUTING.md).

---

<div align="center">

**Developed by Mridul Sharma**

*Meridian v1.0.0 — Market Intelligence, Redefined.*

</div>
