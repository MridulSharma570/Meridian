"""Regression tests for empty/truncated free-model completions.

The screenshots behind this suite showed a verified report dying first at
Researcher ("unusable output") and then at Analyst ("empty completion"),
while Mission Control kept Analyst at WORKING. These tests lock in the
recovery behaviour and the terminal failure telemetry without contacting a
real provider.

Developed by Mridul Sharma
"""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import app.agents.base as base
from app import services
from app.agents.base import BaseAgent, extract_json
from app.agents.orchestrator import Orchestrator
from app.agents.researcher import ResearcherAgent
from app.api import answer_policy, key_manager, llm_router
from app.api.providers import get_provider
from app.database import queries


class FakeResponse:
    def __init__(self, data):
        self.status_code = 200
        self._data = data
        self.text = json.dumps(data)
        self.headers = {}

    def json(self):
        return self._data


def _completion(model: str, *, content=None, reasoning=None,
                finish_reason="stop", reasoning_tokens=0):
    message = {"role": "assistant", "content": content}
    if reasoning is not None:
        message["reasoning"] = reasoning
    return FakeResponse({
        "model": model,
        "choices": [{"message": message, "finish_reason": finish_reason}],
        "usage": {"prompt_tokens": 12, "completion_tokens": 30,
                  "completion_tokens_details": {
                      "reasoning_tokens": reasoning_tokens}},
    })


# --------------------------------------------------------------------------- #
# Router completion parsing
# --------------------------------------------------------------------------- #
def test_reasoning_only_length_response_is_typed_as_truncated():
    provider = get_provider("openrouter_free")
    data = {
        "choices": [{
            "message": {"content": None, "reasoning": "thinking only"},
            "finish_reason": "length",
        }],
        "usage": {"completion_tokens": 2400,
                  "completion_tokens_details": {"reasoning_tokens": 2400}},
    }
    with pytest.raises(llm_router.LLMError) as exc:
        llm_router._extract_completion(provider, data)
    assert exc.value.category == "completion_truncated"
    assert exc.value.kind == "truncated"
    assert exc.value.finish_reason == "length"
    assert exc.value.reasoning_tokens == 2400


def test_reasoning_stop_and_refusal_and_empty_are_distinct():
    provider = get_provider("openrouter_free")

    reasoning = {
        "choices": [{"message": {"content": "", "reasoning": "draft"},
                     "finish_reason": "stop"}],
        "usage": {},
    }
    with pytest.raises(llm_router.LLMError) as exc:
        llm_router._extract_completion(provider, reasoning)
    assert exc.value.category == "completion_reasoning_only"

    refusal = {
        "choices": [{"message": {"content": None, "refusal": "No"},
                     "finish_reason": "stop"}],
        "usage": {},
    }
    with pytest.raises(llm_router.LLMError) as exc:
        llm_router._extract_completion(provider, refusal)
    assert exc.value.category == "completion_refused"

    with pytest.raises(llm_router.LLMError) as exc:
        llm_router._extract_completion(provider, {"choices": []})
    assert exc.value.category == "completion_empty"


def test_content_parts_ignore_reasoning_but_keep_text():
    provider = get_provider("openrouter_free")
    data = {
        "choices": [{
            "message": {"content": [
                {"type": "reasoning", "text": "hidden draft"},
                {"type": "text", "text": "Final answer"},
            ]},
            "finish_reason": "stop",
        }],
        "usage": {"completion_tokens": 8},
    }
    text, meta = llm_router._extract_completion(provider, data)
    assert text == "Final answer"
    assert meta["truncated"] is False


def test_openrouter_reasoning_budget_failure_retries_same_model_directly(monkeypatch):
    pinned = "vendor/reasoner:free"
    key_manager.save_key("writer", "openrouter_free",
                         "test-dummy-key-openrouter-000111", pinned)
    bodies = []

    def post(url, *, headers, json, timeout):
        bodies.append(json)
        if len(bodies) == 1:
            return _completion(pinned, content=None, reasoning="draft",
                               finish_reason="length", reasoning_tokens=99)
        return _completion(pinned, content='{"summary":"Recovered"}')

    monkeypatch.setattr(llm_router.requests, "post", post)
    try:
        result = llm_router.call_llm("writer", "sys", "user", json_mode=True)
    finally:
        key_manager.delete_key("writer")

    assert len(bodies) == 2
    assert "reasoning" not in bodies[0]
    assert bodies[1]["reasoning"] == {"effort": "none", "exclude": True}
    assert result["text"] == '{"summary":"Recovered"}'
    assert result["reasoning_retry"] is True


# --------------------------------------------------------------------------- #
# Agent JSON recovery
# --------------------------------------------------------------------------- #
def test_extract_json_repairs_common_truncations():
    assert extract_json('{"summary":"ok","items":[1,2') == {
        "summary": "ok", "items": [1, 2]}
    recovered = extract_json(
        'Here is the result: {"summary":"ok",'
        '"pestle":[{"factor":"Economic","note":"cut off')
    assert recovered["summary"] == "ok"
    assert recovered["pestle"][0]["factor"] == "Economic"
    assert extract_json('{"summary":"ok","incomplete":') == {"summary": "ok"}


def test_researcher_validation_uses_wire_key_names():
    agent = ResearcherAgent()
    assert agent._has_verified_content({"executive_signals": ["signal"]})
    assert not agent._has_verified_content({"signals": ["wrong wire key"]})
    assert not agent._has_verified_content({})


class _DummyAgent(BaseAgent):
    name = "analyst"
    slot = "analyst"
    verified_fields = ("summary",)

    def local_run(self, ctx):
        return {"summary": "scaffold"}

    def strict_prompt(self, ctx, scaffold):
        return "Return JSON with a summary."


def test_agent_retries_malformed_output_and_avoids_bad_model(monkeypatch):
    monkeypatch.delenv("MERIDIAN_SAMPLE_MODE", raising=False)
    monkeypatch.setattr(base.answer_policy, "require_api", lambda feature: None)
    monkeypatch.setattr(base, "effective_slot", lambda slot: slot)
    responses = [
        {"text": "not json", "provider": "OpenRouter (Free)",
         "model": "vendor/bad:free", "input_tokens": 10, "output_tokens": 3},
        {"text": '{"summary":"Recovered"}', "provider": "OpenRouter (Free)",
         "model": "vendor/good:free", "input_tokens": 11, "output_tokens": 5},
    ]
    calls = []

    def fake_call(slot, system, user, **kwargs):
        calls.append({"slot": slot, "user": user, **kwargs})
        return responses.pop(0)

    monkeypatch.setattr(base, "call_llm", fake_call)
    events = []
    result = _DummyAgent("", events.append).run({})

    assert result.data["summary"] == "Recovered"
    assert result.data["provider_attempts"] == 2
    assert len(calls) == 2
    assert "RETRY 2" in calls[1]["user"]
    assert calls[1]["avoid_models"] == ["vendor/bad:free"]
    assert any(event["type"] == "agent_retry" for event in events)


# --------------------------------------------------------------------------- #
# Terminal pipeline telemetry and honest counters
# --------------------------------------------------------------------------- #
def test_orchestrator_emits_terminal_agent_failed_event(monkeypatch):
    class FailingAgent:
        def __init__(self, report_id, emit):
            pass

        def run(self, ctx):
            raise answer_policy.AnswerUnavailable(
                "provider returned no answer", "try another model",
                "provider_failed")

    monkeypatch.setitem(Orchestrator.__init__.__globals__["AGENT_CLASSES"],
                        "analyst", FailingAgent)
    events = []
    orchestrator = Orchestrator("", events.append)
    with pytest.raises(answer_policy.AnswerUnavailable):
        orchestrator._run_agent("analyst", {})

    failed = [event for event in events if event["type"] == "agent_failed"]
    assert len(failed) == 1
    assert failed[0]["agent"] == "analyst"
    assert failed[0]["status"] == "failed"
    assert failed[0]["error"] == "provider returned no answer"


def test_job_status_maps_agent_failed_to_failed(monkeypatch):
    job = SimpleNamespace(
        status="failed", error="provider failed", started_at=0,
        events=[
            {"type": "agent_start", "agent": "analyst", "name": "Analyst"},
            {"type": "agent_failed", "agent": "analyst", "name": "Analyst",
             "status": "failed", "elapsed_ms": 42, "error": "empty completion"},
        ])
    monkeypatch.setattr(services, "get_job", lambda report_id: job)
    monkeypatch.setattr(services.queries, "get_report", lambda report_id: None)

    status = services.job_status("report-1")
    assert status["status"] == "failed"
    assert status["agents"]["analyst"]["status"] == "failed"
    assert status["agents"]["analyst"]["error"] == "empty completion"


def test_failed_reports_do_not_inflate_source_count():
    before = queries.report_stats()["sources_analyzed"]
    report_id = queries.create_report("Failed source-count regression")
    try:
        queries.update_report(
            report_id, status="failed",
            researcher_output={"dataset": {"verified_sources": [
                {"id": "L01"}, {"id": "L02"}, {"id": "L03"}]}})
        after = queries.report_stats()["sources_analyzed"]
        assert after == before
    finally:
        queries.delete_report(report_id)


def test_frontend_has_terminal_failed_mission_state():
    root = Path(__file__).resolve().parents[1]
    js = (root / "app" / "web" / "app.js").read_text(encoding="utf-8")
    css = (root / "app" / "web" / "app.css").read_text(encoding="utf-8")
    assert "agent_failed" in js
    assert "pipeline stopped" in js
    assert "Reports completed" in js
    assert ".agent-row.failed" in css
