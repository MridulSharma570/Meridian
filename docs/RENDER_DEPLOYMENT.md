# Meridian on Render — Stop the Site Shutting Down

**Version 1.0.0 · Developed by Mridul Sharma**

> **Short version:** your app is not crashing. Render's **Free** plan suspends
> every web service after **15 minutes with no inbound traffic**. The first
> visitor then waits ~1 minute for a cold start. That is a platform rule, not a
> bug in Meridian, and **no code change can disable it**.
>
> - **Guaranteed fix (recommended):** upgrade the service to **Starter**
>   (~$7/month). Always on, no cold starts, no 15-minute sleep.
> - **Free workaround (best effort):** an **external** pinger that calls
>   `/api/ping` every 5–10 minutes — a UptimeRobot monitor, or the included
>   GitHub Actions workflow template. Best effort, not a guarantee.
>
> This repository also fixes two genuine deployment bugs that make a Render
> service look dead even when it is healthy: the old image ignored Render's
> injected `PORT` (it hardcoded 8000), and startup did slow database/seeding
> work before the socket was listening.

---

## 1. Why it shuts down — all the causes

| Symptom | Real cause | Fix |
|---------|-----------|-----|
| First request after ~15 min idle shows a loading screen / 502, then works | Render Free **idle spin-down**; cold start ~60 s | Starter plan, or external pings |
| Site dead for the rest of the month | **750 free instance-hours/month** exhausted (24/7 = ~720 h; two always-awake services exceed it), or **5 GB bandwidth** exceeded | Starter plan; delete unused free services |
| Site dead every day at the same time, or randomly after a deploy | Free services may be **restarted at any time**; local disk is ephemeral | Starter plan + persistent disk / Postgres |
| Deploy fails with "port scan timeout" / immediate 502 | App bound `0.0.0.0:8000` but Render routes to **`$PORT` (10000)** | Fixed in `docker-entrypoint.sh` |
| Deploy fails health check during startup | Schema creation + demo report ran in the ASGI lifespan before the port opened | Fixed: warm-up now runs in a background thread |
| Reports, exports and API keys vanish after a restart | SQLite lives at `/app/data` on an **ephemeral filesystem** | Render Postgres (`DATABASE_URL`) or a paid persistent disk |
| Service suspended with a traffic warning | Unusually high **outbound** (service-initiated) requests; an in-app self-ping loop can trigger this | Use a low-frequency *external* pinger; keep live connectors off on Free |

> ⚠️ Render explicitly says Free instances are **not for production**. A health
> check configured in the Render dashboard is *not* a keep-alive: only real
> inbound HTTP/WebSocket traffic resets the idle timer, and Render's own probes
> do not reliably do that.

---

## 2. GUARANTEED fix — upgrade to Starter (5 minutes, no code)

This is the only supported way to guarantee the site never shuts down.

1. Open **Render Dashboard → your `meridian` service**.
2. Go to **Settings → Instance Type** (or **Plan**).
3. Change **Free → Starter** (0.5 vCPU / 512 MB, ~$7/month) and **Save changes**.
   Render redeploys; no idle spin-down, no cold start, no 750-hour ceiling.
4. Still recommended: **Settings → Health Check Path = `/api/health`**.
   `/api/ping` is an even lighter alternative (no DB access).
5. Verify:
   ```bash
   curl -s https://YOUR-APP.onrender.com/api/health | python -m json.tool
   ```
   Expect `"status": "healthy"`, `"platform": "render"`, `"port": 10000`.

If you prefer Infrastructure-as-Code, edit the Blueprint in this repo:

```yaml
# render.yaml
services:
  - type: web
    name: meridian
    plan: starter      # ← was "free"
```

Then in Render: **New → Blueprint → connect the repo → `main`**. Committing the
change triggers a redeploy when `autoDeploy: true`.

**Paid plan ≠ durable data.** Starter still has an ephemeral filesystem. Do one
of the following:

- **Option A — Render Postgres (recommended).** Uncomment the `databases:`
  block and the `DATABASE_URL` env var in `render.yaml`, or create a Postgres
  database in the dashboard and set `DATABASE_URL` to its **Internal Connection
  String** in **Service → Environment**. `psycopg2-binary==2.9.10` is now an
  active dependency. Reports/keys survive restarts; PDF/PPTX/XLSX files are
  regenerated automatically on first download.
  > Free Postgres expires after 30 days — use a paid Postgres for production.
- **Option B — persistent disk** (paid plans only). Uncomment the `disk:` block
  in `render.yaml`, mounting `/app/data` (1 GB). Also set a **stable**
  `MERIDIAN_FERNET_KEY` in the dashboard; otherwise the key file is regenerated
  and previously saved API keys cannot be decrypted.

---

## 3. FREE workaround — external keep-alive (best effort)

If you stay on Free, an inbound request at least every 15 minutes is required.
Use a **5-minute** interval to leave margin for scheduler drift. Both options
below are **external** — a request from inside the app cannot wake a service
that Render has already spun down.

### 3.1 UptimeRobot (start here — no repo changes needed)

1. Create a free account at **uptimerobot.com → Add New Monitor**.
2. Monitor type: **HTTP(s)**.
3. URL: `https://YOUR-APP.onrender.com/api/ping`
4. Monitoring interval: **5 minutes**.
5. Save. Optionally add an alert contact so you know when Render does sleep.

> Free UptimeRobot monitors send **HEAD** requests by default. Meridian's
> `/api/ping` and `/api/health` both accept `GET` **and** `HEAD` (FastAPI's
> default `@app.get` would return 405 and show a false "down" alert). If you
> point the monitor at a different endpoint, set its method to GET in
> Advanced Settings.

`cron-job.org` works the same way (5–10 min, set a ≥60 s timeout so a
cold-starting service isn't marked failed). **Do not** use a Render Cron Job for
this — cron jobs are not available on the Free plan.

### 3.2 GitHub Actions workflow template (optional second pinger)

`deploy/keep-alive-workflow.yml` is a ready-to-use workflow that runs every 10
minutes and calls `scripts/keepalive.py`, which retries for ~100 seconds to
cover a cold start. It is shipped as a **template** (not installed under
`.github/workflows/`) so that the repository can be updated without needing
special workflow-file permissions.

**Setup — once:**

1. Copy `deploy/keep-alive-workflow.yml` to
   `.github/workflows/keep-alive.yml` on your **default branch** (`main`).
   You can do this in the GitHub web editor — **Add file → Create new file** —
   and paste the template's contents, then commit.
2. GitHub repo → **Settings → Secrets and variables → Actions → Variables**.
3. **New repository variable**: `RENDER_APP_URL` = `https://YOUR-APP.onrender.com`
   (no trailing slash needed; a Secret with the same name also works).
4. **Actions → Keep Meridian Awake → Run workflow** to test it immediately.
   Check the run log for `✓ Service is awake and healthy`.

**Limits you must know:**
- Scheduled workflows can be delayed or skipped under GitHub load, and GitHub
  **disables them after 60 days of repository inactivity**.
- They only run from the **default branch** (`main`).
- This is why the 10-minute schedule is paired with the 5-minute UptimeRobot
  monitor above.

### 3.3 Why the app cannot ping itself into staying awake

`app/keepalive.py` is an optional, **disabled-by-default** watchdog that sends
one request every 10 minutes *while the process is alive*. Once Render spins a
Free service down, that thread is gone too — nothing can wake it from inside.
Enable it only as defence-in-depth alongside an external pinger, and keep its
frequency low (Render may suspend free services with unusually high outbound
traffic):

```
MERIDIAN_SELF_PING_URL=https://YOUR-APP.onrender.com
MERIDIAN_SELF_PING_INTERVAL=600
```

`/api/health` reports the watchdog's hit/miss counters under `keepalive`.

### 3.4 The 750-hour trap

One service awake 24/7 consumes ~720 of the 750 free hours/month. At that rate
you have almost no headroom, and **two** always-awake services exceed the cap —
Render will suspend free services until the next billing cycle. If you need
real always-on availability, Starter is cheaper and more reliable than juggling
pings.

---

## 4. What was fixed in the code

| File | Change | Why |
|------|--------|-----|
| `docker-entrypoint.sh` (new) | `exec uvicorn … --host 0.0.0.0 --port "$PORT"` | Render injects `PORT=10000`; hardcoded 8000 caused port-scan/502 failures |
| `Dockerfile` | `EXPOSE 10000`, `ENV PORT=8000` default, stdlib `HEALTHCHECK` → `/api/ping`, `WEB_CONCURRENCY=1`, new entrypoint | Binds the right port; health probe uses the same port |
| `app/config.py` | `server_port()` reads `PORT` → `MERIDIAN_PORT` → `8000`; `web_concurrency()` | Same image works locally and on Render |
| `run.py` | `--port` / `--workers`, exports `PORT`, proxy headers, single-worker guard | Correct direct launch on any PaaS |
| `app/api/server.py` | `/api/ping` (no DB, `no-store`, GET + HEAD); lifespan starts warm-up in a **background thread** | Port is listening immediately; deploy health checks pass; HEAD works with free UptimeRobot monitors |
| `app/services.py` | `startup_state()`, non-blocking `bootstrap()` | No slow seeding before bind |
| `app/api/key_manager.py` | `_coerce_fernet_key()` derives a valid Fernet key from any secret | Render `generateValue: true` emits an opaque string, not a Fernet key |
| `render.yaml` (new) | Blueprint, `plan: free` → change to `starter`, `healthCheckPath`, `PORT=10000`, `WEB_CONCURRENCY=1`, generated secret, commented Postgres/disk | One-click reproducible deployment |
| `deploy/keep-alive-workflow.yml` (new) | Every 10 min, `RENDER_APP_URL` variable, `workflow_dispatch` | Free-tier external keep-alive |
| `scripts/keepalive.py` (new) | Stdlib-only pinger with cold-start retries | External ping that survives a 60 s wake-up |
| `requirements.txt` | `psycopg2-binary==2.9.10` activated | Durable Postgres on Render |
| `app/keepalive.py` (new) | Opt-in low-frequency watchdog | Closes small gaps between external pings |

**`WEB_CONCURRENCY` must stay 1.** Report jobs and the SSE agent-activity
stream live in process memory; running multiple workers makes status appear to
vanish. The old Dockerfile used `--workers 2`.

---

## 5. Deploy from scratch (Blueprint)

1. Push this branch to `main` (or merge your PR).
2. Render → **New → Blueprint** → connect `MridulSharma570/Meridian` → select
   `main`. Render reads `render.yaml` and creates the web service.
3. In **Environment**, confirm `PORT=10000`, `WEB_CONCURRENCY=1`, and that
   `MERIDIAN_FERNET_KEY` was generated. Fill `MERIDIAN_SELF_PING_URL` after you
   know the public URL (optional).
4. **Settings → Health Check Path = `/api/health`** (or `/api/ping`).
5. Wait for **Live**. Open `https://YOUR-APP.onrender.com`.
6. On Free: add a UptimeRobot 5-minute monitor on `/api/ping`. Optionally
   install the GitHub Actions template and set `RENDER_APP_URL`.
7. For production: change `plan` to `starter`, add Postgres or a disk, and set
   a stable `MERIDIAN_FERNET_KEY` that you keep backed up.

Manual (non-Blueprint) equivalent, if you already have a service:

| Setting | Value |
|---------|-------|
| Runtime | **Docker** (`./Dockerfile`, context `.`) |
| Build command | handled by the Dockerfile |
| Start command | `/bin/sh -c "exec /app/docker-entrypoint.sh"` |
| Health check path | `/api/health` |
| `PORT` | `10000` |
| `WEB_CONCURRENCY` | `1` |
| `MERIDIAN_FERNET_KEY` | generated secret / stable value |
| `MERIDIAN_DATA_DIR` | `/app/data` |

---

## 6. Verify and diagnose

```bash
# Lightweight liveness (no DB, never cached)
curl -i https://YOUR-APP.onrender.com/api/ping

# Full status
curl -s https://YOUR-APP.onrender.com/api/health | python -m json.tool
```

Healthy response includes `"platform": "render"`, `"port": 10000`,
`"warming_up": false`, and a `keepalive` block with ping counters. The
`database` field should read `postgresql` once you attach Postgres.

Checklist when it still sleeps / returns 502:

- [ ] Plan is **Free** → expected; add pings or upgrade to Starter.
- [ ] Free **750 hours** or **5 GB bandwidth** used → suspended until next month.
- [ ] `PORT` is not `10000`, or the start command still hardcodes `--port 8000`.
- [ ] `WEB_CONCURRENCY > 1` → set to `1`.
- [ ] Health check path is `/` instead of `/api/health` and HTML/CDN assets are slow → use `/api/ping`.
- [ ] Deploy logs show `port scan timeout` → the socket did not bind to `0.0.0.0:$PORT`.
- [ ] GitHub Action never ran → confirm the template was copied to `.github/workflows/keep-alive.yml` on `main`, then check the **Actions** tab, `RENDER_APP_URL`, and the 60-day inactivity rule.
- [ ] Outbound-traffic suspension warning → disable `MERIDIAN_SELF_PING_URL`, turn off `MERIDIAN_LIVE_DATA`, lower ping frequency.

See [TROUBLESHOOTING.md](TROUBLESHOOTING.md) for application-level issues.

---

*Developed by Mridul Sharma · Meridian v1.0.0*
