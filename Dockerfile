# ============================================================================
# MERIDIAN — AI Market Intelligence SaaS
# Multi-stage, non-root production image.
# Render-compatible: binds 0.0.0.0:$PORT (Render injects PORT=10000).
# Developed by Mridul Sharma
# ============================================================================

# ---------- Stage 1: build wheels ------------------------------------------ #
FROM python:3.11-slim AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /build
COPY requirements.txt ./
RUN python -m venv /opt/venv \
 && /opt/venv/bin/pip install --upgrade pip setuptools wheel \
 && /opt/venv/bin/pip install -r requirements.txt

# ---------- Stage 2: runtime image ----------------------------------------- #
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    MERIDIAN_HOST=0.0.0.0 \
    MERIDIAN_PORT=8000 \
    PORT=8000 \
    WEB_CONCURRENCY=1 \
    MERIDIAN_DATA_DIR=/app/data \
    MERIDIAN_EXPORT_DIR=/app/data/exports \
    MERIDIAN_BACKGROUND_BOOTSTRAP=true

# curl is intentionally omitted — health checks use the stdlib probe below.
RUN apt-get update \
 && apt-get install -y --no-install-recommends libexpat1 libffi8 \
 && rm -rf /var/lib/apt/lists/* \
 && groupadd --system meridian \
 && useradd --system --gid meridian --home-dir /app --shell /usr/sbin/nologin meridian

WORKDIR /app
COPY --from=builder /opt/venv /opt/venv
COPY --chown=meridian:meridian app/ ./app/
COPY --chown=meridian:meridian scripts/ ./scripts/
COPY --chown=meridian:meridian docs/ ./docs/
COPY --chown=meridian:meridian README.md run.py docker-entrypoint.sh ./
RUN chmod 0755 /app/docker-entrypoint.sh \
 && mkdir -p /app/data /app/data/exports \
 && chown -R meridian:meridian /app/data \
 && python -m compileall -q app scripts run.py

USER meridian

# Render routes to $PORT (10000 by default). EXPOSE is documentation only —
# the entrypoint reads $PORT at runtime, so the same image serves 8000 locally.
EXPOSE 10000
HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \
  CMD python -m scripts.healthcheck || exit 1

# Shell form lets the entrypoint resolve ${PORT} before exec'ing uvicorn.
CMD ["/bin/sh", "-c", "exec /app/docker-entrypoint.sh"]
