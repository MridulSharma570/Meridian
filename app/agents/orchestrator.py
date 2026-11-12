"""LangGraph-style orchestration of the seven Meridian agents.

Dependency-free implementation of a typed state graph:

    researcher ──▶ analyst ──┬──▶ writer ────────┐
                             ├──▶ forecast ─────┼──▶ (barrier) ──▶ translator
                             └──▶ factchecker ──┘
                   chat agent: on-demand branch (follow-up questions)

Nodes share an immutable-ish state dict, fan out over a thread pool, and each
node is wrapped in an isolation boundary: a failing agent is replaced by a
safe fallback so the remaining agents always complete.
"""
from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable, Dict, List, Optional

from app.agents.analyst import AnalystAgent
from app.agents.base import AgentResult
from app.agents.chat_agent import ChatAgent
from app.agents.factchecker import FactCheckerAgent
from app.agents.forecast_agent import ForecastAgent
from app.agents.researcher import ResearcherAgent
from app.agents.translator import TranslatorAgent
from app.agents.writer import WriterAgent
from app.api.answer_policy import AnswerUnavailable
from app.config import AGENT_SLOTS, settings

logger = logging.getLogger("meridian.orchestrator")

PIPELINE: List[Dict[str, Any]] = [
    {"stage": 1, "agents": ["researcher"], "label": "Signal collection"},
    {"stage": 2, "agents": ["analyst"], "label": "Strategic analysis"},
    {"stage": 3, "agents": ["writer", "forecast", "factchecker"],
     "label": "Report, forecast & verification"},
    {"stage": 4, "agents": ["chat"], "label": "Follow-up intelligence ready"},
    {"stage": 5, "agents": ["translator"], "label": "Localisation"},
]

AGENT_META = {s[0]: {"name": s[1], "icon": s[2], "description": s[3]} for s in AGENT_SLOTS}
AGENT_CLASSES = {
    "researcher": ResearcherAgent, "analyst": AnalystAgent, "writer": WriterAgent,
    "chat": ChatAgent, "forecast": ForecastAgent, "factchecker": FactCheckerAgent,
    "translator": TranslatorAgent,
}


class Orchestrator:
    """Executes the agent graph and emits mission-control events."""

    def __init__(self, report_id: str = "", emit: Optional[Callable[[dict], None]] = None):
        self.report_id = report_id
        self.emit = emit or (lambda _e: None)
        self.events: List[dict] = []
        self.results: List[AgentResult] = []

    def _push(self, event: dict) -> None:
        event = dict(event)
        event.setdefault("ts", time.time())
        self.events.append(event)
        try:
            self.emit(event)
        except Exception:
            pass

    def _run_agent(self, name: str, state: Dict[str, Any]) -> AgentResult:
        meta = AGENT_META[name]
        self._push({"type": "agent_start", "agent": name, "name": meta["name"],
                    "icon": meta["icon"], "status": "working"})
        started = time.perf_counter()
        try:
            agent = AGENT_CLASSES[name](self.report_id, self._push)
            result = agent.run(state)
        except AnswerUnavailable:
            # Verified mode must fail closed. Never replace a missing/failed
            # API or missing evidence with a plausible template result.
            raise
        except Exception as exc:
            logger.exception("Agent %s failed hard; using safe fallback", name)
            result = AgentResult(agent=name, ok=False, data={"fallback": True},
                                 warning=f"{name} recovered from a critical error: {exc}")
            result.data["_meta"] = {"agent": name, "ok": False, "source": "fallback",
                                    "warning": result.warning, "latency_ms": 0,
                                    "provider": "recovery", "model": "n/a", "slot": name}
        self.results.append(result)
        self._push({"type": "agent_done", "agent": name, "name": meta["name"],
                    "status": "done" if result.ok else "recovered",
                    "elapsed_ms": int((time.perf_counter() - started) * 1000),
                    "provider": result.provider,
                    "warning": result.warning})
        return result

    def run(self, query: str, *, region: str = "Global", period: str = "3Y",
            language: str = "en") -> Dict[str, Any]:
        state: Dict[str, Any] = {
            "query": query, "region": region, "period": period,
            "language": language, "report_id": self.report_id,
        }
        total = 7
        done = 0
        self._push({"type": "start", "query": query, "region": region,
                    "period": period, "total_agents": total})

        def progress(stage: int) -> None:
            self._push({"type": "progress", "stage": stage, "completed": done,
                        "total": total, "percent": round(done / total * 100)})

        # Stage 1 — research
        res = self._run_agent("researcher", state)
        state["researcher"] = res.data
        state.setdefault("dataset", res.data.get("dataset", {}))
        done += 1
        progress(1)

        # Stage 2 — analysis
        res = self._run_agent("analyst", state)
        state["analyst"] = res.data
        done += 1
        progress(2)

        # Stage 3 — parallel fan-out
        parallel = ("writer", "forecast", "factchecker")
        with ThreadPoolExecutor(max_workers=3) as pool:
            futures = {pool.submit(self._run_agent, n, dict(state)): n for n in parallel}
            for fut in as_completed(futures):
                name = futures[fut]
                try:
                    state[name] = fut.result().data
                except AnswerUnavailable:
                    raise
                except Exception as exc:
                    state[name] = {"fallback": True, "error": str(exc)}
                done += 1
                progress(3)
        # Forecast needs its own output in ctx for LLM enrichment; give it a second,
        # cheap narrative pass only when a provider is configured (handled in merge).
        state["agent_meta"] = [r.as_dict() for r in self.results]

        # Stage 4 — chat agent readiness (no generation cost)
        self._push({"type": "agent_start", "agent": "chat", "name": "Chat Agent",
                    "icon": "💬", "status": "working"})
        time.sleep(0.05)
        state["chat"] = {"ready": True, "suggestions": ChatAgent.SUGGESTIONS}
        self._push({"type": "agent_done", "agent": "chat", "name": "Chat Agent",
                    "status": "done", "elapsed_ms": 50,
                    "provider": "Meridian Local Engine", "warning": ""})
        done += 1
        progress(4)

        # Stage 5 — translation (conditional edge)
        self._push({"type": "agent_start", "agent": "translator", "name": "Translator",
                    "icon": "🌐", "status": "working"})
        if language != "en":
            translation = TranslatorAgent(self.report_id, self._push).translate(
                state.get("writer", {}).get("markdown", ""), language, state, self.report_id)
        else:
            translation = {"language": "en", "native": "English", "content": None,
                           "method": "not-requested", "note": ""}
        state["translation"] = translation
        self._push({"type": "agent_done", "agent": "translator", "name": "Translator",
                    "status": "done", "elapsed_ms": 10,
                    "provider": translation["method"], "warning": ""})
        done += 1
        progress(5)

        state["reliability_score"] = state.get("factchecker", {}).get("reliability_score", 0)
        state["final_report"] = state.get("writer", {}).get("markdown", "")
        self._push({"type": "complete", "report_id": self.report_id,
                    "reliability_score": state["reliability_score"], "percent": 100})
        return state


def build_orchestrator(report_id: str, emit: Callable[[dict], None]) -> Orchestrator:
    return Orchestrator(report_id, emit)
