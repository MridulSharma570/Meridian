"""Shared agent runtime: prompts, JSON repair, telemetry, failure isolation.

Two modes:

* **Verified (default)** — every agent must reach a configured provider API.
  A missing key, failed call or unusable response is an error: Meridian never
  manufactures an answer from templates. See :mod:`app.api.answer_policy`.
* **Sample** (``MERIDIAN_SAMPLE_MODE=1``) — the legacy deterministic engine
  runs and an LLM may optionally enrich it. Offline UI/testing use only.
"""
from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Optional, Tuple

from app.api import answer_policy
from app.api.llm_router import call_llm, effective_slot, is_configured
from app.config import settings
from app.database import queries

logger = logging.getLogger("meridian.agents")

_SYSTEM_PREFIX = (
    "You are a specialist agent inside Meridian, an enterprise market-intelligence "
    "platform. Be rigorous, quantitative, concise and neutral. Never invent a "
    "citation. Return only valid JSON when JSON is requested — no markdown fences, "
    "no commentary before or after the JSON."
)

_STRICT_RULES = (
    " GROUNDING RULES (mandatory): the only acceptable evidence is the list of "
    "VERIFIED SOURCES in the user message. Never invent a figure, publisher, URL, "
    "date, market size, company share or citation. Never reuse numbers from the "
    "template/scaffold as if they were measured facts. If the evidence cannot "
    "support a claim, write 'not available' or state the limitation explicitly. "
    "Cite real source ids like [L01] where they genuinely apply."
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
    """Template method: verified LLM in production, sample engine only when enabled."""

    name: str = "base"
    slot: str = "researcher"
    icon: str = "◆"
    description: str = ""
    expect_json: bool = True
    strict_max_tokens: int = 2400
    # Text fields the LLM is allowed to replace wholesale in verified mode.
    verified_fields: Tuple[str, ...] = ()

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

    # -- verified-mode helpers ---------------------------------------------- #
    def strict_prompt(self, ctx: Dict[str, Any], scaffold: Dict[str, Any]) -> str:
        """Build an evidence-grounded prompt; never ask the model to invent."""
        dataset = ctx.get("dataset", {}) or {}
        sources = dataset.get("verified_sources") or []
        return (
            f"You are Meridian's {self.name} agent. Complete the TASK below for "
            f"the research query {compact(ctx.get('query', ''), 300)} "
            f"(region: {ctx.get('region', 'Global')}, period: {ctx.get('period', '3Y')}).\n\n"
            "CRITICAL: any number, competitor share, headline or 'source' in the "
            "TASK text came from a placeholder generator and is FABRICATED. Do not "
            "restate, quote or cite it as fact. Use ONLY the VERIFIED SOURCES. "
            "Where evidence is missing, say 'not available' instead of guessing. "
            "Return only valid JSON with the keys the TASK requests.\n\n"
            f"VERIFIED SOURCES (cite these ids only):\n{compact(sources, 3200)}\n\n"
            f"TASK:\n{self.llm_prompt(ctx)}\n"
        )

    def strict_merge(self, local: Dict[str, Any], parsed: Any) -> Dict[str, Any]:
        """LLM text is authoritative; structural/chart keys keep their shape."""
        merged = self.merge(local, parsed)
        if isinstance(parsed, dict):
            for key in self.verified_fields:
                value = parsed.get(key)
                if value in (None, "", [], {}):
                    continue
                if key in merged and isinstance(merged[key], type(value)):
                    merged[key] = value
        return merged

    # -- public API ---------------------------------------------------------- #
    def run(self, ctx: Dict[str, Any]) -> AgentResult:
        t0 = time.perf_counter()
        strict = answer_policy.strict_mode()
        data: Dict[str, Any] = {}
        warning = ""
        try:
            data = self.local_run(ctx)
        except answer_policy.AnswerUnavailable:
            raise                              # never swallow the evidence gate
        except Exception as exc:
            if strict:
                raise answer_policy.AnswerUnavailable(
                    f"The {self.name} agent could not prepare a verified context: {exc}",
                    "Check live data connectors in Settings; Meridian will not guess.",
                    "context_failed") from exc
            logger.exception("Local engine failed in %s", self.name)
            data = {"error": str(exc), "fallback": True}
            warning = f"Local engine recovered from: {exc}"

        result = AgentResult(agent=self.name, ok=True, data=data, warning=warning)
        # Give prompt builders access to this agent's own freshly computed output.
        llm_ctx = dict(ctx)
        llm_ctx[self.name] = data
        llm_ctx["self"] = data

        if strict:
            answer_policy.require_api(f"{self.name} agent")
            self.emit({"type": "agent_llm", "agent": self.name, "status": "calling-provider"})
            prompt = self.strict_prompt(llm_ctx, data)
            try:
                response = call_llm(
                    effective_slot(self.slot), _SYSTEM_PREFIX + _STRICT_RULES, prompt,
                    max_tokens=self.strict_max_tokens, temperature=0.25,
                    json_mode=self.expect_json,
                    timeout=settings.agent_timeout_s,
                )
            except Exception as exc:
                raise answer_policy.AnswerUnavailable(
                    f"The configured provider could not complete the {self.name} "
                    f"step: {exc}",
                    "Check the key, model and quota in Settings → API Keys. "
                    "Meridian will not substitute a template answer.",
                    "provider_failed") from exc
            parsed = extract_json(response["text"]) if self.expect_json else response["text"]
            if not parsed:
                raise answer_policy.AnswerUnavailable(
                    f"{response['provider']} returned unusable output for the "
                    f"{self.name} step.",
                    "Try a different model in Settings → API Keys.",
                    "unusable_output")
            result.data = self.strict_merge(data, parsed)
            result.source = "llm"
            result.provider = response["provider"]
            result.model = response["model"]
            result.tokens_in = response["input_tokens"]
            result.tokens_out = response["output_tokens"]
            result.data["verified_answer"] = True
            result.data["answer_model"] = response["model"]
            result.warning = ""
        elif is_configured(self.slot) and self.llm_prompt(llm_ctx):
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
                    f"Provider skipped ({exc}); sample engine completed the task"
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
