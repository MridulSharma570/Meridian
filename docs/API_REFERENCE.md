# Meridian — Internal API Reference

**Base URL:** `http://localhost:8000` · **Interactive docs:** `/docs` · **OpenAPI:** `/openapi.json`
**Version 1.0.0 · Developed by Mridul Sharma**

All requests and responses are JSON unless stated. Errors return
`{"detail": "..."}`, with `400` for bad input, `404` for missing resources and
`500` for unexpected failures. Every endpoint is CORS-enabled and uses relative
paths only.

Generated-answer endpoints fail closed. When no provider API key is configured,
when a provider call fails, or when no live evidence can be collected, they
return **409** with `{"error":"answer_unavailable","reason":"api_key_required",
"message":"...","hint":"...","setup_path":"#/settings"}` rather than a
template-generated answer.

---

## System

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/` | Premium SPA (`text/html`) |
| `GET` | `/static/{file}` | `app.css`, `app.js`, `favicon.svg` |
| `GET`, `HEAD` | `/api/ping` | Ultra-light, no-database liveness probe with `Cache-Control: no-store`. Use for Render health checks and external keep-alive monitors. |
| `GET`, `HEAD` | `/api/health` | Liveness, version, DB engine, platform, port, warm-up state, keep-alive counters, developer |
| `GET` | `/api/bootstrap` | First-load payload: app info, stats, settings, agents, pipeline and `readiness`. No sample report is seeded in production mode. |
| `GET` | `/api/readiness` | Whether answers are enabled, configured LLM slots, sample mode and live-connector status. |
| `GET` | `/api/stats` | Totals, average reliability, sources, agent runs, active keys |
| `GET` | `/api/agents` | Agent metadata, pipeline stages, chat suggestions |
| `GET` | `/api/providers` | All 16 providers, tier, models, hints, signup URLs |
| `GET` | `/api/languages` | 14 supported languages (`code`, `name`, `native`) |
| `GET` | `/api/agent-logs/{report_id}` | Raw agent execution telemetry |

**Example** `GET /api/health`
```json
{"status":"healthy","app":"Meridian","version":"1.0.0",
 "tagline":"Market Intelligence, Redefined.","developer":"Mridul Sharma",
 "database":"sqlite","platform":"local","port":8000,"warming_up":false,
 "keepalive":{"enabled":false,"interval_s":600,"target":"","successes":0,"failures":0},
 "demo_mode":false,"readiness":{"answers_enabled":false,"reason":"api_key_required"}}
```

**Example** `GET /api/ping`
```json
{"ok":true,"ts":1762920000,"service":"meridian"}
```

> On Render, `platform` is `render` and `port` is `10000`. See
> [RENDER_DEPLOYMENT.md](RENDER_DEPLOYMENT.md) for the idle spin-down fix.

---

## Reports

### `POST /api/reports`
Create a report and start the agent pipeline. Returns `201`.
```json
{"query":"Indian electric vehicle market 2026","region":"India",
 "period":"5Y","language":"en"}
```
```json
{"report_id":"0cb3b714-...","status":"processing",
 "events_url":"/api/reports/0cb3b714-.../events"}
```
`query` 3–600 chars · `region` one of Global, North America, Europe,
Asia Pacific, India, LATAM, Middle East · `period` `12M|3Y|5Y|10Y` ·
`language` any supported code.

### `GET /api/reports`
List reports. Query params: `search`, `status`, `region`, `limit` (1–500),
`offset`. Returns a **plain array** of report summaries.

### `GET /api/reports/{id}`
Full persisted row: all seven agent outputs (`JSONB`), `final_report`,
`translated_report`, `reliability_score`, export paths, timestamps.

### `GET /api/reports/{id}/dashboard`
Chart-ready view. Query params `region`, `period`, `competitor` recompute all
charts. Returns `report`, `dataset`, `charts`, `filters`, `analysis`, `forecast`,
`factcheck`, `writer`, `selected_competitor`, `agent_logs`, `sources`.

### `GET /api/reports/{id}/status`
```json
{"report_id":"...","status":"completed","progress":100,
 "agents":{"researcher":{"status":"done","elapsed_ms":25,...}},
 "events":23,"elapsed_s":1.2,"error":""}
```

### `GET /api/reports/{id}/events`  *(text/event-stream)*
Server-Sent Events. Optional `from_index` replays from an offset. Event types:
`start`, `agent_start`, `agent_done`, `agent_llm`, `agent_warning`, `progress`,
`exporting`, `warning`, `job_complete`, `job_failed`, `heartbeat`, `snapshot`.

### `DELETE /api/reports/{id}`
Deletes the row (cascades chat, logs and translations). Export files remain on
disk. Returns `{"ok":true,"report_id":"..."}`.

### `POST /api/reports/compare`
```json
{"report_a":"<uuid>","report_b":"<uuid>"}
```
Returns two report summaries for side-by-side comparison.

### `POST /api/reports/{id}/translate`
```json
{"language":"hi"}
```
Returns `{language, native, content, method, note}`; cached translations are
served from the `translations` table.

### `GET /api/reports/{id}/export/{fmt}`
`fmt` = `pdf`, `pptx`, `excel`. Generates on demand if missing, returns the file
with `Content-Disposition: inline`. Media types: `application/pdf`,
`...presentationml.presentation`, `...spreadsheetml.sheet`.

---

## Chat (Agent 4)

### `GET /api/reports/{id}/chat`
Returns the persisted `[{role, message, created_at}]` history.

### `POST /api/reports/{id}/chat`
```json
{"question":"What about the rural market?"}
```
```json
{"answer":"**Rural / tier-2 opportunity.** ...",
 "provider":"Meridian Local Engine","model":"grounded-context-v1",
 "suggestions":["..."]}
```
The answer is grounded in the report's dataset, analysis, forecast and sources.
When a Chat-slot key exists, an LLM upgrade is attempted; a local answer always
remains as fallback.

---

## Compare mode

### `POST /api/compare`
```json
{"company_a":"Tesla","company_b":"BYD","region":"Global"}
```
Returns `{company_a, company_b, region, metrics[], dataset_a, dataset_b, verdict}`.

### `GET /api/comparisons?limit=30`
Saved comparisons.

---

## Settings / API keys

### `GET /api/settings`
Returns `providers` (16), `slots` (7 masked key statuses), `languages`,
`regions`, `periods`, `encryption`, `demo_mode`, `configured_count`.
**Never returns plaintext or ciphertext.**

### `POST /api/settings/keys`
```json
{"slot":"researcher","provider":"groq",
 "api_key":"gsk_...","model":"llama-3.3-70b-versatile"}
```
Validates, encrypts with Fernet and upserts the slot. `400` on an unknown
slot/provider or empty key.

### `POST /api/settings/keys/test`
```json
{"slot":"researcher"}
```
Performs a real minimal completion. Returns
`{ok, slot, provider, model, latency_ms, quota, inherited}` on success or
`{ok:false, slot, error}` — the error is always key-safe.

### `DELETE /api/settings/keys/{slot}`
Removes the key. If no active provider remains, generated answers are disabled.

### `POST /api/settings/keys/apply-all`
```json
{"provider":"gemini","api_key":"AIza..."}
```
Writes the same encrypted key to all seven slots.

---

## Rate limits & timeouts

There is no built-in rate limiter (deploy behind a gateway for multi-user use).
Every outbound request is time-boxed: connectors 3s, collection 6s, provider
calls `MERIDIAN_AGENT_TIMEOUT` (default 45s), connection tests 12s.
