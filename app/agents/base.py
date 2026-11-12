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
from app.api.key_manager import get_credentials
from app.api.llm_router import (LLMError, call_llm, configured_slots,
                                effective_slot, is_configured)
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


def _close_json_fragment(fragment: str) -> str:
    """Close strings/containers left open by a token-truncated response."""
    stack: list[str] = []
    in_string = False
    escaped = False
    for ch in fragment:
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "{":
            stack.append("}")
        elif ch == "[":
            stack.append("]")
        elif ch in ("}", "]"):
            if stack and stack[-1] == ch:
                stack.pop()
            else:
                return fragment
    candidate = fragment.rstrip()
    if not in_string and candidate.endswith(","):
        candidate = candidate[:-1].rstrip()
    if in_string:
        candidate += '"'
    return candidate + "".join(reversed(stack))


def extract_json(text: str) -> Optional[Any]:
    """Best-effort JSON extraction from an LLM response.

    Free models commonly wrap JSON in prose/fences or stop mid-object when
    their output budget runs out. A complete embedded object is decoded
    first; a truncated object is then closed (dropping only an incomplete
    trailing property/item if necessary). This never invents values — every
    retained token came from the provider — and agent-level key validation
    still decides whether the result is usable.
    """
    if not text:
        return None
    cleaned = text.strip().lstrip("\ufeff")
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.I)
        cleaned = re.sub(r"\s*```$", "", cleaned).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    decoder = json.JSONDecoder()
    starts = [m.start() for m in re.finditer(r"[\[{]", cleaned)]
    for start in starts[:12]:
        fragment = cleaned[start:]
        try:
            value, _ = decoder.raw_decode(fragment)
            return value
        except json.JSONDecodeError:
            pass
        candidate = _close_json_fragment(fragment)
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass
        # If the response stopped in the middle of a property/item, retry
        # with progressively earlier complete comma boundaries.
        search = fragment
        for _ in range(20):
            comma = search.rfind(",")
            if comma <= 0:
                break
            search = search[:comma]
            try:
                return json.loads(_close_json_fragment(search))
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
    strict_max_tokens: int = 3200
    strict_attempts: int = 3
    strict_retry_guidance: str = (
        "Keep every prose string under 25 words and use no more than 3 items "
        "per array unless the task explicitly requires more.")
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

    def _has_verified_content(self, parsed: Any) -> bool:
        """Reject technically-valid JSON that contains no agent answer."""
        if not isinstance(parsed, dict) or not parsed:
            return False
        if not self.verified_fields:
            return True
        return any(parsed.get(key) not in (None, "", [], {})
                   for key in self.verified_fields)

    def _strict_slots(self) -> list[str]:
        # Respect the provider assigned to this agent. ``effective_slot``
        # already borrows a configured slot when this agent has none; it
        # would be surprising (and potentially billable) for a retry to jump
        # to a different provider the user assigned to another agent.
        return [effective_slot(self.slot)]

    def _free_fallback_slots(self, primary: str) -> list[str]:
        """Other configured slots on free-tier providers (never paid ones).

        Used only when the assigned provider is rate-limited: a free Groq /
        Gemini / Cerebras key the user already saved can legitimately rescue
        the step, while silently switching to a paid provider could bill
        them without consent.
        """
        fallbacks: list[str] = []
        try:
            available = configured_slots()
        except Exception:
            available = []
        for slot in available:
            if slot == primary or slot in fallbacks:
                continue
            creds = get_credentials(slot)
            spec = (creds or {}).get("spec")
            if spec is not None and getattr(spec, "tier", "") == "free":
                fallbacks.append(slot)
        return fallbacks

    def _strict_retry_prompt(self, prompt: str, failure: str, attempt: int) -> str:
        return (
            f"RETRY {attempt}: the previous provider response was unusable "
            f"({failure}). Return exactly ONE complete, valid JSON object and "
            "nothing else — no markdown fences, commentary or partial object. "
            "Finish every brace before stopping. If evidence is missing, "
            f"write 'not available'. {self.strict_retry_guidance}\n\n"
            f"ORIGINAL TASK:\n{prompt}")

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
            slots = self._strict_slots()
            bad_models: list[str] = []
            attempts_used = 0
            tokens_in = tokens_out = 0
            last_failure = "the provider returned no usable output"
            last_provider = "The configured provider"
            last_status = 0
            last_category = ""
            completed = False

            for attempt in range(1, max(1, self.strict_attempts) + 1):
                attempts_used = attempt
                # Repairs stay on the agent's assigned slot; OpenRouter auto
                # can still move to another :free model inside the router.
                # The one exception: if the assigned provider is rate-limited,
                # the final attempt may use another free-tier provider the
                # user has configured — never a paid one.
                slot = slots[0]
                if attempt >= 3 and (last_status == 429 or
                                     last_category == "rate_limit"):
                    free_fallbacks = self._free_fallback_slots(slots[0])
                    if free_fallbacks:
                        slot = free_fallbacks[0]
                attempt_prompt = (prompt if attempt == 1 else
                                  self._strict_retry_prompt(prompt, last_failure, attempt))
                try:
                    response = call_llm(
                        slot, _SYSTEM_PREFIX + _STRICT_RULES, attempt_prompt,
                        max_tokens=self.strict_max_tokens, temperature=0.25,
                        json_mode=self.expect_json,
                        timeout=settings.agent_timeout_s,
                        avoid_models=bad_models,
                    )
                except Exception as exc:
                    last_failure = str(exc)
                    if isinstance(exc, LLMError):
                        last_status = exc.status or 0
                        last_category = exc.category or ""
                    # Auth and billing gates will not heal by repeating the
                    # same request; fail fast with the router's explanation.
                    non_retryable = isinstance(exc, LLMError) and (
                        exc.status in {401, 402, 403} or exc.category in {
                            "authentication", "openrouter_credit_gate"})
                    if attempt < self.strict_attempts and not non_retryable:
                        self.emit({
                            "type": "agent_retry", "agent": self.name,
                            "attempt": attempt + 1,
                            "message": (f"{self.name} provider attempt failed; "
                                        "retrying with a repaired request"),
                        })
                        continue
                    raise answer_policy.AnswerUnavailable(
                        f"The configured provider could not complete the {self.name} "
                        f"step after {attempt} attempt(s): {exc}",
                        "Check the key, model and quota in Settings → API Keys. "
                        "Meridian will not substitute a template answer.",
                        "provider_failed") from exc

                tokens_in += int(response.get("input_tokens") or 0)
                tokens_out += int(response.get("output_tokens") or 0)
                last_provider = str(response.get("provider") or last_provider)
                parsed = (extract_json(response.get("text") or "")
                          if self.expect_json else (response.get("text") or "").strip())
                failure = ""
                if self.expect_json:
                    if not isinstance(parsed, dict):
                        failure = "it did not return a JSON object"
                    elif not self._has_verified_content(parsed):
                        failure = "the JSON contained none of the requested fields"
                elif not parsed:
                    failure = "it returned empty text"

                if not failure:
                    try:
                        result.data = self.strict_merge(data, parsed)
                    except answer_policy.AnswerUnavailable as exc:
                        if exc.reason != "unusable_output":
                            raise
                        failure = str(exc)
                    else:
                        completed = True
                        result.source = "llm"
                        result.provider = response["provider"]
                        result.model = response["model"]
                        result.tokens_in = tokens_in
                        result.tokens_out = tokens_out
                        result.data["verified_answer"] = True
                        result.data["answer_model"] = response["model"]
                        result.data["provider_attempts"] = attempts_used
                        result.warning = ""
                        break

                model = str(response.get("model") or "").strip()
                if model and model not in bad_models:
                    bad_models.append(model)
                last_status = 0
                last_category = ""
                truncated = bool(response.get("completion_truncated"))
                last_failure = (
                    "the output was truncated before the JSON finished"
                    if truncated and self.expect_json else failure)
                if attempt < self.strict_attempts:
                    self.emit({
                        "type": "agent_retry", "agent": self.name,
                        "attempt": attempt + 1,
                        "message": (f"{last_provider} returned unusable output for "
                                    f"{self.name}; retrying with a shorter, "
                                    "strict JSON request"),
                    })

            if not completed:
                raise answer_policy.AnswerUnavailable(
                    f"{last_provider} returned unusable output for the {self.name} "
                    f"step after {attempts_used} attempts: {last_failure}.",
                    "Try a different model in Settings → API Keys. Meridian will "
                    "not substitute a template answer.",
                    "unusable_output")
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
