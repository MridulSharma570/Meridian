"""LLM router — one normalised interface over 16 providers.

Every agent asks the router for its *own* slot. The router resolves the slot's
encrypted credentials, speaks the vendor's native wire format and returns
plain text. Failures are typed and never leak the API key into logs.

For ``openrouter_free`` the sentinel ``auto:best-free`` is resolved at call
time against OpenRouter's live free catalogue; see
:mod:`app.api.openrouter_auto`.
"""
from __future__ import annotations

import json
import logging
import re
import threading
import time
from contextlib import nullcontext
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Dict, Iterable, List, Optional, Set

import requests

from app.api import openrouter_auto
from app.api.key_manager import get_credentials, key_status
from app.api.providers import Provider, get_provider
from app.config import settings

logger = logging.getLogger("meridian.llm")

_SENSITIVE = re.compile(r"(sk-[A-Za-z0-9_\-]{6,}|AIza[A-Za-z0-9_\-]{6,}|gsk_[A-Za-z0-9_\-]{6,})")


class LLMError(RuntimeError):
    """Raised when a provider call fails. Message is always key-safe.

    The optional structured fields let Settings show one short, actionable
    explanation instead of dumping a provider's raw JSON response into a
    toast. ``str(error)`` remains safe to display anywhere.
    """

    def __init__(self, message: str, *, status: Optional[int] = None,
                 category: str = "provider_error", action: str = "",
                 provider_message: str = "", kind: str = "",
                 finish_reason: str = "", reasoning_tokens: int = 0,
                 completion_tokens: int = 0, retry_after_s: float = 0.0):
        super().__init__(message)
        self.status = status
        self.category = category
        self.action = action
        self.provider_message = provider_message
        self.retry_after_s = retry_after_s
        # Completion diagnostics are deliberately separate from HTTP status:
        # a provider can return HTTP 200 with no usable answer at all.
        self.kind = kind or category
        self.finish_reason = finish_reason
        self.reasoning_tokens = reasoning_tokens
        self.completion_tokens = completion_tokens

    def as_dict(self) -> Dict[str, Any]:
        return {
            "error": str(self), "status": self.status,
            "category": self.category, "action": self.action,
            "provider_message": self.provider_message or None,
        }


def _safe(text: str) -> str:
    return _SENSITIVE.sub("<redacted>", str(text))[:800]


# --------------------------------------------------------------------------- #
# OpenRouter rate-limit discipline
#
# Free ``:free`` variants are capped per minute (and per day) at the account
# level, so the worst response to a 429 is what Meridian used to do: retry
# instantly from several agents at once and trip the limit again. Instead,
# a 429 starts a shared cooldown — later OpenRouter calls wait out the
# window (honouring Retry-After when supplied) — and OpenRouter requests
# are serialised so parallel pipeline stages cannot burst the cap.
# --------------------------------------------------------------------------- #
_rate_limit_lock = threading.Lock()
_rate_limit_until = 0.0
_or_request_lock = threading.Lock()
_MAX_COOLDOWN_WAIT_S = 120.0


def _is_openrouter(p: Provider) -> bool:
    return p.key.startswith("openrouter")


def _parse_retry_after(headers: Any) -> float:
    """Seconds from a Retry-After header (delta-seconds or HTTP-date)."""
    try:
        raw = headers.get("Retry-After") or headers.get("retry-after")
    except AttributeError:
        return 0.0
    if not raw:
        return 0.0
    try:
        return max(0.0, float(raw))
    except (TypeError, ValueError):
        pass
    try:
        when = parsedate_to_datetime(str(raw))
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
        return max(0.0, (when - datetime.now(timezone.utc)).total_seconds())
    except (TypeError, ValueError):
        return 0.0


def _note_rate_limit(p: Provider, retry_after_s: float = 0.0) -> None:
    global _rate_limit_until
    if not _is_openrouter(p):
        return
    wait = retry_after_s if retry_after_s > 0 else settings.openrouter_429_cooldown_s
    with _rate_limit_lock:
        _rate_limit_until = max(_rate_limit_until, time.time() + max(0.0, wait))


def _wait_out_rate_limit(p: Provider) -> None:
    """Block until the shared OpenRouter cooldown has expired (bounded)."""
    if not _is_openrouter(p):
        return
    with _rate_limit_lock:
        remaining = _rate_limit_until - time.time()
    wait = min(max(0.0, remaining), _MAX_COOLDOWN_WAIT_S)
    if wait > 0:
        logger.info("OpenRouter rate-limit cooldown: waiting %.0fs before next call", wait)
        time.sleep(wait)


def _reset_rate_limit_state() -> None:
    """Test hook: clear the shared cooldown."""
    global _rate_limit_until
    with _rate_limit_lock:
        _rate_limit_until = 0.0


def resolve_slot(slot: str) -> str:
    """Translator inherits the Writer slot when it has no key of its own."""
    if slot == "translator":
        if get_credentials("translator"):
            return "translator"
        return "writer"
    return slot


def is_configured(slot: str) -> bool:
    return get_credentials(resolve_slot(slot)) is not None


def configured_slots() -> List[str]:
    try:
        return [k["slot"] for k in key_status() if k["configured"] and k["is_active"]]
    except Exception:
        # Health checks may run before the key table exists.
        return []


def effective_slot(slot: str) -> str:
    """Pick a real configured API slot for an agent.

    Users often save a single key and use "apply to all" later. In verified
    mode an agent must reach a provider, so an unconfigured slot borrows any
    active configured slot instead of silently falling back to templates.
    """
    resolved = resolve_slot(slot)
    if is_configured(resolved):
        return resolved
    slots = configured_slots()
    return slots[0] if slots else resolved


def _endpoint(p: Provider) -> str:
    base = p.base_url.rstrip("/")
    if p.api_style == "anthropic":
        return f"{base}/messages"
    if p.api_style == "cohere":
        return f"{base}/chat"
    if base.endswith("/v1") or base.endswith("/openai") or "/v1/" in base:
        return f"{base}/chat/completions"
    return f"{base}/v1/chat/completions"


def _headers(p: Provider, key: str) -> Dict[str, str]:
    h = {"Content-Type": "application/json"}
    if p.api_style == "anthropic":
        h.update({"x-api-key": key, "anthropic-version": "2023-06-01"})
    elif not key:
        h.update({"Authorization": "Bearer local"})
    else:
        h.update({"Authorization": f"Bearer {key}"})
    if p.key.startswith("openrouter"):
        h["HTTP-Referer"] = "https://meridian.local"
        h["X-Title"] = "Meridian Market Intelligence"
    return h


def _payload(p: Provider, model: str, system: str, user: str,
             max_tokens: int, temperature: float, json_mode: bool,
             fallbacks: Optional[List[str]] = None,
             disable_reasoning: bool = False) -> Dict[str, Any]:
    if p.api_style == "anthropic":
        body: Dict[str, Any] = {
            "model": model, "max_tokens": max_tokens, "temperature": temperature,
            "system": system, "messages": [{"role": "user", "content": user}],
        }
        return body
    if p.api_style == "cohere":
        return {"model": model, "messages": [
            {"role": "system", "content": system}, {"role": "user", "content": user}],
            "max_tokens": max_tokens, "temperature": temperature}
    body = {
        "model": model, "temperature": temperature, "max_tokens": max_tokens,
        "messages": [{"role": "system", "content": system},
                     {"role": "user", "content": user}],
    }
    if json_mode and p.key not in {"perplexity", "huggingface"}:
        body["response_format"] = {"type": "json_object"}
    if disable_reasoning and p.key.startswith("openrouter"):
        # Some free OpenRouter models spend the entire completion budget on
        # hidden reasoning and return finish_reason="length" with no content.
        # This recovery variant asks the same model to answer directly. It is
        # only sent after that failure, because mandatory-reasoning endpoints
        # may reject it; the caller then fails over to another free model.
        body["reasoning"] = {"effort": "none", "exclude": True}
    if fallbacks:
        # OpenRouter's priority-ordered failover for /chat/completions. The
        # router only builds all-free chains, so a retry can never be billed.
        body["models"] = list(fallbacks)
    return body


def _content_text(content: Any) -> str:
    """Normalise the text-bearing shapes used by OpenAI-compatible APIs."""
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, dict):
        for key in ("text", "output_text", "content"):
            if isinstance(content.get(key), str):
                return content[key].strip()
        return ""
    if isinstance(content, list):
        parts: List[str] = []
        for part in content:
            if isinstance(part, str):
                parts.append(part)
            elif isinstance(part, dict):
                # Reasoning/refusal parts are not an answer, even when a
                # provider puts them in the same content array.
                if str(part.get("type") or "").lower() in {
                        "reasoning", "reasoning_content", "thinking", "refusal"}:
                    continue
                text = _content_text(part)
                if text:
                    parts.append(text)
        return "".join(parts).strip()
    return ""


def _reasoning_text(message: Dict[str, Any]) -> str:
    for key in ("reasoning", "reasoning_content", "thinking"):
        value = message.get(key)
        text = _content_text(value)
        if text:
            return text
    details = message.get("reasoning_details")
    if isinstance(details, list):
        return _content_text(details)
    return ""


def _usage_int(usage: Dict[str, Any], *keys: str) -> int:
    for key in keys:
        try:
            if usage.get(key) is not None:
                return int(usage[key])
        except (TypeError, ValueError):
            continue
    details = usage.get("completion_tokens_details")
    if isinstance(details, dict):
        return _usage_int(details, *keys)
    return 0


def _completion_error(p: Provider, *, finish_reason: str = "",
                      refusal: str = "", reasoning: str = "",
                      reasoning_tokens: int = 0,
                      completion_tokens: int = 0) -> LLMError:
    """Describe an HTTP-200 response that contains no usable answer."""
    action = ("Meridian will retry another configured/free model where one is "
              "available; otherwise try a model with a larger output limit in "
              "Settings → API Keys.")
    if refusal:
        kind = "refused"
        message = f"{p.label} refused to return a completion"
    elif finish_reason == "length":
        kind = "truncated"
        message = (f"{p.label} ran out of output budget before returning an "
                   "answer (finish_reason=length)")
    elif reasoning or reasoning_tokens:
        kind = "reasoning_only"
        message = (f"{p.label} returned reasoning without a final answer; "
                   "the output budget was exhausted before the response")
    else:
        kind = "empty"
        message = f"{p.label} returned an empty completion"
    return LLMError(message, status=502, category=f"completion_{kind}",
                    action=action, kind=kind, finish_reason=finish_reason,
                    reasoning_tokens=reasoning_tokens,
                    completion_tokens=completion_tokens)


def _extract_completion(p: Provider, data: Dict[str, Any]) -> tuple[str, Dict[str, Any]]:
    """Return completion text plus finish/usage diagnostics.

    Providers increasingly return HTTP 200 for reasoning-only, refused or
    token-truncated responses. Treating all of those as a generic empty string
    made a single free model look like a dead API key, so the distinction is
    preserved here and in :func:`call_llm`'s return value.
    """
    if not isinstance(data, dict):
        raise LLMError(f"Malformed response from {p.label}: expected an object")
    usage = data.get("usage") if isinstance(data.get("usage"), dict) else {}
    meta: Dict[str, Any] = {
        "finish_reason": "",
        "reasoning_tokens": _usage_int(usage, "reasoning_tokens"),
        "completion_tokens": _usage_int(
            usage, "completion_tokens", "output_tokens"),
        "truncated": False,
    }
    try:
        if p.api_style == "anthropic":
            text = _content_text(data.get("content", []))
            meta["finish_reason"] = str(data.get("stop_reason") or "")
            meta["truncated"] = meta["finish_reason"] == "max_tokens"
            if text:
                return text, meta
            raise _completion_error(
                p, finish_reason="length" if meta["truncated"] else meta["finish_reason"],
                reasoning_tokens=meta["reasoning_tokens"],
                completion_tokens=meta["completion_tokens"])
        if p.api_style == "cohere":
            msg = data.get("message", {}) if isinstance(data.get("message"), dict) else {}
            text = _content_text(msg.get("content"))
            meta["finish_reason"] = str(data.get("finish_reason") or "")
            meta["truncated"] = meta["finish_reason"].upper() == "MAX_TOKENS"
            if text:
                return text, meta
            raise _completion_error(
                p, finish_reason="length" if meta["truncated"] else meta["finish_reason"],
                reasoning=_reasoning_text(msg),
                reasoning_tokens=meta["reasoning_tokens"],
                completion_tokens=meta["completion_tokens"])

        choices = data.get("choices") or []
        if choices and isinstance(choices[0], dict):
            choice = choices[0]
            message = choice.get("message") if isinstance(choice.get("message"), dict) else {}
            # A few compatible gateways put the delta/text directly on choice.
            text = _content_text(message.get("content"))
            if not text:
                text = _content_text(choice.get("text") or choice.get("delta"))
            finish = str(choice.get("finish_reason") or
                         choice.get("finishReason") or "")
            meta["finish_reason"] = finish
            meta["truncated"] = finish == "length"
            if text:
                return text, meta
            refusal = _content_text(message.get("refusal"))
            raise _completion_error(
                p, finish_reason=finish, refusal=refusal,
                reasoning=_reasoning_text(message),
                reasoning_tokens=meta["reasoning_tokens"],
                completion_tokens=meta["completion_tokens"])
        text = _content_text(data.get("text"))
        if text:
            return text, meta
    except LLMError:
        raise
    except (AttributeError, TypeError, IndexError) as exc:
        raise LLMError(f"Malformed response from {p.label}: {_safe(exc)}") from exc
    raise _completion_error(p, reasoning_tokens=meta["reasoning_tokens"],
                            completion_tokens=meta["completion_tokens"])


def _extract(p: Provider, data: Dict[str, Any]) -> str:
    return _extract_completion(p, data)[0]


def _provider_error_payload(detail: Any) -> Dict[str, Any]:
    """Extract the useful fields from a provider error without exposing JSON."""
    if isinstance(detail, dict):
        payload = detail
    else:
        try:
            payload = json.loads(str(detail))
        except (TypeError, ValueError):
            return {}
    if not isinstance(payload, dict):
        return {}
    error = payload.get("error") if isinstance(payload.get("error"), dict) else payload
    if not isinstance(error, dict):
        return {}
    metadata = error.get("metadata") if isinstance(error.get("metadata"), dict) else {}
    return {
        "message": str(error.get("message") or "")[:240],
        "code": str(error.get("code") or payload.get("code") or ""),
        "limit_source": str(metadata.get("limit_source") or ""),
        "remedy_hint": str(metadata.get("remedy_hint") or "")[:240],
    }


def _clean_provider_message(message: str) -> str:
    """One-line provider wording, with credentials and JSON syntax removed."""
    text = _safe(message).replace("\n", " ").strip()
    text = re.sub(r"\s+", " ", text)
    return text[:180].rstrip(" .")


def _error_for_status(p: Provider, status: int, detail: Any) -> LLMError:
    """Translate an HTTP failure into a short cause + next step.

    Raw provider bodies are deliberately *not* included: OpenRouter returns
    nested billing JSON for HTTP 402, and rendering it verbatim made every
    Settings slot look broken in a different way. The parsed provider message
    is retained separately for diagnostics, capped and credential-redacted.
    """
    info = _provider_error_payload(detail)
    provider_message = _clean_provider_message(info.get("message", ""))
    limit_source = info.get("limit_source", "")
    is_or_free = p.key == "openrouter_free"

    if status == 402:
        if is_or_free and limit_source in {"openrouter_credits", "org_credits",
                                           "user_credits", "key_credits", ""}:
            title = "OpenRouter stopped this free request at a billing check (HTTP 402)"
            action = (
                "Meridian now sends only models whose IDs end in :free. Check that this "
                "key belongs to the intended OpenRouter account/organisation, remove or "
                "raise any per-key credit limit, and make sure the account balance is not "
                "negative. A :free model does not normally require buying credits; if "
                "OpenRouter still blocks this account, use a free Groq or Gemini key instead."
            )
            category = "openrouter_credit_gate"
        elif is_or_free:
            title = "OpenRouter rejected the request size or credit reservation (HTTP 402)"
            action = (
                "Retry with Auto — best free model (live). Meridian's connection test already "
                "uses a tiny prompt; if the same 402 persists, check the key's credit limit "
                "or use a free Groq or Gemini key."
            )
            category = "openrouter_request_limit"
        else:
            title = f"{p.label} requires payment or more credit (HTTP 402)"
            action = "Add credit to that provider account, raise the key's spending limit, or choose another provider."
            category = "payment_required"
        return LLMError(f"{title}. {action}", status=status, category=category,
                        action=action, provider_message=provider_message)

    if status in (401, 403):
        action = ("Check that the key was copied completely, belongs to this provider, "
                  "is active, and has access to the selected model.")
        return LLMError(f"{p.label} rejected this API key (HTTP {status}). {action}",
                        status=status, category="authentication", action=action,
                        provider_message=provider_message)
    if status == 429:
        if is_or_free:
            action = ("OpenRouter's free pool is rate-limited for now (free variants are "
                      "capped per minute and per day). Meridian automatically waits out "
                      "the limit window and retries; if this persists, the daily free "
                      "cap may be reached — wait, choose Auto — best free model, or use "
                      "a free Groq/Gemini key.")
        else:
            action = "The provider's rate limit or quota is exhausted. Wait, reduce usage, or choose another provider."
        return LLMError(f"{p.label} is rate-limited (HTTP 429). {action}",
                        status=status, category="rate_limit", action=action,
                        provider_message=provider_message)
    if status in (404, 410):
        action = ("That model is unavailable or retired. For OpenRouter (Free), choose "
                  "Auto — best free model (live); otherwise select a current model.")
        return LLMError(f"{p.label} could not find the selected model (HTTP {status}). {action}",
                        status=status, category="model_unavailable", action=action,
                        provider_message=provider_message)
    if status == 400:
        action = ("The provider rejected the request shape or parameters. Choose Auto — "
                  "best free model for OpenRouter (Free), or a standard model for this provider.")
        return LLMError(f"{p.label} rejected the request (HTTP 400). {action}",
                        status=status, category="bad_request", action=action,
                        provider_message=provider_message)
    if status >= 500:
        action = "The provider is temporarily unavailable. Wait briefly and test again, or use another configured provider."
        return LLMError(f"{p.label} is temporarily unavailable (HTTP {status}). {action}",
                        status=status, category="provider_unavailable", action=action,
                        provider_message=provider_message)

    action = "Check the selected provider and model, then test again."
    if provider_message:
        return LLMError(f"{p.label} HTTP {status}: {provider_message}. {action}",
                        status=status, category="provider_error", action=action,
                        provider_message=provider_message)
    return LLMError(f"{p.label} HTTP {status}. {action}", status=status,
                    category="provider_error", action=action,
                    provider_message=provider_message)


# Errors for which another *free* model may legitimately succeed. Auth errors
# and payments are deliberately excluded: retrying them would only waste quota.
_RETRYABLE = {400, 404, 408, 409, 410, 429, 500, 502, 503, 504}
_AUTO_ATTEMPTS = 3


def call_llm(slot: str, system: str, user: str, *, max_tokens: int = 1600,
             temperature: float = 0.35, json_mode: bool = False,
             timeout: Optional[float] = None,
             avoid_models: Optional[Iterable[str]] = None) -> Dict[str, Any]:
    """Execute one completion. Returns text plus usage telemetry.

    On an ``openrouter_free`` auto slot the sentinel is resolved against the
    live free catalogue, an all-free ``models`` fallback chain is attached,
    and a dead/rate-limited model triggers a re-resolution (never a paid one).
    The returned ``model`` is OpenRouter's authoritative ``data["model"]`` —
    the free model that actually answered.

    HTTP 200 is not treated as success by itself: empty, refused,
    reasoning-only and output-truncated completions are typed failures. On
    OpenRouter the same model first gets one direct-answer retry with
    reasoning disabled; auto free routing can then fail over to another
    ``:free`` model. ``avoid_models`` lets an agent-level repair retry skip a
    model that already returned malformed output.
    """
    actual_slot = resolve_slot(slot)
    creds = get_credentials(actual_slot)
    if creds is None:
        raise LLMError(f"No active API key configured for the {slot} slot")
    p: Provider = creds["spec"]
    requested = creds["model"]
    key = creds["api_key"]
    if not key and p.key != "ollama":
        raise LLMError(f"Empty key for {p.label} in the {actual_slot} slot")

    auto = (p.key == "openrouter_free" and
            requested in (openrouter_auto.AUTO_MODEL, openrouter_auto.ROUTER_MODEL))
    attempts = _AUTO_ATTEMPTS if auto else 1
    url = _endpoint(p)
    avoid: Set[str] = {str(m).strip() for m in (avoid_models or ()) if str(m).strip()}
    resolution = None
    last_error: Optional[LLMError] = None
    per_call_timeout = timeout or settings.request_timeout
    t0 = time.perf_counter()

    # If an earlier call hit the free pool's rate limit, wait out the window
    # before sending anything else. Failover *within* this call stays
    # immediate, because a 429 can also be specific to one model's endpoint.
    _wait_out_rate_limit(p)

    model_attempt = 0
    reasoning_retry_for: Optional[str] = None
    while model_attempt < attempts or reasoning_retry_for is not None:
        is_reasoning_retry = reasoning_retry_for is not None
        if is_reasoning_retry:
            chosen = str(reasoning_retry_for)
            reasoning_retry_for = None
            fallbacks = []
            structured = json_mode
        else:
            model_attempt += 1
            chosen = requested
            fallbacks = []
            structured = json_mode
            if auto:
                if model_attempt > 1 and model_attempt == attempts:
                    # Final safety net: let OpenRouter's own capability-aware
                    # free router choose. It is always current and zero-cost.
                    chosen = openrouter_auto.ROUTER_MODEL
                    structured = json_mode
                else:
                    resolution = openrouter_auto.resolve(
                        requested, json_mode=json_mode, max_tokens=max_tokens,
                        avoid=avoid)
                    chosen = resolution.primary
                    # All-free chain for OpenRouter's server-side failover;
                    # the primary stays in `model`, so `models` holds the
                    # remaining concrete free candidates. The router slug is
                    # used as a primary only when no concrete model is usable,
                    # because some endpoints reject router slugs in `models`.
                    fallbacks = [m for m in resolution.fallbacks
                                 if m != chosen and
                                 m != openrouter_auto.ROUTER_MODEL]
                    structured = json_mode and resolution.json_supported
        body = _payload(p, chosen, system, user, max_tokens, temperature,
                        structured, fallbacks,
                        disable_reasoning=is_reasoning_retry)
        # Send OpenRouter requests one at a time: the pipeline's parallel
        # stage must not burst the free pool's per-minute cap.
        try:
            with _or_request_lock if _is_openrouter(p) else nullcontext():
                resp = requests.post(url, headers=_headers(p, key), json=body,
                                     timeout=per_call_timeout)
        except requests.Timeout as exc:
            raise LLMError(f"{p.label} timed out after {per_call_timeout}s") from exc
        except requests.RequestException as exc:
            raise LLMError(f"Could not reach {p.label}: {_safe(exc)}") from exc

        if resp.status_code >= 400:
            if resp.status_code == 429:
                retry_after = _parse_retry_after(resp.headers)
                _note_rate_limit(p, retry_after)
            err = _error_for_status(p, resp.status_code, resp.text)
            if resp.status_code == 429:
                err.retry_after_s = retry_after
            if (auto and model_attempt < attempts and
                    resp.status_code in _RETRYABLE):
                openrouter_auto.note_failure(chosen, resp.status_code)
                avoid.add(chosen)
                last_error = err
                logger.info("OpenRouter auto: %s failed (HTTP %s), retrying free model",
                            chosen, resp.status_code)
                continue
            raise err

        try:
            data = resp.json()
        except ValueError as exc:
            raise LLMError(f"{p.label} returned non-JSON response") from exc
        if isinstance(data, dict) and data.get("error"):
            err = _error_for_status(p, resp.status_code if resp.status_code >= 400 else 502,
                                    data)
            if err.status == 429 or err.category == "rate_limit":
                _note_rate_limit(p, _parse_retry_after(resp.headers))
            if auto and model_attempt < attempts and err.status in _RETRYABLE:
                openrouter_auto.note_failure(chosen, 502)
                avoid.add(chosen)
                last_error = err
                continue
            raise err
        try:
            text, completion_meta = _extract_completion(p, data)
        except LLMError as exc:
            if (p.key.startswith("openrouter") and not is_reasoning_retry and
                    exc.category.startswith("completion_")):
                # A reasoning model may have spent its whole budget before
                # the final answer. Ask that same model once more, directly.
                # OpenRouter's fallback chain may have served a different
                # model from the requested primary, so prefer its report.
                served_model = data.get("model") if isinstance(data, dict) else None
                reasoning_retry_for = (served_model.strip()
                                       if isinstance(served_model, str) and
                                       served_model.strip() else chosen)
                last_error = exc
                logger.info("OpenRouter %s returned %s; retrying without reasoning",
                            chosen, exc.kind)
                continue
            if auto and model_attempt < attempts:
                openrouter_auto.note_failure(chosen, 502)
                avoid.add(chosen)
                last_error = exc
                continue
            raise

        # OpenRouter reports the model that actually served the request (which
        # can differ from the primary when a fallback fired).
        served = requested
        if isinstance(data, dict) and isinstance(data.get("model"), str):
            served = data["model"].strip() or chosen
        elif auto:
            served = chosen
        if auto:
            openrouter_auto.note_success(served)
        usage = (data.get("usage", {}) or {}) if isinstance(data, dict) else {}
        quota_headers = {k: v for k, v in resp.headers.items()
                         if "ratelimit" in k.lower() or "quota" in k.lower()}
        return {
            "text": text, "provider": p.label, "model": served, "slot": actual_slot,
            "requested_model": requested, "auto_selected": bool(auto),
            "selection_source": resolution.source if resolution else "pinned",
            "fallback_models": tuple(fallbacks),
            "latency_ms": int((time.perf_counter() - t0) * 1000),
            "input_tokens": int(usage.get("prompt_tokens") or usage.get("input_tokens") or 0),
            "output_tokens": int(usage.get("completion_tokens") or usage.get("output_tokens") or 0),
            "finish_reason": completion_meta.get("finish_reason", ""),
            "reasoning_tokens": completion_meta.get("reasoning_tokens", 0),
            "completion_truncated": bool(completion_meta.get("truncated")),
            "reasoning_retry": bool(is_reasoning_retry),
            "quota_headers": quota_headers,
        }

    raise last_error or LLMError(f"{p.label}: no free model could complete the request")


def complete(slot: str, system: str, user: str, **kwargs) -> str:
    """Shortcut returning only the text."""
    return call_llm(slot, system, user, **kwargs)["text"]


def test_connection(slot: str, timeout: float = 12.0) -> Dict[str, Any]:
    """Validate one slot with a minimal, cheap completion."""
    from app.database import queries
    actual = resolve_slot(slot)
    creds = get_credentials(actual)
    if creds is None:
        return {"ok": False, "slot": slot, "error": "No key saved in this slot"}
    try:
        result = call_llm(slot, "You are a connectivity probe. Reply with exactly: OK",
                          "Reply with exactly: OK", max_tokens=12, temperature=0,
                          timeout=timeout)
        quota = result["quota_headers"] or None
        try:
            queries.update_key_test(actual, True, quota)
        except Exception:
            logger.warning("Could not persist successful key test for %s", actual)
        return {"ok": True, "slot": slot, "provider": result["provider"],
                "model": result["model"], "latency_ms": result["latency_ms"],
                "quota": quota, "inherited": actual != slot}
    except LLMError as exc:
        try:
            queries.update_key_test(actual, False)
        except Exception:
            logger.warning("Could not persist failed key test for %s", actual)
        return {"ok": False, "slot": slot, "tested_slot": actual,
                "inherited": actual != slot, **exc.as_dict()}
    except Exception as exc:
        try:
            queries.update_key_test(actual, False)
        except Exception:
            logger.warning("Could not persist failed key test for %s", actual)
        message = _safe(exc)[:240] or "The connection test failed"
        return {"ok": False, "slot": slot, "tested_slot": actual,
                "inherited": actual != slot, "error": message,
                "status": None, "category": "connection_error",
                "action": "Check the provider status and test again.",
                "provider_message": None}
