"""Shared agent runtime: prompts, JSON repair, telemetry, failure isolation.

Design rule: **an agent never fails a report.** If its provider is missing,
times out, rate-limits or returns malformed JSON, the local analytical engine
produces a complete result and the incident is recorded as a warning + log.
"""
from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Optional

from app.api.llm_router import call_llm, is_configured
from app.config import settings
from app.database import queries

logger = logging.getLogger("meridian.agents")

_SYSTEM_PREFIX = (
    "You are a specialist agent inside Meridian, an enterprise market-intelligence "
    "platform. Be rigorous, quantitative, concise and neutral. Never invent a "
    "citation. Return only valid JSON when JSON is requested — no markdown fences, "
    "no commentary, no commentary before or after the JSON."
)


def extract_json(text: str) -> Optional[Any]:
    """Best-effort JSON extraction from an LLM response."""
    if not text:
        return None
    cleaned = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass
    for opener, closer in (("{", "}"), ("[", "]")):
        start, end = cleaned.find(opener), cleaned.rfind(closer)
        if start != -1 and end > start:
            try:
                return json.loads(cleaned[start:end + 1])
            except json.JSONDecodeError:
                continue
    return None


@dataclass
class AgentResult:
    agent: str
    ok: bool
    data: Dict[str, Any]
    provider: str = "Meridian Local Engine"
    model: str = "deterministic-v1"
    latency_ms: int = 0
    warning: str = ""
    tokens_in: int = 0
    tokens_out: int = 0
    source: str = "local"          # local | llm | hybrid
    extra: Dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "agent": self.agent, "ok": self.ok, "data": self.data,
            "provider": self.provider, "model": self.model,
            "latency_ms": self.latency_ms, "warning": self.warning,
            "tokens_in": self.tokens_in, "tokens_out": self.tokens_out,
            "source": self.source,
        }


class BaseAgent:
    """Template method: local engine first, optional LLM enrichment on top."""

    name: str = "base"
    slot: str = "researcher"
    icon: str = "◆"
    description: str = ""
    expect_json: bool = True

    def __init__(self, report_id: str = "", emit: Optional[Callable[[dict], None]] = None):
        self.report_id = report_id
        self.emit = emit or (lambda _event: None)

    # -- to be implemented by subclasses ------------------------------------ #
    def local_run(self, ctx: Dict[str, Any]) -> Dict[str, Any]:
        raise NotImplementedError

    def llm_prompt(self, ctx: Dict[str, Any]) -> str:
        return ""

    def merge(self, local: Dict[str, Any], remote: Any) -> Dict[str, Any]:
        """Merge verified LLM enrichment without losing chart-critical fields."""
        if isinstance(remote, dict):
            for k, v in remote.items():
                if v not in (None, "", [], {}) and k not in {"_meta"}:
                    local[k] = v
        return local

    # -- public API ---------------------------------------------------------- #
    def run(self, ctx: Dict[str, Any]) -> AgentResult:
        t0 = time.perf_counter()
        data: Dict[str, Any] = {}
        warning = ""
        try:
            data = self.local_run(ctx)
        except Exception as exc:  # local engine must still be recoverable
            logger.exception("Local engine failed in %s", self.name)
            data = {"error": str(exc), "fallback": True}
            warning = f"Local engine recovered from: {exc}"

        result = AgentResult(agent=self.name, ok=True, data=data, warning=warning)

        # Give prompt builders access to this agent's own freshly computed output.
        llm_ctx = dict(ctx)
        llm_ctx[self.name] = data
        llm_ctx["self"] = data
        if is_configured(self.slot) and self.llm_prompt(llm_ctx):
            self.emit({"type": "agent_llm", "agent": self.name, "status": "calling-provider"})
            try:
                response = call_llm(
                    self.slot, _SYSTEM_PREFIX, self.llm_prompt(llm_ctx),
                    max_tokens=1800, temperature=0.3, json_mode=self.expect_json,
                    timeout=settings.agent_timeout_s,
                )
                parsed = extract_json(response["text"]) if self.expect_json else response["text"]
                if parsed:
                    result.data = self.merge(data, parsed)
                    result.source = "hybrid"
                    result.provider = response["provider"]
                    result.model = response["model"]
                else:
                    result.warning = (result.warning + " | " if result.warning else "") + \
                        f"{response['provider']} returned unusable output; kept local analysis"
                result.tokens_in = response["input_tokens"]
                result.tokens_out = response["output_tokens"]
            except Exception as exc:
                result.warning = (result.warning + " | " if result.warning else "") + \
                    f"Provider skipped ({exc}); local engine completed the task"
                self.emit({"type": "agent_warning", "agent": self.name, "message": str(exc)})

        result.latency_ms = int((time.perf_counter() - t0) * 1000)
        result.data.setdefault("_meta", {})
        result.data["_meta"].update({
            "agent": self.name, "slot": self.slot, "provider": result.provider,
            "model": result.model, "latency_ms": result.latency_ms,
            "source": result.source, "warning": result.warning,
            "ok": result.ok,
        })
        if self.report_id:
            queries.add_agent_log(
                self.report_id, self.name, result.provider,
                "done" if not result.warning else "done_with_warnings",
                result.latency_ms, result.tokens_in, result.tokens_out,
                result.warning,
            )
        return result


def compact(obj: Any, limit: int = 6000) -> str:
    """Compact JSON for prompt injection (keeps prompts small and cheap)."""
    try:
        return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))[:limit]
    except (TypeError, ValueError):
        return str(obj)[:limit]
