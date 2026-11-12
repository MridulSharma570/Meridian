# Meridian — System Architecture

**Version 1.0.0 · Developed by Mridul Sharma**

---

## 1. Overview

Meridian converts a single free-text market question into a complete, verified,
exportable research report. Two frontends share one Python service layer:

- **Premium SPA** (default) — dependency-free HTML/CSS/JS served by FastAPI.
- **Streamlit frontend** — `app/main.py`, with a full CSS theme override.

Both call the same `app/services.py` facade, which drives the agent graph and
persistence. There is no duplicated business logic.

```
┌─────────────────────────────────────────────────────────────────────────┐
│  BROWSER   Premium SPA (app/web)      Streamlit UI (app/ui, optional)    │
│            sidebar · dashboard · report · compare · history · settings    │
└────────────────────────────┬────────────────────────────────────────────┘
                             │ REST /api + SSE /api/reports/{id}/events
┌────────────────────────────▼────────────────────────────────────────────┐
│  FASTAPI  app/api/server.py                                              │
│  33 routes · CORS · static files · structured JSON errors · lifespan      │
└────────────────────────────┬────────────────────────────────────────────┘
                             │
┌────────────────────────────▼────────────────────────────────────────────┐
│  SERVICE LAYER  app/services.py                                          │
│  ReportJob registry · background threads · SSE event bus · exports        │
│  chat · translation · comparison · filters · settings · bootstrap         │
└──────┬──────────────────────────┬───────────────────────┬───────────────┘
       │                          │                       │
┌──────▼──────────┐   ┌───────────▼──────────┐   ┌───────▼───────────────┐
│ ORCHESTRATOR    │   │  DATA SOURCES        │   │  API KEY VAULT + ROUTER│
│ app/agents/     │   │  collector.py        │   │  key_manager (Fernet)  │
│ orchestrator.py │◄──┤  web · yahoo · news  │   │  providers.py (16)     │
│                 │   │  reddit · world bank │   │  llm_router.py         │
│ LangGraph-style │   │  demo_data.py        │   │                        │
│ typed state DAG │   └──────────────────────┘   └────────────────────────┘
└──────┬──────────┘
       │
┌──────▼──────────────────────────────────────────────────────────────────┐
│  PERSISTENCE  app/database   PostgreSQL (JSONB) | SQLite fallback        │
│  users · api_keys · reports · chat_history · agent_logs · comparisons ·   │
│  translations      + optional Redis cache                                 │
└─────────────────────────────────────────────────────────────────────────┘
```

## 2. Agent graph

```
                    ┌───────────────┐
   query + filters  │  researcher   │  live connectors + offline engine
 ──────────────────►│   (Agent 1)   │──────────────┐
                    └───────────────┘              │ typed state dict
                                                  ▼
                    ┌───────────────┐       ┌──────────────┐
                    │    analyst    │◄──────│  researcher  │
                    │   (Agent 2)   │       │   output     │
                    └───────┬───────┘       └──────────────┘
                            │  fan-out over ThreadPoolExecutor(3)
            ┌───────────────┼─────────────────┐
            ▼               ▼                 ▼
     ┌────────────┐  ┌────────────┐  ┌────────────────┐
     │  writer    │  │ forecast   │  │ factchecker    │
     │ (Agent 3)  │  │ (Agent 5)  │  │  (Agent 6)     │
     └─────┬──────┘  └─────┬──────┘  └───────┬────────┘
           └───────────────┼──────────────────┘
                           ▼  barrier
                   ┌────────────────┐
                   │ chat (Agent 4) │  branch: on-demand, not in the pipeline
                   └───────┬────────┘
                           ▼  conditional edge (language != en)
                   ┌────────────────┐
                   │  translator    │  14 languages
                   └────────────────┘
```

Each node is wrapped by `BaseAgent.run()`:

1. `local_run(ctx)` produces a **complete** result from the deterministic engine.
2. If that slot has an active key, `call_llm()` enriches it with a JSON-mode
   provider call; `extract_json()` repairs fenced / noisy output.
3. Any exception is captured as a `warning`, logged to `agent_logs`, and the
   local result is kept. **No agent can fail the report.**

## 3. Data flow

1. `POST /api/reports` → `services.start_report()` creates a `reports` row with
   `status=processing`, registers a `ReportJob`, and starts a daemon thread.
2. The thread builds an `Orchestrator` whose `emit` callback appends events to a
   condition-protected list. `GET /api/reports/{id}/events` streams them as SSE.
3. `collect_market_data()` runs five connectors in parallel under a six-second
   budget, overlaying successful live results on the deterministic baseline.
   `data_mode` is `live` (3+ connectors), `hybrid` (1–2) or `simulated` (0).
4. Agent outputs are persisted as JSONB columns; the Writer's markdown goes to
   `final_report`; the reliability score comes from the Fact-Checker.
5. `generate_exports()` writes PDF / PPTX / XLSX into `data/exports/`, then the
   row is marked `completed` and a `job_complete` event is emitted.
6. The SPA listens to SSE, paints the mission-control panel, and navigates to
   the finished report automatically.

## 4. Resilience matrix

| Failure | Behaviour |
|---------|-----------|
| No API key anywhere | Full pipeline via local analytical engine |
| Provider 401 / 429 / timeout | Warning + local fallback, other agents continue |
| Malformed LLM JSON | `extract_json()` repair, then local fallback |
| Connector unreachable | That connector marked `offline`, report continues |
| PostgreSQL/Redis down | SQLite / no cache |
| Export engine error | PDF falls back to a minimal valid PDF; other exports isolated |
| Undecryptable stored key | Slot treated as unconfigured, clear Settings message |

## 5. Security model

- Fernet encryption before any DB write; only masked keys leave the server.
- `MERIDIAN_FERNET_KEY` from env or a `0600` local file, never committed.
- Provider errors pass through `_safe()` which redacts key-shaped strings.
- No authentication layer: intended for trusted/local/demo use. Put behind SSO
  in production (see `docs/DEPLOYMENT.md`).

## 6. Design system

Signature trio: **Deep Navy `#0A1628`**, **Champagne Gold `#C9A84C`**,
**Ivory Platinum `#EDE4D3`**. Sapphire `#4C7BF3` and amethyst `#8B7CF6` appear
only in gradient accents. Satoshi Bold / Inter / JetBrains Mono, 4px type grid,
8px spacing, 16px glassmorphic cards, layered shadows, dark mode only.

All charts are hand-built interactive SVG — no CDN JavaScript, no build step.
