"""Isolated test environment: a temporary database and disabled live connectors."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="meridian-test-"))
os.environ["MERIDIAN_DATA_DIR"] = str(_TMP)
os.environ["MERIDIAN_EXPORT_DIR"] = str(_TMP / "exports")
os.environ["DATABASE_URL"] = f"sqlite:///{(_TMP / 'test.db').as_posix()}"
os.environ["MERIDIAN_FERNET_KEY_FILE"] = str(_TMP / ".fernet_key")
os.environ["MERIDIAN_LIVE_DATA"] = "false"
os.environ["MERIDIAN_USE_YFINANCE"] = "false"
os.environ["MERIDIAN_DEMO_MODE"] = "true"
# Existing pipeline/export tests exercise the explicitly labelled offline
# sample engine. Production defaults remain off; answer-policy tests opt out
# per-test with monkeypatch.delenv("MERIDIAN_SAMPLE_MODE").
os.environ["MERIDIAN_SAMPLE_MODE"] = "true"

import pytest  # noqa: E402


@pytest.fixture(scope="session")
def workspace() -> Path:
    return _TMP
