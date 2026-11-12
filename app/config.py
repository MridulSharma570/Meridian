"""Central configuration for Meridian.

All settings are read from the environment (or a local ``.env`` file).
Booting requires no external service, but **generating an answer does**: see
:mod:`app.api.answer_policy`. The deterministic engine is sample-only and is
disabled unless ``MERIDIAN_SAMPLE_MODE`` is explicitly enabled.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Tuple

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=False)
except Exception:  # pragma: no cover - dotenv is optional at runtime
    pass

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = Path(os.getenv("MERIDIAN_DATA_DIR", ROOT / "data"))
EXPORT_DIR = Path(os.getenv("MERIDIAN_EXPORT_DIR", DATA_DIR / "exports"))
WEB_DIR = Path(__file__).resolve().parent / "web"
for _p in (DATA_DIR, EXPORT_DIR):
    try:
        _p.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass


def _bool(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


def _int_env(name: str, default: int) -> int:
    """Read an integer env var without ever crashing app import."""
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        logging.getLogger("meridian.config").warning(
            "Invalid %s=%r; using %s", name, os.getenv(name), default)
        return default


def _float_env(name: str, default: float) -> float:
    """Read a float env var without ever crashing app import."""
    try:
        return float(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        logging.getLogger("meridian.config").warning(
            "Invalid %s=%r; using %s", name, os.getenv(name), default)
        return default


def server_port(default: int = 8000) -> int:
    """Resolve the HTTP port at call time.

    PaaS hosts inject ``PORT`` at runtime (Render defaults to 10000). Reading
    it at call time means the same image works locally on 8000 and on Render
    without a rebuild.
    ``MERIDIAN_PORT`` is supported for local/direct launches, but a host
    injected ``PORT`` always wins (Render/Railway/Fly set it at runtime).
    """
    raw = os.getenv("PORT") or os.getenv("MERIDIAN_PORT") or str(default)
    try:
        value = int(raw)
    except (TypeError, ValueError):
        logging.getLogger("meridian.config").warning(
            "Invalid port %r; falling back to %s", raw, default)
        return default
    return value if 1 <= value <= 65535 else default


def web_concurrency() -> int:
    """Worker count. Meridian keeps in-memory job/SSE state, so this MUST stay 1."""
    raw = os.getenv("WEB_CONCURRENCY", "1")
    try:
        return max(1, min(int(raw), 4))
    except ValueError:
        return 1


@dataclass(frozen=True)
class Settings:
    """Immutable runtime settings."""

    app_name: str = "Meridian"
    tagline: str = "Market Intelligence, Redefined."
    version: str = "1.0.0"
    developer: str = "Mridul Sharma"

    host: str = os.getenv("MERIDIAN_HOST", "0.0.0.0")
    debug: bool = _bool("MERIDIAN_DEBUG", False)
    render_service: str = os.getenv("RENDER_SERVICE_NAME", "")  # set by Render

    # Startup / warm-up. On PaaS hosts the listening socket must be ready fast;
    # schema creation and demo seeding run in a background thread.
    warmup_in_background: bool = _bool("MERIDIAN_BACKGROUND_BOOTSTRAP", True)

    # Optional self-ping. It only helps while the process is alive (it cannot
    # wake a spun-down free-tier instance) — use an external pinger as well.
    self_ping_url: str = os.getenv("MERIDIAN_SELF_PING_URL", "").strip()
    self_ping_interval_s: int = _int_env("MERIDIAN_SELF_PING_INTERVAL", 600)

    # Database: SQLite by default, PostgreSQL when DATABASE_URL is supplied.
    database_url: str = os.getenv("DATABASE_URL", f"sqlite:///{(DATA_DIR / 'meridian.db').as_posix()}")
    redis_url: str = os.getenv("REDIS_URL", "")
    fernet_key_file: Path = Path(os.getenv("MERIDIAN_FERNET_KEY_FILE", DATA_DIR / ".fernet_key"))
    fernet_key: str = os.getenv("MERIDIAN_FERNET_KEY", "")

    # External data sources (all optional).
    tavily_api_key: str = os.getenv("TAVILY_API_KEY", "")
    news_api_key: str = os.getenv("NEWS_API_KEY", "")
    world_bank_enabled: bool = _bool("MERIDIAN_WORLD_BANK", True)
    request_timeout: float = _float_env("MERIDIAN_HTTP_TIMEOUT", 8.0)
    max_sources: int = _int_env("MERIDIAN_MAX_SOURCES", 12)

    # Behaviour.
    # Offline sample data is OFF by default: the product must not answer
    # without a real API. See app/api/answer_policy.py.
    demo_mode: bool = _bool("MERIDIAN_DEMO_MODE", False)
    require_live_evidence: bool = _bool("MERIDIAN_REQUIRE_LIVE_EVIDENCE", True)
    enable_live_data: bool = _bool("MERIDIAN_LIVE_DATA", True)
    use_yfinance: bool = _bool("MERIDIAN_USE_YFINANCE", False)
    max_workers: int = _int_env("MERIDIAN_MAX_WORKERS", 6)
    agent_timeout_s: float = _float_env("MERIDIAN_AGENT_TIMEOUT", 45.0)

    # OpenRouter free-model auto-selection (see app/api/openrouter_auto.py).
    openrouter_auto_enabled: bool = _bool("MERIDIAN_OPENROUTER_AUTO", True)
    openrouter_catalog_ttl: int = _int_env("MERIDIAN_OPENROUTER_CATALOG_TTL", 900)
    openrouter_catalog_timeout: float = _float_env("MERIDIAN_OPENROUTER_CATALOG_TIMEOUT", 5.0)
    openrouter_max_fallbacks: int = _int_env("MERIDIAN_OPENROUTER_FALLBACKS", 4)

    signature_trio: Tuple[str, str, str] = ("#0A1628", "#C9A84C", "#EDE4D3")

    @property
    def port(self) -> int:
        """Resolved at call time so ``--port`` overrides are reported correctly."""
        return server_port()

    @property
    def using_postgres(self) -> bool:
        return self.database_url.startswith(("postgresql", "postgres"))

    @property
    def platform(self) -> str:
        return "render" if self.render_service else "local"


settings = Settings()

# The six agent slots. Order is significant: it is the pipeline order.
AGENT_SLOTS: Tuple[Tuple[str, str, str, str], ...] = (
    ("researcher", "Researcher", "🔍", "Collects live market signals and verified sources"),
    ("analyst", "Analyst", "📊", "Runs SWOT, PESTLE, Porter's Five Forces and sizing"),
    ("writer", "Writer", "✍️", "Composes the board-ready research report"),
    ("chat", "Chat Agent", "💬", "Answers follow-up questions from report context"),
    ("forecast", "Forecast Agent", "📈", "Builds a 12-month forecast with confidence bands"),
    ("factchecker", "Fact-Checker", "✅", "Cross-verifies claims and scores reliability"),
    ("translator", "Translator", "🌐", "Localises the full report, preserving structure"),
)

REGIONS = ("Global", "North America", "Europe", "Asia Pacific", "India", "LATAM", "Middle East")
PERIODS = ("12M", "3Y", "5Y", "10Y")

SUPPORTED_LANGUAGES: Tuple[Tuple[str, str, str], ...] = (
    ("en", "English", "English"),
    ("hi", "Hindi", "हिन्दी"),
    ("es", "Spanish", "Español"),
    ("fr", "French", "Français"),
    ("de", "German", "Deutsch"),
    ("ja", "Japanese", "日本語"),
    ("zh", "Chinese", "中文"),
    ("ar", "Arabic", "العربية"),
    ("pt", "Portuguese", "Português"),
    ("ko", "Korean", "한국어"),
    ("ru", "Russian", "Русский"),
    ("it", "Italian", "Italiano"),
    ("bn", "Bengali", "বাংলা"),
    ("pa", "Punjabi", "ਪੰਜਾਬੀ"),
)
