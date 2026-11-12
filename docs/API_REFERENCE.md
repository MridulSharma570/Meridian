# Meridian — Internal API Reference

**Base URL:** `http://localhost:8000` · **Interactive docs:** `/docs` · **OpenAPI:** `/openapi.json`
**Version 1.0.0 · Developed by Mridul Sharma**

All requests and responses are JSON unless stated. Errors return
`{"detail": "..."}`, with `400` for bad input, `404` for missing resources and
`500` for unexpected failures. Every endpoint is CORS-enabled and uses relative
paths only.

---

## System

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/` | Premium SPA (`text/html`) |
| `GET` | `/static/{file}` | `app.css`, `app.js`, `favicon.svg` |
| `GET` | `/api/health` | Liveness, version, DB engine, developer |
| `GET` | `/api/bootstrap` | First-load payload: app info, stats, settings, agents, pipeline. Also seeds a demo report on a fresh install. |
| `GET` | `/api/stats` | Totals, average reliability, sources, agent runs, active keys |
| `GET` | `/api/agents` | Agent metadata, pipeline stages, chat suggestions |
| `GET` | `/api/providers` | All 16 providers, tier, models, hints, signup URLs |
| `GET` | `/api/languages` | 14 supported languages (`code`, `name`, `native`) |
| `GET` | `/api/agent-logs/{report_id}` | Raw agent execution telemetry |

**Example** `GET /api/health`
```json
{"status":"healthy","app":"Meridian","version":"1.0.0",
 "tagline":"Market Intelligence, Redefined.","developer":"Mridul Sharma",
 "database":"sqlite","demo_mode":true}
```

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
Removes the key; the local engine takes over.

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
