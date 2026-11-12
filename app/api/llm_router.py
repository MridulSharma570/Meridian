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
import time
from typing import Any, Dict, List, Optional, Set

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
                 provider_message: str = ""):
        super().__init__(message)
        self.status = status
        self.category = category
        self.action = action
        self.provider_message = provider_message

    def as_dict(self) -> Dict[str, Any]:
        return {
            "error": str(self), "status": self.status,
            "category": self.category, "action": self.action,
            "provider_message": self.provider_message or None,
        }


def _safe(text: str) -> str:
    return _SENSITIVE.sub("<redacted>", str(text))[:800]


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
             fallbacks: Optional[List[str]] = None) -> Dict[str, Any]:
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
    if fallbacks:
        # OpenRouter's priority-ordered failover for /chat/completions. The
        # router only builds all-free chains, so a retry can never be billed.
        body["models"] = list(fallbacks)
    return body


def _extract(p: Provider, data: Dict[str, Any]) -> str:
    try:
        if p.api_style == "anthropic":
            parts = data.get("content", [])
            return "".join(x.get("text", "") for x in parts if isinstance(x, dict)).strip()
        if p.api_style == "cohere":
            msg = data.get("message", {})
            parts = msg.get("content", [])
            if parts and isinstance(parts[0], dict):
                return "".join(x.get("text", "") for x in parts).strip()
            return (msg.get("content") or "").strip()
        choices = data.get("choices") or []
        if choices:
            msg = choices[0].get("message", {}) or {}
            content = msg.get("content")
            if isinstance(content, list):
                return "".join(x.get("text", "") for x in content if isinstance(x, dict)).strip()
            return (content or "").strip()
        if isinstance(data.get("text"), str):
            return data["text"].strip()
    except (AttributeError, TypeError, IndexError) as exc:
        raise LLMError(f"Malformed response from {p.label}: {_safe(exc)}") from exc
    raise LLMError(f"{p.label} returned no completion text")


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
                      "capped per minute and per day). Wait a few minutes, choose Auto — "
                      "best free model, or use a free Groq/Gemini key.")
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
             timeout: Optional[float] = None) -> Dict[str, Any]:
    """Execute one completion. Returns text plus usage telemetry.

    On an ``openrouter_free`` auto slot the sentinel is resolved against the
    live free catalogue, an all-free ``models`` fallback chain is attached,
    and a dead/rate-limited model triggers a re-resolution (never a paid one).
    The returned ``model`` is OpenRouter's authoritative ``data["model"]`` —
    the free model that actually answered.
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
    avoid: Set[str] = set()
    resolution = None
    last_error: Optional[LLMError] = None
    per_call_timeout = timeout or settings.request_timeout
    t0 = time.perf_counter()

    for attempt in range(attempts):
        chosen = requested
        fallbacks: List[str] = []
        structured = json_mode
        if auto:
            if attempt and attempt == attempts - 1:
                # Final safety net: let OpenRouter's own capability-aware free
                # router choose. It is always current and always zero-cost.
                chosen = openrouter_auto.ROUTER_MODEL
                structured = json_mode
            else:
                resolution = openrouter_auto.resolve(
                    requested, json_mode=json_mode, max_tokens=max_tokens, avoid=avoid)
                chosen = resolution.primary
                # All-free chain for OpenRouter's server-side failover; the
                # primary stays in `model`, so `models` holds the remaining
                # concrete free candidates. The `openrouter/free` router slug
                # is excluded here — it is used as a *primary* only when no
                # concrete model is usable, because some endpoints reject
                # router slugs inside `models`.
                fallbacks = [m for m in resolution.fallbacks
                             if m != chosen and m != openrouter_auto.ROUTER_MODEL]
                structured = json_mode and resolution.json_supported
        body = _payload(p, chosen, system, user, max_tokens, temperature,
                        structured, fallbacks)
        try:
            resp = requests.post(url, headers=_headers(p, key), json=body,
                                 timeout=per_call_timeout)
        except requests.Timeout as exc:
            raise LLMError(f"{p.label} timed out after {per_call_timeout}s") from exc
        except requests.RequestException as exc:
            raise LLMError(f"Could not reach {p.label}: {_safe(exc)}") from exc

        if resp.status_code >= 400:
            err = _error_for_status(p, resp.status_code, resp.text)
            if (auto and attempt < attempts - 1 and
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
            if auto and attempt < attempts - 1 and err.status in _RETRYABLE:
                openrouter_auto.note_failure(chosen, 502)
                avoid.add(chosen)
                last_error = err
                continue
            raise err
        try:
            text = _extract(p, data)
        except LLMError as exc:
            if auto and attempt < attempts - 1:
                openrouter_auto.note_failure(chosen, 502)
                avoid.add(chosen)
                last_error = exc
                continue
            raise
        if not text:
            err = LLMError(f"{p.label} returned an empty completion")
            if auto and attempt < attempts - 1:
                openrouter_auto.note_failure(chosen, 502)
                avoid.add(chosen)
                last_error = err
                continue
            raise err

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
