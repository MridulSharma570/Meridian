"""SQLAlchemy models — mirrors the published Meridian schema.

JSON columns use PostgreSQL JSONB when available and plain JSON on SQLite.
Every primary key is a portable 36-char UUID string.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict

from sqlalchemy import (JSON, Boolean, DateTime, ForeignKey, Integer, String,
                        Text, func)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

JsonType = JSON().with_variant(JSONB(), "postgresql")


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    full_name: Mapped[str] = mapped_column(String(100), default="Meridian User")
    plan: Mapped[str] = mapped_column(String(20), default="free")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class ApiKey(Base):
    __tablename__ = "api_keys"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"),
                                         nullable=True, index=True)
    agent_name: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    provider: Mapped[str] = mapped_column(String(50), nullable=False, default="groq")
    model: Mapped[str] = mapped_column(String(120), default="")
    api_key_encrypted: Mapped[str] = mapped_column(String(2000), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_tested_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_test_ok: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    quota_info: Mapped[Dict[str, Any] | None] = mapped_column(JsonType, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)


class Report(Base):
    __tablename__ = "reports"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(36), nullable=True, index=True)
    query: Mapped[str] = mapped_column(Text, nullable=False)
    company: Mapped[str] = mapped_column(String(200), default="")
    region: Mapped[str] = mapped_column(String(60), default="Global")
    period: Mapped[str] = mapped_column(String(20), default="3Y")
    status: Mapped[str] = mapped_column(String(20), default="processing", index=True)
    language: Mapped[str] = mapped_column(String(10), default="en")
    researcher_output: Mapped[dict | None] = mapped_column(JsonType, nullable=True)
    analyst_output: Mapped[dict | None] = mapped_column(JsonType, nullable=True)
    writer_output: Mapped[dict | None] = mapped_column(JsonType, nullable=True)
    chat_output: Mapped[dict | None] = mapped_column(JsonType, nullable=True)
    forecast_output: Mapped[dict | None] = mapped_column(JsonType, nullable=True)
    factcheck_output: Mapped[dict | None] = mapped_column(JsonType, nullable=True)
    comparison_data: Mapped[dict | None] = mapped_column(JsonType, nullable=True)
    final_report: Mapped[str | None] = mapped_column(Text, nullable=True)
    translated_report: Mapped[str | None] = mapped_column(Text, nullable=True)
    reliability_score: Mapped[int] = mapped_column(Integer, default=0)
    pdf_path: Mapped[str] = mapped_column(String(255), default="")
    pptx_path: Mapped[str] = mapped_column(String(255), default="")
    excel_path: Mapped[str] = mapped_column(String(255), default="")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now, index=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class ChatHistory(Base):
    __tablename__ = "chat_history"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    report_id: Mapped[str] = mapped_column(String(36), ForeignKey("reports.id", ondelete="CASCADE"),
                                           index=True)
    role: Mapped[str] = mapped_column(String(10), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class AgentLog(Base):
    __tablename__ = "agent_logs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    report_id: Mapped[str] = mapped_column(String(36), ForeignKey("reports.id", ondelete="CASCADE"),
                                           index=True)
    agent_name: Mapped[str] = mapped_column(String(50), nullable=False)
    provider_used: Mapped[str] = mapped_column(String(50), default="local-engine")
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    execution_time_ms: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20), default="done")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class Comparison(Base):
    __tablename__ = "comparisons"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(36), nullable=True)
    company_a: Mapped[str] = mapped_column(String(200), default="")
    company_b: Mapped[str] = mapped_column(String(200), default="")
    comparison_data: Mapped[dict | None] = mapped_column(JsonType, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class Translation(Base):
    __tablename__ = "translations"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    report_id: Mapped[str] = mapped_column(String(36), ForeignKey("reports.id", ondelete="CASCADE"),
                                           index=True)
    source_language: Mapped[str] = mapped_column(String(10), default="en")
    target_language: Mapped[str] = mapped_column(String(10), default="en")
    translated_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


def ensure_demo_user() -> str:
    """Return the id of the local demo user, creating it on first use."""
    from app.database.connection import session_scope
    with session_scope() as s:
        u = s.query(User).filter(User.email == "demo@meridian.local").first()
        if u is None:
            u = User(email="demo@meridian.local", full_name="Mridul Sharma",
                     plan="enterprise", password_hash="")
            s.add(u)
            s.flush()
        return u.id
