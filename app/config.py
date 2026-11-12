"""Central configuration for Meridian.

All settings are read from the environment (or a local ``.env`` file) with
safe, demo-friendly defaults. Nothing here requires a paid service to boot.
"""
from __future__ import annotations

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


@dataclass(frozen=True)
class Settings:
    """Immutable runtime settings."""

    app_name: str = "Meridian"
    tagline: str = "Market Intelligence, Redefined."
    version: str = "1.0.0"
    developer: str = "Mridul Sharma"

    host: str = os.getenv("MERIDIAN_HOST", "0.0.0.0")
    port: int = int(os.getenv("MERIDIAN_PORT", "8000"))
    debug: bool = _bool("MERIDIAN_DEBUG", False)

    # Database: SQLite by default, PostgreSQL when DATABASE_URL is supplied.
    database_url: str = os.getenv("DATABASE_URL", f"sqlite:///{(DATA_DIR / 'meridian.db').as_posix()}")
    redis_url: str = os.getenv("REDIS_URL", "")
    fernet_key_file: Path = Path(os.getenv("MERIDIAN_FERNET_KEY_FILE", DATA_DIR / ".fernet_key"))
    fernet_key: str = os.getenv("MERIDIAN_FERNET_KEY", "")

    # External data sources (all optional).
    tavily_api_key: str = os.getenv("TAVILY_API_KEY", "")
    news_api_key: str = os.getenv("NEWS_API_KEY", "")
    world_bank_enabled: bool = _bool("MERIDIAN_WORLD_BANK", True)
    request_timeout: float = float(os.getenv("MERIDIAN_HTTP_TIMEOUT", "8"))
    max_sources: int = int(os.getenv("MERIDIAN_MAX_SOURCES", "12"))

    # Behaviour.
    demo_mode: bool = _bool("MERIDIAN_DEMO_MODE", True)
    enable_live_data: bool = _bool("MERIDIAN_LIVE_DATA", True)
    use_yfinance: bool = _bool("MERIDIAN_USE_YFINANCE", False)
    max_workers: int = int(os.getenv("MERIDIAN_MAX_WORKERS", "6"))
    agent_timeout_s: float = float(os.getenv("MERIDIAN_AGENT_TIMEOUT", "45"))

    signature_trio: Tuple[str, str, str] = ("#0A1628", "#C9A84C", "#EDE4D3")

    @property
    def using_postgres(self) -> bool:
        return self.database_url.startswith(("postgresql", "postgres"))


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
