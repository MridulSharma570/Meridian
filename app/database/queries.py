"""Typed CRUD helpers. All database access from the app goes through here."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import desc, or_

from app.database.connection import session_scope
from app.database.models import (AgentLog, ApiKey, ChatHistory, Comparison,
                                 Report, Translation)


# --------------------------------------------------------------------------- #
# API keys
# --------------------------------------------------------------------------- #
def upsert_api_key(agent_name: str, provider: str, encrypted: str, model: str = "",
                   is_active: bool = True) -> Dict[str, Any]:
    with session_scope() as s:
        row = (s.query(ApiKey).filter(ApiKey.agent_name == agent_name)
               .order_by(desc(ApiKey.created_at)).first())
        if row is None:
            row = ApiKey(agent_name=agent_name)
            s.add(row)
        row.provider = provider
        row.model = model
        row.api_key_encrypted = encrypted
        row.is_active = is_active
        s.flush()
        return {"id": row.id, "agent_name": row.agent_name, "provider": row.provider}


def get_api_key_row(agent_name: str) -> Optional[Dict[str, Any]]:
    with session_scope() as s:
        row = (s.query(ApiKey).filter(ApiKey.agent_name == agent_name)
               .order_by(desc(ApiKey.updated_at)).first())
        if row is None:
            return None
        return {
            "id": row.id, "agent_name": row.agent_name, "provider": row.provider,
            "model": row.model or "", "encrypted": row.api_key_encrypted,
            "is_active": bool(row.is_active), "quota_info": row.quota_info,
            "last_tested_at": row.last_tested_at.isoformat() if row.last_tested_at else None,
            "last_test_ok": row.last_test_ok,
        }


def list_api_key_rows() -> List[Dict[str, Any]]:
    with session_scope() as s:
        rows = s.query(ApiKey).order_by(ApiKey.agent_name).all()
        return [{
            "id": r.id, "agent_name": r.agent_name, "provider": r.provider,
            "model": r.model or "", "encrypted": r.api_key_encrypted,
            "is_active": bool(r.is_active), "quota_info": r.quota_info,
            "last_tested_at": r.last_tested_at.isoformat() if r.last_tested_at else None,
            "last_test_ok": r.last_test_ok,
        } for r in rows]


def update_key_test(agent_name: str, ok: bool, quota: Optional[dict] = None) -> None:
    with session_scope() as s:
        row = (s.query(ApiKey).filter(ApiKey.agent_name == agent_name)
               .order_by(desc(ApiKey.updated_at)).first())
        if row:
            row.last_tested_at = datetime.utcnow()
            row.last_test_ok = ok
            if quota is not None:
                row.quota_info = quota


def delete_api_key(agent_name: str) -> bool:
    with session_scope() as s:
        rows = s.query(ApiKey).filter(ApiKey.agent_name == agent_name).all()
        if not rows:
            return False
        for r in rows:
            s.delete(r)
        return True


def count_active_keys() -> int:
    with session_scope() as s:
        return s.query(ApiKey).filter(ApiKey.is_active.is_(True)).count()


# --------------------------------------------------------------------------- #
# Reports
# --------------------------------------------------------------------------- #
def create_report(query: str, *, company: str = "", region: str = "Global",
                  period: str = "3Y", language: str = "en",
                  user_id: Optional[str] = None) -> str:
    with session_scope() as s:
        r = Report(query=query, company=company, region=region, period=period,
                   language=language, user_id=user_id, status="processing")
        s.add(r)
        s.flush()
        return r.id


def update_report(report_id: str, **fields: Any) -> None:
    with session_scope() as s:
        r = s.get(Report, report_id)
        if r is None:
            raise KeyError(f"Report {report_id} not found")
        for k, v in fields.items():
            if hasattr(r, k):
                setattr(r, k, v)


def get_report(report_id: str) -> Optional[Dict[str, Any]]:
    with session_scope() as s:
        r = s.get(Report, report_id)
        return _report_dict(r) if r else None


def _report_dict(r: Report) -> Dict[str, Any]:
    def iso(d):
        return d.isoformat() if d else None
    return {
        "id": r.id, "query": r.query, "company": r.company, "region": r.region,
        "period": r.period, "status": r.status, "language": r.language,
        "researcher_output": r.researcher_output, "analyst_output": r.analyst_output,
        "writer_output": r.writer_output, "chat_output": r.chat_output,
        "forecast_output": r.forecast_output, "factcheck_output": r.factcheck_output,
        "comparison_data": r.comparison_data, "final_report": r.final_report,
        "translated_report": r.translated_report,
        "reliability_score": r.reliability_score,
        "pdf_path": r.pdf_path, "pptx_path": r.pptx_path, "excel_path": r.excel_path,
        "error_message": r.error_message, "created_at": iso(r.created_at),
        "completed_at": iso(r.completed_at),
    }


def list_reports(search: str = "", status: str = "", region: str = "",
                 limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
    with session_scope() as s:
        q = s.query(Report)
        if search:
            like = f"%{search}%"
            q = q.filter(or_(Report.query.like(like), Report.company.like(like),
                             Report.final_report.like(like)))
        if status:
            q = q.filter(Report.status == status)
        if region:
            q = q.filter(Report.region == region)
        rows = q.order_by(desc(Report.created_at)).offset(offset).limit(limit).all()
        return [{"id": r.id, "query": r.query, "company": r.company,
                 "region": r.region, "period": r.period, "status": r.status,
                 "language": r.language, "reliability_score": r.reliability_score,
                 "created_at": r.created_at.isoformat() if r.created_at else None,
                 "completed_at": r.completed_at.isoformat() if r.completed_at else None,
                 "has_pdf": bool(r.pdf_path), "has_pptx": bool(r.pptx_path),
                 "has_excel": bool(r.excel_path)} for r in rows]


def delete_report(report_id: str) -> bool:
    with session_scope() as s:
        r = s.get(Report, report_id)
        if r is None:
            return False
        s.delete(r)
        return True


def report_stats() -> Dict[str, Any]:
    with session_scope() as s:
        total = s.query(Report).count()
        completed = s.query(Report).filter(Report.status == "completed").count()
        failed = s.query(Report).filter(Report.status == "failed").count()
        scores = [x[0] for x in s.query(Report.reliability_score)
                  .filter(Report.status == "completed").all() if x[0]]
        return {
            "total_reports": total, "completed": completed, "failed": failed,
            "avg_reliability": round(sum(scores) / len(scores), 1) if scores else 0,
            "sources_analyzed": completed * 12,
            "agents_run": s.query(AgentLog).count(),
        }


# --------------------------------------------------------------------------- #
# Chat / logs / comparisons / translations
# --------------------------------------------------------------------------- #
def add_chat_message(report_id: str, role: str, message: str) -> None:
    with session_scope() as s:
        s.add(ChatHistory(report_id=report_id, role=role, message=message))


def get_chat_history(report_id: str, limit: int = 60) -> List[Dict[str, Any]]:
    with session_scope() as s:
        rows = (s.query(ChatHistory).filter(ChatHistory.report_id == report_id)
                .order_by(ChatHistory.created_at).limit(limit).all())
        return [{"role": r.role, "message": r.message,
                 "created_at": r.created_at.isoformat()} for r in rows]


def add_agent_log(report_id: str, agent_name: str, provider_used: str,
                  status: str, execution_time_ms: int, input_tokens: int = 0,
                  output_tokens: int = 0, error_message: str = "") -> None:
    try:
        with session_scope() as s:
            s.add(AgentLog(report_id=report_id, agent_name=agent_name,
                           provider_used=provider_used, status=status,
                           execution_time_ms=execution_time_ms,
                           input_tokens=input_tokens, output_tokens=output_tokens,
                           error_message=error_message or None))
    except Exception:
        pass  # telemetry must never break the pipeline


def get_agent_logs(report_id: str) -> List[Dict[str, Any]]:
    with session_scope() as s:
        rows = (s.query(AgentLog).filter(AgentLog.report_id == report_id)
                .order_by(AgentLog.created_at).all())
        return [{"agent_name": r.agent_name, "provider_used": r.provider_used,
                 "status": r.status, "execution_time_ms": r.execution_time_ms,
                 "input_tokens": r.input_tokens, "output_tokens": r.output_tokens,
                 "error_message": r.error_message,
                 "created_at": r.created_at.isoformat()} for r in rows]


def save_comparison(company_a: str, company_b: str, data: dict) -> str:
    with session_scope() as s:
        c = Comparison(company_a=company_a, company_b=company_b, comparison_data=data)
        s.add(c)
        s.flush()
        return c.id


def list_comparisons(limit: int = 30) -> List[Dict[str, Any]]:
    with session_scope() as s:
        rows = s.query(Comparison).order_by(desc(Comparison.created_at)).limit(limit).all()
        return [{"id": r.id, "company_a": r.company_a, "company_b": r.company_b,
                 "comparison_data": r.comparison_data,
                 "created_at": r.created_at.isoformat()} for r in rows]


def save_translation(report_id: str, source: str, target: str, content: str) -> None:
    with session_scope() as s:
        s.add(Translation(report_id=report_id, source_language=source,
                          target_language=target, translated_content=content))


def get_cached_translation(report_id: str, target: str) -> Optional[str]:
    with session_scope() as s:
        row = (s.query(Translation).filter(Translation.report_id == report_id,
               Translation.target_language == target)
               .order_by(desc(Translation.created_at)).first())
        return row.translated_content if row else None
