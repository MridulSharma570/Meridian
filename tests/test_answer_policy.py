"""Verified-answer policy: no API key means no generated answer.

The rest of the suite runs with ``MERIDIAN_SAMPLE_MODE=true`` (see conftest),
which exercises the explicitly labelled offline sample engine. These tests
turn sample mode OFF and assert the production behaviour: Meridian fails
closed with a structured, actionable error instead of inventing an answer.
"""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from app import services
from app.agents.chat_agent import ChatAgent
from app.agents.translator import TranslatorAgent
from app.agents.writer import WriterAgent
from app.api import answer_policy
from app.api.server import app
from app.data_sources.collector import collect_market_data
from app.data_sources.demo_data import build_market_dataset
from app.database import queries
from app.database.connection import ensure_schema


@pytest.fixture()
def strict(monkeypatch):
    """Production mode: sample engine off, no provider keys configured."""
    monkeypatch.delenv("MERIDIAN_SAMPLE_MODE", raising=False)
    monkeypatch.setattr(answer_policy, "configured_llm_slots", lambda: [])
    ensure_schema()
    for slot in ("researcher", "analyst", "writer", "chat", "forecast",
                 "factchecker", "translator"):
        queries.delete_api_key(slot)
    assert answer_policy.strict_mode() is True
    assert answer_policy.readiness()["answers_enabled"] is False
    return monkeypatch


def test_readiness_reports_answers_disabled(strict):
    ready = answer_policy.readiness()
    assert ready["llm_configured"] is False
    assert ready["sample_mode"] is False
    assert ready["reason"] == "api_key_required"
    assert ready["setup_path"] == "#/settings"
    with TestClient(app) as c:
        body = c.get("/api/readiness").json()
        assert body["answers_enabled"] is False
        boot = c.get("/api/bootstrap").json()
        assert boot["demo_mode"] is False
        assert boot["readiness"]["reason"] == "api_key_required"


def test_start_report_refuses_without_api_key(strict):
    before = len(queries.list_reports(limit=500))
    with pytest.raises(answer_policy.AnswerUnavailable) as exc:
        services.start_report("Electric vehicle market in India")
    assert exc.value.reason == "api_key_required"
    assert len(queries.list_reports(limit=500)) == before  # nothing was created


def test_report_api_returns_structured_409_without_key(strict):
    with TestClient(app) as c:
        res = c.post("/api/reports", json={"query": "Fintech in India",
                                           "region": "India", "period": "3Y"})
        assert res.status_code == 409
        body = res.json()
        assert body["error"] == "answer_unavailable"
        assert body["reason"] == "api_key_required"
        assert "Settings" in body["hint"]
        chat = c.post("/api/reports/anything/chat", json={"question": "Why?"})
        assert chat.status_code in (404, 409)


def test_chat_never_falls_back_to_template_answer(strict):
    strict.setattr(answer_policy, "configured_llm_slots", lambda: ["chat"])
    strict.setattr("app.agents.chat_agent.effective_slot", lambda _slot: "chat")

    def boom(*_args, **_kwargs):
        raise RuntimeError("provider unavailable")

    strict.setattr("app.agents.chat_agent.call_llm", boom)
    ctx = {"dataset": {"company": "Acme", "verified_sources": [
        {"id": "L01", "title": "Real source", "publisher": "Example Wire",
         "url": "https://example.com/a"}]},
        "analyst": {}, "writer": {}, "researcher": {}}
    with pytest.raises(answer_policy.AnswerUnavailable):
        ChatAgent().answer(ctx, "What is the outlook?")


def test_chat_requires_api_key(strict):
    ctx = {"dataset": {"verified_sources": []}, "analyst": {}, "writer": {}}
    with pytest.raises(answer_policy.AnswerUnavailable) as exc:
        ChatAgent().answer(ctx, "Summarise this report")
    assert exc.value.reason == "api_key_required"


def test_translator_requires_api_key(strict):
    with pytest.raises(answer_policy.AnswerUnavailable):
        TranslatorAgent().translate("# Report\n\nBody", "hi", {"dataset": {}})


def test_compare_requires_api_key(strict):
    with pytest.raises(answer_policy.AnswerUnavailable):
        services.compare_companies("Tesla", "BYD")


def test_collector_strips_fabricated_evidence_in_strict_mode(strict):
    data = collect_market_data("Tesla electric vehicles", "India", "3Y")
    assert data["verified_sources"] == []
    assert data["sources"] == []
    assert data["news"] == []
    assert data["verified"] is False
    assert data["unverified_metrics"] is True
    assert data["market_size_usd_b"] == 0
    assert all(c["share"] == 0 for c in data["competitors"])
    assert "Reuters" not in json.dumps(data["sources"])


def test_sample_engine_is_loudly_labelled():
    data = build_market_dataset("Tesla electric vehicles", "India", "3Y")
    assert data["data_mode"] == "sample"
    assert data["sample"] is True
    assert all(s["verified"] is False for s in data["sources"])
    assert all("example.invalid" in s["url"] for s in data["sources"])
    assert "SAMPLE" in data["sources"][0]["title"]


def test_legacy_sample_report_is_not_served_as_verified(strict):
    rid = queries.create_report("Legacy offline report", company="Legacy",
                                region="Global", period="3Y", language="en")
    dataset = build_market_dataset("Legacy offline report", "Global", "3Y")
    queries.update_report(
        rid, status="completed",
        researcher_output={"dataset": dataset, "sources": dataset["sources"]},
        writer_output={"markdown": "# Legacy", "sections": [],
                       "executive_summary": "Invented summary"},
        analyst_output={}, forecast_output={}, factcheck_output={})
    with pytest.raises(answer_policy.AnswerUnavailable) as exc:
        services.dashboard_payload(rid)
    assert exc.value.reason == "unverified_report"
    with pytest.raises(answer_policy.AnswerUnavailable):
        services.report_context(rid)


def test_writer_uses_provider_text_when_api_and_evidence_exist(strict):
    strict.setattr(answer_policy, "configured_llm_slots", lambda: ["writer"])
    markdown = ("# Verified Report [L01]\n\n" +
                ("Evidence-led analysis [Z99]. " * 40))

    def fake_call(*_args, **_kwargs):
        return {"text": json.dumps({
                    "markdown": markdown,
                    "executive_summary": "Generated by the configured provider.",
                    "citations": ["[L01]"], "recommendations": ["Act on evidence"],
                    "headline": "Evidence-led report"}),
                "provider": "Mock Provider", "model": "mock-model",
                "input_tokens": 10, "output_tokens": 20}

    strict.setattr("app.agents.base.call_llm", fake_call)
    strict.setattr("app.agents.base.effective_slot", lambda _slot: "writer")
    ctx = {"query": "EV market", "region": "India", "period": "3Y",
           "dataset": {"company": "Acme", "sector": "EV", "region": "India",
                       "verified_sources": [
                           {"id": "L01", "title": "Real source",
                            "publisher": "Example Wire",
                            "url": "https://example.com/a"}]},
           "analyst": {"summary": "Provider summary"}, "researcher": {}}
    result = WriterAgent().run(ctx)
    assert result.provider == "Mock Provider"
    assert "[L01]" in result.data["markdown"]
    assert "[Z99]" not in result.data["markdown"]
    assert result.data["citations"] == ["[L01]"]
    assert result.data["verified_answer"] is True
    assert result.source == "llm"


def test_writer_refuses_unusable_provider_output(strict):
    strict.setattr(answer_policy, "configured_llm_slots", lambda: ["writer"])
    strict.setattr("app.agents.base.effective_slot", lambda _slot: "writer")
    strict.setattr("app.agents.base.call_llm",
                   lambda *_a, **_k: {"text": "not json", "provider": "Mock",
                                      "model": "mock", "input_tokens": 0,
                                      "output_tokens": 0})
    ctx = {"query": "EV market", "dataset": {"verified_sources": [
        {"id": "L01", "title": "Real", "publisher": "Wire",
         "url": "https://example.com"}]}, "analyst": {}, "researcher": {}}
    with pytest.raises(answer_policy.AnswerUnavailable):
        WriterAgent().run(ctx)


def test_strict_orchestrator_uses_only_provider_answers(strict):
    """With a key + live evidence, every narrative comes from the provider."""
    from app.agents.orchestrator import Orchestrator

    strict.setattr(answer_policy, "configured_llm_slots", lambda: ["writer"])
    strict.setattr("app.agents.base.effective_slot", lambda _slot: "writer")

    source = {"id": "L01", "title": "Real market source", "publisher": "Example Wire",
              "url": "https://example.com/report", "type": "Live Web Result",
              "reliability": 82, "verified": True}
    dataset = build_market_dataset("EV market India", "India", "3Y")
    dataset.update({"verified_sources": [source], "sources": [source],
                    "data_mode": "verified", "verified": True,
                    "connectors": {"web_search": "live"}})
    strict.setattr("app.agents.researcher.collect_market_data",
                   lambda *_a, **_k: dataset)

    markdown = "# Provider Report [L01]\n\n" + ("Provider-written analysis. " * 40)

    def fake_call(_slot, _system, prompt, **_kwargs):
        if "Write a complete" in prompt:
            payload = {"markdown": markdown, "executive_summary": "Provider summary.",
                       "citations": ["[L01]"], "recommendations": ["Use evidence"],
                       "headline": "Provider report"}
        elif "Rewrite the strategic analysis" in prompt:
            payload = {"summary": "Provider analyst summary.",
                       "swot": {"Strengths": ["Evidence"], "Weaknesses": ["Gaps"],
                                "Opportunities": ["Growth"], "Threats": ["Risk"]},
                       "strategic_priorities": ["Verify"], "growth_drivers": ["Evidence"]}
        elif "Forecast agent" in prompt:
            payload = {"narratives": ["Base narrative", "Up narrative", "Down narrative"],
                       "key_risk": "Evidence gap"}
        elif "Fact-Checker agent" in prompt:
            payload = {"review_notes": ["Only L01 is citable"],
                       "highest_risk_claim": "Unsupported figures"}
        else:
            payload = {"executive_signals": ["One live source retrieved"],
                       "source_notes": ["L01 retrieved live"], "data_gaps": ["Sizing"]}
        return {"text": json.dumps(payload), "provider": "Mock Provider",
                "model": "mock-model", "input_tokens": 5, "output_tokens": 7}

    strict.setattr("app.agents.base.call_llm", fake_call)
    state = Orchestrator("", lambda _e: None).run(
        "EV market India", region="India", period="3Y", language="en")
    assert state["final_report"] == markdown
    assert state["writer"]["verified_answer"] is True
    assert state["analyst"]["summary"] == "Provider analyst summary."
    assert state["researcher"]["source_count"] == 1
    assert state["reliability_score"] == 0  # never invented in strict mode
