"""Database, encryption vault and query-layer tests."""
from __future__ import annotations

import pytest

from app.api import key_manager
from app.database import queries
from app.database.connection import ensure_schema
from app.database.models import ensure_demo_user


@pytest.fixture(scope="module", autouse=True)
def _db():
    ensure_schema()


def test_schema_and_demo_user():
    uid = ensure_demo_user()
    assert uid and len(uid) == 36
    assert ensure_demo_user() == uid


def test_report_crud_lifecycle():
    rid = queries.create_report("Test semiconductor market", company="Test Co",
                                region="India", period="5Y")
    assert queries.get_report(rid)["status"] == "processing"
    queries.update_report(rid, status="completed", final_report="A full report",
                          reliability_score=88, researcher_output={"dataset": {"x": 1}})
    row = queries.get_report(rid)
    assert row["status"] == "completed" and row["reliability_score"] == 88
    assert row["researcher_output"]["dataset"]["x"] == 1
    assert any(r["id"] == rid for r in queries.list_reports())
    assert any(r["id"] == rid for r in queries.list_reports(search="semiconductor"))
    assert queries.delete_report(rid) is True
    assert queries.get_report(rid) is None


def test_chat_comparison_translation_and_logs():
    rid = queries.create_report("Chat context report")
    queries.add_chat_message(rid, "user", "What about rural markets?")
    queries.add_chat_message(rid, "assistant", "Segments suggest 18% SMB demand.")
    assert len(queries.get_chat_history(rid)) == 2
    queries.add_agent_log(rid, "researcher", "local", "done", 42, 10, 20)
    assert queries.get_agent_logs(rid)[0]["execution_time_ms"] == 42
    cid = queries.save_comparison("A", "B", {"metrics": []})
    assert any(c["id"] == cid for c in queries.list_comparisons())
    queries.save_translation(rid, "en", "hi", "अनुवाद")
    assert queries.get_cached_translation(rid, "hi") == "अनुवाद"
    assert queries.report_stats()["total_reports"] >= 1
    queries.delete_report(rid)


def test_api_keys_are_encrypted_at_rest():
    from sqlalchemy import text
    from app.database.connection import session_scope
    key_manager.save_key("researcher", "groq", "test-dummy-key-1234567890")
    creds = key_manager.get_credentials("researcher")
    assert creds["api_key"] == "test-dummy-key-1234567890"
    with session_scope() as s:
        stored = s.execute(text("SELECT api_key_encrypted FROM api_keys WHERE agent_name='researcher'")).scalar()
    assert stored.startswith("gAAAAA")
    assert "SUPERSECRET" not in stored
    status = next(x for x in key_manager.key_status() if x["slot"] == "researcher")
    assert status["configured"] and "SUPERSECRET" not in status["masked_key"]
    assert key_manager.delete_key("researcher") is True


def test_invalid_inputs_are_rejected():
    with pytest.raises(ValueError):
        key_manager.save_key("unknown_agent", "groq", "x")
    with pytest.raises(ValueError):
        key_manager.save_key("writer", "groq", "")
