#!/usr/bin/env python3
"""Idempotent schema migration.

Creates any missing tables and, on SQLite, adds columns introduced after an
earlier release. Safe to run on every deployment.

    python -m scripts.migrate
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import inspect, text  # noqa: E402
from app.config import settings  # noqa: E402
from app.database.connection import ensure_schema, get_engine, session_scope  # noqa: E402
from app.database.models import Base  # noqa: E402

# column -> DDL type for columns added after v1.0.0 base schema
EXPECTED_COLUMNS = {
    "reports": {"company": "VARCHAR(200)", "region": "VARCHAR(60)",
                "period": "VARCHAR(20)", "translated_report": "TEXT",
                "reliability_score": "INTEGER", "error_message": "TEXT"},
    "api_keys": {"model": "VARCHAR(120)", "last_tested_at": "DATETIME",
                 "last_test_ok": "BOOLEAN", "quota_info": "JSON", "updated_at": "DATETIME"},
}


def main() -> None:
    ensure_schema()
    engine = get_engine()
    inspector = inspect(engine)
    added = 0
    with session_scope() as s:
        for table, columns in EXPECTED_COLUMNS.items():
            if table not in inspector.get_table_names():
                continue
            existing = {c["name"] for c in inspector.get_columns(table)}
            for name, ddl in columns.items():
                if name not in existing:
                    s.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}"))
                    print(f"   + {table}.{name}")
                    added += 1
    print("◆  MERIDIAN — migration complete")
    print(f"   Tables: {len(Base.metadata.tables)} · columns added: {added}")
    print(f"   Engine: {'PostgreSQL' if settings.using_postgres else 'SQLite'}")
    print("   Developed by Mridul Sharma")


if __name__ == "__main__":
    main()
