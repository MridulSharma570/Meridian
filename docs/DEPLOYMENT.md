# Meridian — Deployment Guide

**Version 1.0.0 · Developed by Mridul Sharma**

---

## 0. Requirements

| Component | Minimum | Notes |
|-----------|---------|-------|
| Python | 3.11+ | 3.12 supported |
| RAM | 1 GB | 2 GB recommended |
| Disk | 500 MB | plus generated reports/exports |
| Database | none (SQLite) | PostgreSQL 15+ optional |
| Network | optional | only needed for live connectors / LLM providers |

---

## 1. Local (fastest — zero configuration)

```bash
git clone https://github.com/MridulSharma570/Meridian.git
cd Meridian
python -m venv .venv
source .venv/bin/activate                 # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                      # optional
python run.py                             # http://localhost:8000
```

The first boot automatically:
1. creates the SQLite schema at `data/meridian.db`,
2. generates a `0600` Fernet key at `data/.fernet_key`,
3. seeds one complete demo report so the dashboard is never empty.

Open **http://localhost:8000**. Interactive API docs are at `/docs`.

### Alternative frontends

```bash
python run.py --port 9000                 # custom port
python run.py --reload                    # development auto-reload
python run.py --streamlit                 # Streamlit UI on :8501
streamlit run app/main.py                 # same, directly
```

### Useful scripts

```bash
python -m scripts.setup_db                # create/verify schema + demo user
python -m scripts.migrate                 # idempotent column migration
python -m scripts.seed_data               # four curated demo reports
pytest -q                                 # 46-test verification suite
python -m compileall app                  # syntax smoke test
```

---

## 2. Docker (single container)

```bash
docker build -t meridian:1.0.0 .
docker run -d --name meridian -p 8000:8000 \
  -v meridian_data:/app/data \
  -e MERIDIAN_FERNET_KEY="$(python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())')" \
  meridian:1.0.0
curl http://localhost:8000/api/health
```

The image runs as a non-root `meridian` user, has a built-in healthcheck and
keeps all state under `/app/data`. Mount that volume to preserve reports and the
Fernet key across restarts.

---

## 3. Docker Compose (full stack: app + PostgreSQL + Redis)

```bash
# Generate a stable encryption key once and store it in .env
echo "MERIDIAN_FERNET_KEY=$(python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())')" >> .env
echo "TAVILY_API_KEY=..." >> .env
echo "NEWS_API_KEY=..." >> .env

docker compose up -d --build
docker compose ps
docker compose logs -f app
```

Compose starts Postgres 16, Redis 7 and two uvicorn workers. `DATABASE_URL`
uses `postgresql+psycopg2`; `psycopg2-binary==2.9.10` is already an active
dependency in `requirements.txt`.

To initialise/verify the schema explicitly:

```bash
docker compose exec app python -m scripts.migrate
docker compose exec app python -m scripts.seed_data
```

---

## 4. Cloud deployment

### 4.1 Render (Blueprint — see [RENDER_DEPLOYMENT.md](RENDER_DEPLOYMENT.md))

> **Render Free web services spin down after 15 minutes idle and take ~1 minute
> to wake. No code can prevent that.** Upgrade to **Starter** for guaranteed
> always-on, or use an external `/api/ping` monitor every 5–10 minutes as a
> best-effort workaround. Full diagnosis and dashboard steps are in
> [RENDER_DEPLOYMENT.md](RENDER_DEPLOYMENT.md).

1. Render → **New → Blueprint** → connect this repo → `main`. `render.yaml`
   creates the Docker web service with `healthCheckPath: /api/health`.
2. The image binds **`0.0.0.0:$PORT`** (Render injects `PORT=10000`).
   `docker-entrypoint.sh` resolves it at runtime; never hardcode 8000.
3. `WEB_CONCURRENCY=1` — report jobs and SSE streams are in-process.
4. Environment: `MERIDIAN_FERNET_KEY` (generated secret; any opaque string is
   accepted), optional `DATABASE_URL`, `REDIS_URL`, `TAVILY_API_KEY`,
   `NEWS_API_KEY`. Leave `MERIDIAN_LIVE_DATA=false` on Free.
5. **Persistence:** the filesystem is ephemeral — reports, exports and keys are
   wiped on every restart/deploy/spin-down. Attach **Render Postgres** (set
   `DATABASE_URL` to its internal connection string) or a **paid persistent
   disk** mounted at `/app/data`. Exports are regenerated on first download.
6. To stay on Free, add a **UptimeRobot** HTTP(s) monitor on `/api/ping` at a
   5-minute interval. Optionally install the GitHub Actions template
   (`deploy/keep-alive-workflow.yml` → `.github/workflows/keep-alive.yml`) with
   the `RENDER_APP_URL` variable as a second, independent pinger.
7. Lighter health endpoint: `/api/ping` (no database work, `Cache-Control:
   no-store`). `/api/health` also reports `platform`, `port` and warm-up state.

For Railway / Fly / other PaaS hosts the same rules apply: `python run.py`
reads `PORT`, binds `0.0.0.0`, and runs slow warm-up in a background thread.

### 4.2 VPS with systemd + Nginx

```ini
# /etc/systemd/system/meridian.service
[Unit]
Description=Meridian Market Intelligence
After=network.target

[Service]
User=meridian
WorkingDirectory=/opt/meridian
EnvironmentFile=/opt/meridian/.env
ExecStart=/opt/meridian/.venv/bin/uvicorn app.api.server:app --host 127.0.0.1 --port 8000 --workers 2
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```nginx
server {
    listen 443 ssl http2;
    server_name meridian.example.com;
    # ssl_certificate / ...;

    client_max_body_size 2M;
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_buffering off;          # REQUIRED for SSE agent events
        proxy_read_timeout 120s;
    }
}
```

> **Important:** `proxy_buffering off` is required for the live Agent Activity
> stream. Without it the progress panel appears frozen.

### 4.3 Kubernetes (sketch)

- Deployment: image `meridian:1.0.0`, 2 replicas, `resources.requests` 256Mi/250m.
- Secret: `MERIDIAN_FERNET_KEY`; ConfigMap for non-secret env.
- PersistentVolumeClaim mounted at `/app/data`.
- Service port 80 → 8000; Ingress with `proxy-read-timeout: "120"` and
  `proxy-buffering: "off"`.
- Liveness/readiness: `GET /api/health`.

---

## 5. PostgreSQL setup

```sql
CREATE USER meridian WITH PASSWORD 'change-me';
CREATE DATABASE meridian OWNER meridian;
```

```bash
export DATABASE_URL='postgresql+psycopg2://meridian:change-me@localhost:5432/meridian'
pip install psycopg2-binary==2.9.10
python -m scripts.migrate
```

JSON columns automatically use `JSONB` on PostgreSQL and plain `JSON` on
SQLite through SQLAlchemy's `with_variant`.

---

## 6. Environment variables

See [`.env.example`](../.env.example) for the complete annotated list. The
critical production ones are:

| Variable | Why |
|----------|-----|
| `MERIDIAN_FERNET_KEY` | Stable secret; losing it makes stored keys undecryptable |
| `DATABASE_URL` | Switch from SQLite to PostgreSQL |
| `MERIDIAN_DATA_DIR` | Must be on a persistent volume |
| `MERIDIAN_LIVE_DATA` | Set `false` in an offline/air-gapped environment |
| `TAVILY_API_KEY`, `NEWS_API_KEY` | Live search and news |
| `MERIDIAN_AGENT_TIMEOUT` | Provider call budget |

---

## 7. Production checklist

- [ ] HTTPS terminated at the proxy; app never exposed directly.
- [ ] Authentication/SSO in front — Meridian has **no built-in auth layer**.
- [ ] `MERIDIAN_FERNET_KEY` from a secret manager, backed up.
- [ ] Persistent volume for `data/`.
- [ ] `proxy_buffering off` for SSE.
- [ ] Database credentials least-privilege; Postgres/Redis ports private.
- [ ] `pytest -q` green and `python -m compileall app` clean before deploy.
- [ ] Verify `/api/health`, one report generation and all three exports.

---

## 8. Backups

```bash
# SQLite
cp data/meridian.db backups/meridian-$(date +%F).db
cp data/.fernet_key backups/.fernet_key        # store securely, mode 0600

# PostgreSQL
pg_dump -U meridian meridian | gzip > meridian-$(date +%F).sql.gz
```

Always back up the Fernet key alongside the database — without it, encrypted
API keys cannot be recovered.
