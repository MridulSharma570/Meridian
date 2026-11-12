# Meridian — Troubleshooting

**Version 1.0.0 · Developed by Mridul Sharma**

Work through **1. Fast diagnostics** first — it resolves most issues.

---

## 1. Fast diagnostics

```bash
python --version                      # must be 3.11+
.venv/bin/pip check                   # dependency conflicts
python -m compileall app              # syntax errors
pytest -q                             # 23 tests should pass
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

Set `MERIDIAN_LIVE_DATA=false` and/or lower `MERIDIAN_AGENT_TIMEOUT=15`,
then restart. The local engine always completes in under a second.

### `Report failed: ...`
Read `report.error_message` and the `job_failed` SSE event. The pipeline is
designed to isolate agent failures, so this usually means a database write
failed (disk full or locked). Free space and re-run `python -m scripts.migrate`.

### Charts are empty or show "Chart unavailable"
The report's `researcher_output.dataset` is missing. Regenerate the report, or
open a different one. Filtering with an unsupported region/period falls back
safely to Global/3Y.

### Figures look "made up"
They are model-generated when no live feeds are available — that is by design
and is labelled `SIMULATED` in the badge, the report and the fact-check tab.
Add `TAVILY_API_KEY` / `NEWS_API_KEY` and LLM keys to move to `HYBRID`/`LIVE`.
Always verify ⚠️ flagged claims against primary sources before publishing.

### Agent Activity panel never updates
SSE is being buffered. In Nginx add `proxy_buffering off;` and
`proxy_read_timeout 120s;` (see [DEPLOYMENT.md](DEPLOYMENT.md)). If your proxy
blocks SSE entirely, the panel still resyncs via `/status` polling every 4 s.

---

## 4. API keys (Settings)

| Error | Meaning / fix |
|-------|---------------|
| `Enter an API key first` | The field was empty. Paste a key — or leave the slot unconfigured and use the local engine. |
| `Unknown agent slot` | Only `researcher, analyst, writer, chat, forecast, factchecker, translator` are valid. |
| `Unknown provider` | Choose from the dropdown; provider ids are internal (e.g. `openrouter_free`). |
| `No key saved in this slot` | Press **Save key** before **Test connection**. |
| `HTTP 401 / 403` | Invalid or expired key; regenerate it at the provider. |
| `HTTP 429` | Rate limit / exhausted quota; wait or switch to a free provider. |
| `Could not reach <provider>` | Sandbox/VPN/firewall blocks the host. Meridian already used the local engine — no report is lost. |
| `timed out after 45s` | Lower `MERIDIAN_AGENT_TIMEOUT` or use Groq/Cerebras for speed. |
| `returned unusable output` | The model ignored JSON mode. Meridian repaired what it could and kept the local analysis. |
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
```bash
pip install psycopg2-binary==2.9.10
```

### Redis warnings in the logs
Harmless — a broken/missing Redis never affects a request. Remove `REDIS_URL`
to silence them.

### Reset everything
```bash
rm -rf data/meridian.db* data/.fernet_key data/exports/*
python run.py     # recreates schema, key and a fresh demo report
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

## 9. Getting help

Open a GitHub issue with:
- the exact command you ran,
- the full error text (**never include a real API key**),
- `GET /api/health` output,
- your `data_mode` and connector statuses,
- OS + Python version and `pip check` output.

For anything security-related, follow [SECURITY.md](../SECURITY.md) instead.

---

*Developed by Mridul Sharma · Meridian v1.0.0*
