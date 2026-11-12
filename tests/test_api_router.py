"""LLM router, provider registry and HTTP API endpoint tests."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.api import key_manager
from app.api.llm_router import (_endpoint, _payload, is_configured,
                                test_connection as probe_connection)
from app.api.providers import PROVIDERS, get_provider, list_providers
from app.api.server import app


def test_provider_catalogue_is_complete():
    rows = list_providers()
    assert len(rows) >= 15
    assert {"groq", "gemini", "openai", "anthropic", "deepseek"} <= set(PROVIDERS)
    assert all(p["default_model"] in p["models"] for p in rows)
    assert any(p["group"] == "FREE" for p in rows)
    assert any(p["group"] == "PAID" for p in rows)
    with pytest.raises(ValueError):
        get_provider("not-a-provider")


def test_endpoints_and_payloads_for_every_wire_format():
    for p in PROVIDERS.values():
        ep = _endpoint(p)
        assert ep.startswith("http")
        body = _payload(p, p.default_model, "s", "u", 100, 0.2, False)
        assert "model" in body and "max_tokens" in body
        if p.api_style == "anthropic":
            assert "system" in body and "messages" in body
        if p.api_style == "openai":
            assert body["messages"][0]["role"] == "system"


def test_missing_key_fails_cleanly_without_secret_leakage():
    assert is_configured("writer") is False
    r = probe_connection("writer")
    assert r["ok"] is False and "No key" in r["error"]


def test_key_save_test_and_delete_via_api():
    with TestClient(app) as c:
        res = c.post("/api/settings/keys", json={"slot": "writer", "provider": "groq",
                                                 "api_key": "test-dummy-key-000111222",
                                                 "model": "llama-3.3-70b-versatile"})
        assert res.status_code == 200 and res.json()["ok"] is True
        status = c.get("/api/settings").json()
        slot = next(x for x in status["slots"] if x["slot"] == "writer")
        assert slot["configured"] and "TESTKEY" not in slot["masked_key"]
        assert status["configured_count"] >= 1
        # Test connection returns a structured failure when the network is unavailable.
        probe = c.post("/api/settings/keys/test", json={"slot": "writer"}).json()
        assert "ok" in probe
        assert c.delete("/api/settings/keys/writer").json()["ok"] is True
        assert c.post("/api/settings/keys/test", json={"slot": "writer"}).json()["ok"] is False


def test_core_endpoints():
    with TestClient(app) as c:
        assert c.get("/").status_code == 200
        assert c.get("/static/app.css").status_code == 200
        h = c.get("/api/health").json()
        assert h["app"] == "Meridian" and h["developer"] == "Mridul Sharma"
        b = c.get("/api/bootstrap").json()
        assert b["version"] == "1.0.0" and len(b["agents"]) == 7
        assert c.get("/api/providers").status_code == 200
        assert c.get("/api/agents").json()["chat_suggestions"]
        assert isinstance(c.get("/api/reports").json(), list)
        assert c.post("/api/reports", json={"query": "x"}).status_code == 422
        assert c.get("/api/reports/does-not-exist").status_code == 404
        assert c.get("/api/reports/does-not-exist/export/pdf").status_code == 404


def test_full_report_flow_via_api():
    import time
    with TestClient(app) as c:
        res = c.post("/api/reports", json={"query": "Fintech payments in India",
                                          "region": "India", "period": "3Y",
                                          "language": "en"})
        assert res.status_code == 201
        rid = res.json()["report_id"]
        deadline = time.time() + 30
        while time.time() < deadline:
            st = c.get(f"/api/reports/{rid}/status").json()
            if st["status"] != "processing":
                break
            time.sleep(.1)
        assert st["status"] == "completed", st
        dash = c.get(f"/api/reports/{rid}/dashboard?region=India&period=12M").json()
        assert "charts" in dash and len(dash["writer"]["sections"]) >= 8
        for fmt in ("pdf", "pptx", "excel"):
            assert c.get(f"/api/reports/{rid}/export/{fmt}").status_code == 200
        chat = c.post(f"/api/reports/{rid}/chat",
                      json={"question": "What about the rural market?"}).json()
        assert "rural" in chat["answer"].lower() or "tier-2" in chat["answer"].lower()
        tr = c.post(f"/api/reports/{rid}/translate", json={"language": "hi"}).json()
        assert tr["content"] and tr["language"] == "hi"
        cmp = c.post("/api/compare", json={"company_a": "Razorpay",
                                           "company_b": "Stripe"}).json()
        assert len(cmp["metrics"]) == 5
        assert c.delete(f"/api/reports/{rid}").json()["ok"] is True
