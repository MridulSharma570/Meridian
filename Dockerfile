# ============================================================================
# MERIDIAN — production container
# Developed by Mridul Sharma
# ============================================================================
FROM python:3.11-slim AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /build
COPY requirements.txt .
RUN python -m venv /opt/venv \
 && /opt/venv/bin/pip install --upgrade pip \
 && /opt/venv/bin/pip install -r requirements.txt

# ---------------------------------------------------------------------------
FROM python:3.11-slim AS runtime

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    MERIDIAN_HOST=0.0.0.0 \
    MERIDIAN_PORT=8000 \
    MERIDIAN_DATA_DIR=/app/data \
    MERIDIAN_EXPORT_DIR=/app/data/exports

RUN groupadd --system meridian && useradd --system --gid meridian meridian \
 && mkdir -p /app/data/exports \
 && chown -R meridian:meridian /app

COPY --from=builder /opt/venv /opt/venv
WORKDIR /app
COPY --chown=meridian:meridian . .

USER meridian
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=3).read()"

CMD ["uvicorn", "app.api.server:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
