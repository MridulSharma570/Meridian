"""Agent pipeline, failure isolation, orchestration and translation tests."""
from __future__ import annotations

import pytest

from app.agents.analyst import AnalystAgent
from app.agents.base import extract_json
from app.agents.chat_agent import ChatAgent
from app.agents.factchecker import FactCheckerAgent
from app.agents.forecast_agent import ForecastAgent
from app.agents.orchestrator import Orchestrator
from app.agents.researcher import ResearcherAgent
from app.agents.translator import TranslatorAgent
from app.agents.writer import WriterAgent
from app.data_sources.demo_data import (build_comparison, build_market_dataset,
                                        split_comparison)


@pytest.fixture(scope="module")
def ctx():
    dataset = build_market_dataset("Tesla vs BYD electric vehicles", "India", "5Y")
    return {"query": "Tesla vs BYD electric vehicles", "region": "India",
            "period": "5Y", "dataset": dataset}


def test_deterministic_dataset(ctx):
    d = ctx["dataset"]
    assert d["market_size_usd_b"] > 0 and d["cagr_pct"] > 0
    assert len(d["history"]) >= 5 and len(d["sources"]) == 12
    assert abs(sum(c["share"] for c in d["competitors"]) - 100) < 0.2
    assert build_market_dataset("Tesla vs BYD electric vehicles", "India", "5Y") == d
    assert split_comparison("Tesla vs BYD") == ("Tesla", "Byd")


def test_researcher_and_analyst(ctx):
    r = ResearcherAgent().run(dict(ctx)).data
    assert r["source_count"] >= 12 and r["dataset"]["region"] == "India"
    state = dict(ctx, researcher=r, dataset=r["dataset"])
    a = AnalystAgent().run(state).data
    assert set(a["swot"]) == {"Strengths", "Weaknesses", "Opportunities", "Threats"}
    assert len(a["pestle"]) == 6 and len(a["porter"]) == 5
    assert a["sizing"]["TAM (USD B)"] > a["sizing"]["SAM (USD B)"] > a["sizing"]["SOM (USD B)"]


def test_writer_forecast_and_factchecker(ctx):
    state = dict(ctx)
    state["researcher"] = ResearcherAgent().run(state).data
    state["analyst"] = AnalystAgent().run(state).data
    w = WriterAgent().run(state).data
    assert "Executive Summary" in w["markdown"] and "Sources" in w["markdown"]
    assert len(w["sections"]) >= 8 and w["word_count"] > 500
    f = ForecastAgent().run(state).data
    assert len(f["series"]) == 12
    assert all(x["pessimistic"] <= x["base"] <= x["optimistic"] for x in f["series"])
    fc = FactCheckerAgent().run(state).data
    assert 0 <= fc["reliability_score"] <= 100
    assert all(len(c["sources"]) >= 1 for c in fc["claims"])
    assert fc["verified_count"] + fc["partial_count"] + fc["flagged_count"] == len(fc["claims"])


def test_chat_is_grounded_and_never_errors(ctx):
    state = dict(ctx)
    state["researcher"] = ResearcherAgent().run(state).data
    state["analyst"] = AnalystAgent().run(state).data
    for q in ("What about the rural market?", "Compare the top competitors",
              "What are the biggest risks?", "Which sources support the sizing?",
              "hello", "an entirely novel question about nothing"):
        ans = ChatAgent().answer(state, q)
        assert len(ans["answer"]) > 60 and "Traceback" not in ans["answer"]


def test_translator_structure_preserved(ctx):
    state = dict(ctx)
    state["researcher"] = ResearcherAgent().run(state).data
    state["analyst"] = AnalystAgent().run(state).data
    state["writer"] = WriterAgent().run(state).data
    for lang in ("hi", "es", "ja", "ar", "pa", "de"):
        out = TranslatorAgent().translate(state["writer"]["markdown"], lang, state)
        assert out["language"] == lang
        assert "## " in out["content"] and "| " in out["content"]
        assert len(out["content"]) > len(state["writer"]["markdown"]) * 0.8
    assert TranslatorAgent().translate("# Hi", "en", state)["method"] == "original"


def test_json_repair():
    assert extract_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert extract_json('noise {"b": [1,2]} trailing') == {"b": [1, 2]}
    assert extract_json("not json at all") is None


def test_orchestrator_all_agents_complete():
    events = []
    o = Orchestrator("test-report-id", events.append)
    state = o.run("Global AI platforms market", region="Global", period="3Y", language="en")
    done = [e["agent"] for e in events if e["type"] == "agent_done"]
    assert set(done) == {"researcher", "analyst", "writer", "forecast",
                         "factchecker", "chat", "translator"}
    assert state["final_report"] and state["reliability_score"] > 0
    assert any(e["type"] == "complete" for e in events)


def test_comparison_engine():
    c = build_comparison("Tesla", "BYD", "Global")
    assert len(c["metrics"]) == 5 and "verdict" in c
    assert c["dataset_a"]["history"] and c["dataset_b"]["history"]
