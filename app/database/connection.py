"""Database engine and session management.

PostgreSQL is used whenever ``DATABASE_URL`` points at it; otherwise Meridian
falls back to a zero-configuration SQLite file so the product boots anywhere.
Redis is entirely optional — a missing cache never breaks a request.
"""
from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Iterator, Optional

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings

logger = logging.getLogger("meridian.db")

_engine: Optional[Engine] = None
_SessionFactory: Optional[sessionmaker] = None
_redis = None
_initialised = False


def _build_engine() -> Engine:
    url = settings.database_url
    kwargs = {"pool_pre_ping": True, "future": True}
    if url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False, "timeout": 30}
    else:
        kwargs.update({"pool_size": 5, "max_overflow": 10, "pool_recycle": 1800})
    eng = create_engine(url, **kwargs)

    if url.startswith("sqlite"):
        @event.listens_for(eng, "connect")
        def _sqlite_pragmas(dbapi_conn, _record):  # pragma: no cover - driver level
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA journal_mode=WAL")
            cur.execute("PRAGMA foreign_keys=ON")
            cur.execute("PRAGMA busy_timeout=30000")
            cur.close()

    return eng


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        _engine = _build_engine()
    return _engine


def get_session_factory() -> sessionmaker:
    global _SessionFactory
    if _SessionFactory is None:
        _SessionFactory = sessionmaker(bind=get_engine(), expire_on_commit=False,
                                       autoflush=False, class_=Session)
    return _SessionFactory


def ensure_schema() -> None:
    """Create tables on first use — makes the app immune to import-order bugs."""
    global _initialised
    if _initialised:
        return
    try:
        init_db()
        _initialised = True
    except Exception as exc:  # pragma: no cover - misconfigured database
        logger.error("Schema initialisation failed: %s", exc)
        raise


@contextmanager
def session_scope() -> Iterator[Session]:
    """Transactional scope with automatic commit / rollback / close."""
    ensure_schema()
    s = get_session_factory()()
    try:
        yield s
        s.commit()
    except Exception:
        s.rollback()
        raise
    finally:
        s.close()


def init_db() -> None:
    """Create every table. Safe to call repeatedly."""
    from app.database.models import Base  # local import avoids cycles
    Base.metadata.create_all(get_engine())
    logger.info("Database ready (%s)", "PostgreSQL" if settings.using_postgres else "SQLite")


def get_redis():
    """Return a Redis client, or ``None`` when Redis is unavailable/unset."""
    global _redis
    if _redis is not None:
        return _redis
    if not settings.redis_url:
        return None
    try:
        import redis  # type: ignore
        client = redis.from_url(settings.redis_url, socket_connect_timeout=1,
                                socket_timeout=1, decode_responses=True)
        client.ping()
        _redis = client
        logger.info("Redis cache connected")
        return _redis
    except Exception as exc:  # pragma: no cover - depends on deployment
        logger.warning("Redis unavailable, continuing without cache: %s", exc)
        return None


def cache_get(key: str):
    client = get_redis()
    if client is None:
        return None
    try:
        return client.get(key)
    except Exception:
        return None


def cache_set(key: str, value: str, ttl: int = 900) -> None:
    client = get_redis()
    if client is None:
        return
    try:
        client.setex(key, ttl, value)
    except Exception:
        pass
