# Meridian — Troubleshooting

**Version 1.0.0 · Developed by Mridul Sharma**

Work through **1. Fast diagnostics** first — it resolves most issues.

---

## 1. Fast diagnostics

```bash
python --version                      # must be 3.11+
.venv/bin/pip check                   # dependency conflicts
python -m compileall app              # syntax errors
pytest -q                             # 123 tests should pass
curl -s http://localhost:8000/api/health | python -m json.tool
```

If the health check fails, the server is not running. Start it with
`python run.py` and read the console output.

---

## 2. Installation & startup

### `ModuleNotFoundError: No module named 'fastapi'` (or any dependency)
The virtual environment is not active or dependencies aren't installed.
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### `RequestsDependencyWarning: urllib3 or chardet doesn't match`
`requirements.txt` pins `urllib3==2.8.0` and `chardet==5.2.0` which are
compatible with `requests==2.32.3`. Reinstall:
```bash
pip install --force-reinstall 'chardet==5.2.0' 'urllib3==2.8.0'
```

### `Address already in use` on port 8000
```bash
python run.py --port 8001
# or: lsof -ti:8000 | xargs kill -9
```

### `no such table: api_keys` / `reports`
Meridian now creates the schema lazily on first DB access, but an old database
may still be missing newer columns:
```bash
python -m scripts.migrate
```

### `Unable to initialise encryption key file`
`data/` is not writable. Fix permissions or point to a writable path:
```bash
export MERIDIAN_DATA_DIR=/tmp/meridian-data
```

### Page shows a white/blank screen
1. Hard-refresh (Ctrl/Cmd+Shift+R).
2. Open the browser console: any `404` on `/static/app.js` means the server is
   running from the wrong working directory — start it from the repo root.
3. Confirm `curl http://localhost:8000/static/app.css` returns 200.

---

## 3. Report generation

### A report stays on `processing` forever
Check `GET /api/reports/{id}/status` and the server console. Causes:
- an agent's provider is hanging (default budget 45 s),
- a live connector is slow (collection budget is 6 s).

Check whether the job actually failed with a provider/evidence error. In
production mode Meridian fails closed; it does not complete from a local
template. Lower `MERIDIAN_AGENT_TIMEOUT=15` only to fail faster.

### `Report failed: ...`
Read `report.error_message` and the `job_failed` SSE event. The pipeline is
designed to isolate agent failures, so this usually means a database write
failed (disk full or locked). Free space and re-run `python -m scripts.migrate`.

### Charts are empty or show "Chart unavailable"
The report's `researcher_output.dataset` is missing. Regenerate the report, or
open a different one. Filtering with an unsupported region/period falls back
safely to Global/3Y.

### "API key required" / no answer is generated
This is the intended production behaviour. Save at least one active provider
key in Settings → API Keys. Meridian no longer creates market sizes, SWOTs,
forecasts, citations or chat answers from a deterministic template. If a key
exists but reports still fail, check live evidence: enable `MERIDIAN_LIVE_DATA`
or configure `TAVILY_API_KEY` / `NEWS_API_KEY`. Sample output is available only
with explicit `MERIDIAN_SAMPLE_MODE=true` and is labelled SAMPLE.

### Agent Activity panel never updates
SSE is being buffered. In Nginx add `proxy_buffering off;` and
`proxy_read_timeout 120s;` (see [DEPLOYMENT.md](DEPLOYMENT.md)). If your proxy
blocks SSE entirely, the panel still resyncs via `/status` polling every 4 s.

---

## 4. API keys (Settings)

| Error | Meaning / fix |
|-------|---------------|
| `Enter an API key first` | The field was empty. Paste a key; unconfigured slots can borrow another active provider, but with none active answers stay disabled. |
| `Unknown agent slot` | Only `researcher, analyst, writer, chat, forecast, factchecker, translator` are valid. |
| `Unknown provider` | Choose from the dropdown; provider ids are internal (e.g. `openrouter_free`). |
| `No key saved in this slot` | Press **Save key** before **Test connection**. |
| `HTTP 401 / 403` | Invalid or expired key; regenerate it at the provider. |
| `HTTP 429` | Rate limit / exhausted quota. On an OpenRouter auto slot the next free model is tried automatically, and after a 429 Meridian waits out the rate-limit window (honouring `Retry-After`) before further calls instead of instantly tripping it again. If the assigned provider stays limited, the final agent attempt may use another configured **free** provider (never a paid one). A persistent 429 usually means the daily free cap is reached — wait or add a free Groq/Gemini key. |
| `HTTP 402` on OpenRouter (Free) | OpenRouter's billing gate blocked the key/account. Meridian only sends explicit `:free` models; check the key is on the intended account/organisation, remove or raise its per-key credit limit, and check for a negative balance. A genuine `:free` model normally does not require buying credits — if the account still blocks free calls, use Groq or Gemini. The slot should read **SAVED · TEST FAILED**, not “tested”, until a new test succeeds. |
| `HTTP 404 … this free model was retired` | OpenRouter removed a `:free` slug. Auto mode refreshes the catalogue and cools that model down for five minutes. Press **Refresh** in the Settings auto-selection panel to force a re-fetch; pin a specific model only if you need reproducibility. |
| `No free models found` / `OFFLINE FALLBACK` | The public catalogue could not be reached (or it returned no free chat models). Meridian falls back to OpenRouter's own `openrouter/free` router — still zero cost and still current. Check `MERIDIAN_OPENROUTER_CATALOG_TIMEOUT` and outbound DNS. |
| `returned unusable output` on an auto slot | A free model returned empty, reasoning-only, truncated or malformed output. Meridian retries that model with reasoning disabled, can fail over to another `:free` model, repairs truncated JSON and retries the agent with a shorter strict-JSON prompt. If every attempt fails, the step fails instead of using a template and Mission Control marks the agent **FAILED**. |
| `Could not reach <provider>` | Sandbox/VPN/firewall blocks the host. No answer was generated; fix connectivity or switch provider. |
| `timed out after 45s` | Lower `MERIDIAN_AGENT_TIMEOUT` or use Groq/Cerebras for speed. |
| `returned unusable output` | The model ignored JSON mode or returned no requested fields after Meridian's repair retries. Meridian refused to publish a substitute answer. |
| `Stored credential could not be decrypted` | The Fernet key changed (e.g. `data/` was reset). Re-enter the key in Settings. |
| Keys disappear after restart | `MERIDIAN_DATA_DIR` points at a temporary path; mount a persistent volume. |

**Verifying encryption manually**
```bash
python -c "
import sqlite3; c=sqlite3.connect('data/meridian.db')
print(c.execute('select api_key_encrypted from api_keys limit 1').fetchone())
"
```
The value must start with `gAAAAA` and must not contain your plaintext key.

---

## 5. Exports

| Symptom | Fix |
|---------|-----|
| `404` on `/export/pdf` | Report id is wrong or was deleted. |
| `500 PDF export could not be generated` | `data/exports` is not writable or ReportLab is missing: `pip install reportlab==4.2.5`. A minimal valid PDF fallback is written automatically on layout errors. |
| PDF hangs | Fixed in v1.0.0 — `pie.slices` is indexed by a fixed range rather than iterated (iterating a ReportLab `TypedPropertyCollection` never terminates). |
| PowerPoint won't open | Reinstall `python-pptx==1.0.2` and `lxml==6.1.3`; regenerate with `services.generate_exports(report_id)`. |
| Excel has no charts | Ensure `openpyxl==3.1.5`; charts are native and appear in Excel/LibreOffice, not in every lightweight previewer. |
| Exports show old numbers | Exports use the report's original scope. Apply filters and regenerate the report if you need a filtered deliverable. |

Regenerate all three manually:
```bash
python -c "from app import services; print(services.generate_exports('<report-id>'))"
```

---

## 6. Database

### `database is locked` (SQLite)
WAL mode is enabled with a 30 s busy timeout. Avoid running `scripts/seed_data.py`
and the server against the same file simultaneously, or switch to PostgreSQL.

### `psycopg2` missing with `DATABASE_URL=postgresql+psycopg2://…`
`psycopg2-binary==2.9.10` is now an active requirement. If an older image
still lacks it:
```bash
pip install psycopg2-binary==2.9.10
```

### Redis warnings in the logs
Harmless — a broken/missing Redis never affects a request. Remove `REDIS_URL`
to silence them.

### Reset everything
```bash
rm -rf data/meridian.db* data/.fernet_key data/exports/*
python run.py     # recreates schema and encryption key; configure a provider key next
```
⚠️ This deletes all saved reports and forces you to re-enter API keys.

---

## 7. Streamlit frontend

| Symptom | Fix |
|---------|-----|
| Theme looks like default Streamlit | `inject_theme()` must be the first call in `app/main.py`; clear the browser cache. |
| `missing ScriptRunContext` warnings | Normal when importing modules outside a Streamlit run (e.g. tests), harmless. |
| Port 8501 conflict | `streamlit run app/main.py --server.port 8502` |
| Fonts look plain | Fontshare/Google Fonts are CDN-loaded; offline they fall back to system sans-serif. Ship the `.woff2` files in `app/assets/fonts/` for fully offline typography. |

---

## 8. Live data connectors

| Symptom | Fix |
|---------|-----|
| All connectors `offline` | Network egress is blocked. Expected in sandboxes/air-gapped demos; set `MERIDIAN_LIVE_DATA=false` to skip attempts. |
| `Tavily HTTP 401` | Bad `TAVILY_API_KEY`. |
| `NewsAPI HTTP 426/401` | Free NewsAPI key only works from localhost/with HTTPS; check plan limits. |
| World Bank empty | Some indicators are unavailable for aggregates like `EU`; Meridian keeps model estimates. |
| Yahoo `possibly delisted` | Only well-known tickers are mapped; set `MERIDIAN_USE_YFINANCE=false` (default) to skip the heavy fallback. |

---

## 9. Render / PaaS — "the site keeps shutting down"

| Symptom | Cause and fix |
|---------|---------------|
| App loads only after ~60 s, then sleeps again | Render **Free** spins down after 15 min idle. This is a platform rule. Upgrade to **Starter** (guaranteed) or add an external `/api/ping` every 5–10 min (best effort). See [RENDER_DEPLOYMENT.md](RENDER_DEPLOYMENT.md). |
| Site dead until the next billing cycle | Free **750 instance-hours/month** or **5 GB bandwidth** exhausted. Upgrade, or delete unused free services. |
| Deploy fails with `port scan timeout` / immediate 502 | Start command bound port 8000 instead of **`0.0.0.0:$PORT`** (Render uses 10000). Use `docker-entrypoint.sh` or `python run.py`. |
| Health check fails only during startup | Fixed: schema/demo seeding now runs in a background thread, so the socket opens immediately. Confirm `MERIDIAN_BACKGROUND_BOOTSTRAP=true`. |
| Progress/agents disappear mid-run | `WEB_CONCURRENCY` > 1. Set it to **1**; jobs and SSE state are in-process. |
| Reports and API keys vanish after a restart | Ephemeral filesystem. Set `DATABASE_URL` to Render Postgres, or mount a paid persistent disk at `/app/data`; keep a stable `MERIDIAN_FERNET_KEY`. |
| `Stored credential could not be decrypted` after deploy | The Fernet key file was regenerated with an ephemeral disk. Set a stable `MERIDIAN_FERNET_KEY` in the Render Environment (any opaque secret works — Meridian derives a valid key from it). |
| Suspension warning about outbound traffic | Disable the optional in-app self-ping (`MERIDIAN_SELF_PING_URL`), set `MERIDIAN_LIVE_DATA=false`, and rely on a low-frequency external monitor. |
| GitHub Actions keep-alive stops firing | Confirm `deploy/keep-alive-workflow.yml` was copied to `.github/workflows/keep-alive.yml` on `main`. Scheduled workflows are delayed under load, are disabled after 60 days of repo inactivity, and only run on the default branch. Check the Actions tab; use UptimeRobot as the primary pinger. |

Quick verification:
```bash
curl -s https://YOUR-APP.onrender.com/api/health | python -m json.tool
# expect: platform=render, port=10000, warming_up=false, keepalive counters
```

---

## 10. Responsive layout & the menu button

| Symptom | Fix |
|---------|-----|
| Only the ≡ button is visible / content looks off-screen | Hard-refresh — an older cached `app.css` has a three-column grid squeezed into a phone. Confirm `/static/app.css` contains `@media(max-width:1100px)`. |
| ≡ button "does nothing" on a tablet | Below 1100px it opens the navigation **drawer** (off-canvas, from the left). Look for the dimmed backdrop; the button turns gold while open. On desktop it instead collapses the sidebar to a 72px rail. |
| Sidebar disappeared entirely on a phone | Expected — tap the labelled **Menu** button. The sidebar is a drawer below 1100px; there is no bottom bar. |
| Agent Activity panel is missing | Use the pulse button in the top bar: on desktop it toggles the panel, on tablets/phones it opens it as a right-hand drawer. |
| Drawer will not close | Tap the backdrop, press `Escape`, use the ✕ inside the drawer, or pick a page. Opening one drawer always closes the other. |
| Charts/heatmap cut off on a phone | Charts scale their gutters to the measured card width and reflow on resize / orientation change; the heatmap shrinks its label column and cell height to fit. Refresh if an older cached `app.css` is being served. |
| Inputs zoom the whole page on iOS | Fixed — every input, select and textarea uses 16px / 44px on phones. |
| Wide table forces sideways scrolling | On phones the table header is hidden and each row becomes a labelled stacked card; `decorateTables()` copies `<th>` text onto every cell. |
| A bottom bar is still visible | The bottom navigation bar was removed entirely. Hard-refresh to drop a cached `app.css` / `app.js`; `grep -ri tabbar app/web` must return nothing. |
| Footer hidden behind the iOS home indicator | The footer, chat dock, Ask button and toasts reserve `env(safe-area-inset-bottom)`; no extra bottom-bar padding remains. |

Both frontends (the SPA and Streamlit) share the same breakpoints. Verify with
`pytest -q tests/test_responsive_ui.py`.

---

## 11. Getting help

Open a GitHub issue with:
- the exact command you ran,
- the full error text (**never include a real API key**),
- `GET /api/health` output,
- your `data_mode` and connector statuses,
- OS + Python version and `pip check` output.

For anything security-related, follow [SECURITY.md](../SECURITY.md) instead.

---

*Developed by Mridul Sharma · Meridian v1.0.0*
