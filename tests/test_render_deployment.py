"""Regression tests for the Render deployment fix.

Covers PORT resolution, PORT-aware health probes, non-blocking warm-up,
Fernet key coercion, the keep-alive pinger and the external keep-alive script.
"""
from __future__ import annotations

import importlib
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import config, keepalive
from app.api import key_manager
from app.api.server import app
from scripts import keepalive as external_keepalive


@pytest.fixture(autouse=True)
def clean_port_env(monkeypatch):
    for name in ("PORT", "MERIDIAN_PORT", "WEB_CONCURRENCY",
                 "MERIDIAN_SELF_PING_URL", "RENDER_SERVICE_NAME"):
        monkeypatch.delenv(name, raising=False)


# --------------------------------------------------------------------------- #
# PORT handling (Render injects PORT=10000)
# --------------------------------------------------------------------------- #
def test_server_port_defaults_to_8000():
    assert config.server_port() == 8000


def test_server_port_reads_render_port(monkeypatch):
    monkeypatch.setenv("PORT", "10000")
    assert config.server_port() == 10000


def test_render_port_wins_over_local_override(monkeypatch):
    monkeypatch.setenv("MERIDIAN_PORT", "8000")
    monkeypatch.setenv("PORT", "10000")
    assert config.server_port() == 10000


def test_server_port_rejects_garbage(monkeypatch):
    monkeypatch.setenv("PORT", "not-a-port")
    assert config.server_port() == 8000
    monkeypatch.setenv("PORT", "99999")
    assert config.server_port() == 8000


def test_settings_port_is_resolved_at_call_time(monkeypatch):
    """A CLI --port override must be reflected in /api/health too."""
    monkeypatch.setenv("PORT", "8000")
    assert config.settings.port == 8000
    monkeypatch.setenv("PORT", "10000")
    assert config.settings.port == 10000


def test_malformed_numeric_env_never_crashes(monkeypatch):
    monkeypatch.setenv("MERIDIAN_AGENT_TIMEOUT", "abc")
    assert config._float_env("MERIDIAN_AGENT_TIMEOUT", 45.0) == 45.0
    monkeypatch.setenv("MERIDIAN_MAX_WORKERS", "abc")
    assert config._int_env("MERIDIAN_MAX_WORKERS", 6) == 6


def test_web_concurrency_defaults_to_one():
    assert config.web_concurrency() == 1


def test_web_concurrency_is_clamped(monkeypatch):
    monkeypatch.setenv("WEB_CONCURRENCY", "99")
    assert config.web_concurrency() == 4
    monkeypatch.setenv("WEB_CONCURRENCY", "broken")
    assert config.web_concurrency() == 1


def test_run_py_exports_port(monkeypatch):
    monkeypatch.setenv("PORT", "10000")
    import run
    args = run.parse_args([])
    assert args.host == "0.0.0.0"
    assert args.port is None
    assert args.workers is None
    assert config.server_port() == 10000


# --------------------------------------------------------------------------- #
# Health endpoints must be cheap and uncached
# --------------------------------------------------------------------------- #
def test_ping_is_lightweight_and_uncached():
    with TestClient(app) as client:
        resp = client.get("/api/ping")
    assert resp.status_code == 200
    assert resp.json()["ok"] is True
    assert resp.json()["service"] == "meridian"
    assert "no-store" in resp.headers["cache-control"]


def test_head_probes_are_accepted():
    """Free UptimeRobot monitors send HEAD; a 405 would report a false outage."""
    with TestClient(app) as client:
        assert client.head("/api/ping").status_code == 200
        assert client.head("/api/health").status_code == 200


def test_health_reports_platform_and_warmup():
    with TestClient(app) as client:
        resp = client.get("/api/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "healthy"
    assert body["platform"] in {"local", "render"}
    assert isinstance(body["port"], int)
    assert isinstance(body["warming_up"], bool)
    assert "enabled" in body["keepalive"]
    assert "no-store" in resp.headers["cache-control"]


def test_bootstrap_never_blocks_on_seeding():
    with TestClient(app) as client:
        resp = client.get("/api/bootstrap")
    assert resp.status_code == 200
    assert isinstance(resp.json()["warming_up"], bool)


# --------------------------------------------------------------------------- #
# Render's generateValue secret is not a Fernet key
# --------------------------------------------------------------------------- #
def test_opaque_secret_becomes_valid_fernet_key():
    from cryptography.fernet import Fernet
    key = key_manager._coerce_fernet_key("render-generated-opaque-secret-123")
    Fernet(key)  # must not raise
    assert len(key) == 44


def test_valid_fernet_key_used_verbatim():
    from cryptography.fernet import Fernet
    original = Fernet.generate_key()
    assert key_manager._coerce_fernet_key(original.decode()) == original


def test_empty_secret_rejected():
    with pytest.raises(ValueError):
        key_manager._coerce_fernet_key("  ")


# --------------------------------------------------------------------------- #
# Keep-alive helpers
# --------------------------------------------------------------------------- #
def test_keepalive_disabled_by_default():
    wd = keepalive.KeepAlive("", 600)
    assert wd.enabled is False
    assert wd.ping_once() is False
    assert wd.status()["successes"] == 0


def test_keepalive_target_and_status():
    wd = keepalive.KeepAlive("https://meridian.onrender.com/", 300)
    assert wd.target == "https://meridian.onrender.com/api/ping"
    assert wd.status()["interval_s"] == 300


def test_external_pinger_normalises_urls():
    assert external_keepalive.normalise_url("meridian.onrender.com") == \
        "https://meridian.onrender.com/api/ping"
    assert external_keepalive.normalise_url("https://x.onrender.com/") == \
        "https://x.onrender.com/api/ping"
    assert external_keepalive.normalise_url("https://x/api/health") == \
        "https://x/api/health"
    with pytest.raises(ValueError):
        external_keepalive.normalise_url("")


def test_external_pinger_handles_network_failure():
    ok, detail = external_keepalive.ping_once(
        "http://127.0.0.1:1/api/ping", timeout=1)
    assert ok is False
    assert detail


# --------------------------------------------------------------------------- #
# Repo-level Render assets
# --------------------------------------------------------------------------- #
def test_render_assets_exist():
    root = Path(__file__).resolve().parents[1]
    for rel in ("render.yaml", "Dockerfile", "docker-entrypoint.sh",
                "deploy/keep-alive-workflow.yml",
                "scripts/healthcheck.py", "scripts/keepalive.py",
                "docs/RENDER_DEPLOYMENT.md"):
        assert (root / rel).is_file(), f"missing {rel}"


def test_dockerfile_and_blueprint_use_render_port():
    root = Path(__file__).resolve().parents[1]
    dockerfile = (root / "Dockerfile").read_text()
    entrypoint = (root / "docker-entrypoint.sh").read_text()
    blueprint = (root / "render.yaml").read_text()
    assert "EXPOSE 10000" in dockerfile
    assert "docker-entrypoint.sh" in dockerfile
    assert "--port \"$PORT\"" in entrypoint
    assert "--host 0.0.0.0" in entrypoint
    assert "healthCheckPath: /api/health" in blueprint
    assert "value: \"10000\"" in blueprint
    assert "plan: free" in blueprint
    assert "plan: starter" in blueprint  # documented upgrade path
    assert "*/10 * * * *" in (root / "deploy/keep-alive-workflow.yml").read_text()


def test_requirements_include_postgres_driver():
    root = Path(__file__).resolve().parents[1]
    text = (root / "requirements.txt").read_text()
    assert "psycopg2-binary==2.9.10" in text
    assert "# psycopg2-binary" not in text
