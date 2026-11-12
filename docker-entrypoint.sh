#!/bin/sh
# ============================================================================
# MERIDIAN — container entrypoint
# Render injects PORT (default 10000) and requires the app to bind
# 0.0.0.0:$PORT. Hardcoding 8000 causes port-scan / health-check failures.
# Locally, PORT is unset so the image still serves on 8000.
# Developed by Mridul Sharma
# ============================================================================
set -eu

PORT="${PORT:-${MERIDIAN_PORT:-8000}}"
WORKERS="${WEB_CONCURRENCY:-1}"
export PORT
export MERIDIAN_PORT="$PORT"
export WEB_CONCURRENCY="$WORKERS"

echo "◆  MERIDIAN — Market Intelligence, Redefined."
echo "   Binding 0.0.0.0:${PORT} (workers=${WORKERS})"

# WEB_CONCURRENCY must stay 1: report jobs and SSE events live in process memory.
# --proxy-headers makes Uvicorn trust Render's edge proxy (correct scheme/host).
exec uvicorn app.api.server:app \
  --host 0.0.0.0 \
  --port "$PORT" \
  --workers "$WORKERS" \
  --timeout-keep-alive 75 \
  --proxy-headers \
  --forwarded-allow-ips '*' \
  --no-access-log \
  --log-level info
