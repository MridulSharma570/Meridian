#!/usr/bin/env python3
"""Initialise the Meridian database (SQLite by default, PostgreSQL if configured).

    python -m scripts.setup_db
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import settings  # noqa: E402
from app.database.connection import ensure_schema, get_engine  # noqa: E402
from app.database.models import ensure_demo_user  # noqa: E402
from sqlalchemy import inspect  # noqa: E402


def main() -> None:
    ensure_schema()
    uid = ensure_demo_user()
    inspector = inspect(get_engine())
    print("◆  MERIDIAN — database setup")
    print(f"   Engine   : {'PostgreSQL' if settings.using_postgres else 'SQLite'}")
    print(f"   Tables   : {', '.join(sorted(inspector.get_table_names()))}")
    print(f"   Demo user: {uid}")
    print("   Developed by Mridul Sharma")


if __name__ == "__main__":
    main()
