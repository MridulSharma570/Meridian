"""Live OpenRouter free-model discovery and "best free model" auto-selection.

OpenRouter rotates its free catalogue constantly: a hard-coded ``:free`` slug
eventually starts returning HTTP 404. This module queries the public
``GET /api/v1/models`` catalogue, keeps only *currently free* text→text chat
models, ranks them with an explainable score and returns a ranked, all-free
fallback chain for the LLM router.

Official references
  Free Models Router  https://openrouter.ai/docs/guides/routing/routers/free-router.md
  Model Fallbacks     https://openrouter.ai/docs/guides/routing/model-fallbacks.md
  Models catalogue    https://openrouter.ai/docs/api-reference/models/get-models.md

Design rules
  * No API key is ever sent to the catalogue endpoint (it is public).
  * Every candidate is free (zero prompt/completion price, or ``:free``), so a
    fallback can never silently turn a free slot into a billable request.
  * Any network/parsing failure degrades to ``openrouter/free`` (OpenRouter's
    own capability-aware free router) — no stale, possibly retired slugs.
  * A model that 404s / rate-limits is cooled down and skipped on the next call.
  * The response's ``model`` field is authoritative: it names the free model
    that actually answered.

Developed by Mridul Sharma
"""
from __future__ import annotations

import logging
import re
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

import requests

from app.api.providers import (AUTO_MODEL_LABELS, OPENROUTER_AUTO_MODEL,
                               OPENROUTER_FREE_ROUTER)
from app.config import settings

logger = logging.getLogger("meridian.openrouter")

MODELS_URL = "https://openrouter.ai/api/v1/models"
AUTO_MODEL = OPENROUTER_AUTO_MODEL
ROUTER_MODEL = OPENROUTER_FREE_ROUTER
COOLDOWN_S = 300
STICKY_S = 600
_FAILURE_STATUSES = {400, 404, 408, 409, 410, 429, 500, 502, 503, 504}
_REFRESH_STATUSES = {404, 410}

# Model IDs that cannot serve a plain text chat completion.
_EXCLUDE_ID_TOKENS = (
    "embedding", "rerank", "tts", "speech", "transcription", "safety",
    "moderation", "guard", "decision", "classifier", "image-generation",
    "video-generation", "openrouter/free", "openrouter/auto", "switchyard",
)
_TINY_MODEL = re.compile(r"(?:^|[-_/])(\d+(?:\.\d+)?b)(?:[-_/]|$)", re.I)
_TINY_WORDS = ("tiny", "mini", "nano", "small", "micro")
# Stay clear of "alpha"/"beta": they are common *version* labels (e.g.
# "gemini-2.0-flash-beta-30b") and are not evidence of a throwaway preview.
_PREVIEW_WORDS = ("preview", "stealth", "experimental", "crouton")
_STRONG_FAMILIES = ("gpt-oss", "qwen", "nemotron", "llama", "gemma",
                    "deepseek", "mistral", "glm", "kimi", "qwen3")


# --------------------------------------------------------------------------- #
# Value objects
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class FreeModel:
    id: str
    name: str
    context_length: int
    max_completion_tokens: int
    created: int
    supported_parameters: Tuple[str, ...]
    score: float

    @property
    def supports_json(self) -> bool:
        return ("response_format" in self.supported_parameters or
                "structured_outputs" in self.supported_parameters)

    @property
    def supports_tools(self) -> bool:
        return ("tools" in self.supported_parameters or
                "tool_choice" in self.supported_parameters)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id, "name": self.name,
            "context_length": self.context_length,
            "max_completion_tokens": self.max_completion_tokens,
            "created": self.created,
            "supported_parameters": list(self.supported_parameters),
            "score": self.score, "supports_json": self.supports_json,
            "supports_tools": self.supports_tools, "free": True,
        }


@dataclass(frozen=True)
class Catalog:
    models: Tuple[FreeModel, ...]
    source: str                     # live | cache | fallback | disabled
    fetched_at: float
    error: str = ""


@dataclass(frozen=True)
class Resolution:
    primary: str
    fallbacks: Tuple[str, ...]      # priority-ordered `models` array for OpenRouter
    auto: bool
    source: str
    requested: str
    candidates: Tuple[str, ...]
    json_supported: bool


# --------------------------------------------------------------------------- #
# Thread-safe module state
# --------------------------------------------------------------------------- #
_lock = threading.Lock()
_cache: Optional[Catalog] = None
_cooldowns: Dict[str, float] = {}
_last_success: Tuple[str, float] = ("", 0.0)
_force_refresh = False


def _safe_error(exc: BaseException) -> str:
    """Short, key-free error text (catalogue calls carry no credentials)."""
    return f"{type(exc).__name__}: {str(exc)[:160]}"


def _zero(value: Any) -> bool:
    try:
        return abs(float(value)) < 1e-12
    except (TypeError, ValueError):
        return False


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _expired(value: Any, now: float) -> bool:
    """True when an explicit expiration_date is already in the past."""
    if not value:
        return False
    try:
        ts = datetime.strptime(str(value)[:10], "%Y-%m-%d").replace(
            tzinfo=timezone.utc).timestamp()
        return ts < now
    except (ValueError, TypeError):
        return False


def _is_free_chat_model(m: Dict[str, Any], now: float) -> bool:
    """Keep only free, text-in/text-out, chat-completions-capable models."""
    mid = str(m.get("id") or "").strip()
    if not mid or mid != mid.lower() or any(t in mid.lower() for t in _EXCLUDE_ID_TOKENS):
        return False
    if "/" not in mid:                       # router slugs / aliases are not models
        return False
    pricing = m.get("pricing") or {}
    if not isinstance(pricing, dict):
        return False
    if not (_zero(pricing.get("prompt")) and _zero(pricing.get("completion"))):
        return False
    if not _zero(pricing.get("request", 0)):
        return False

    arch = m.get("architecture") or {}
    if not isinstance(arch, dict) or not arch:
        return False
    inputs = [str(x).lower() for x in (arch.get("input_modalities") or [])]
    outputs = [str(x).lower() for x in (arch.get("output_modalities") or [])]
    if (inputs and "text" not in inputs) or (outputs and "text" not in outputs):
        return False

    endpoints = m.get("endpoints")
    if isinstance(endpoints, list) and endpoints:
        if not any("chat/completions" in str(e) for e in endpoints):
            return False
    if _expired(m.get("expiration_date"), now):
        return False
    return True


def _score(m: Dict[str, Any], now: float) -> float:
    """Explainable quality score. Higher is better for long report generation."""
    mid = str(m.get("id") or "").lower()
    ctx = max(0, min(_int(m.get("context_length")), 1_048_576))
    top = m.get("top_provider") or {}
    out = max(0, min(_int(top.get("max_completion_tokens") if isinstance(top, dict) else 0), 262144))
    params = {str(p).lower() for p in (m.get("supported_parameters") or [])}

    # Long context matters for a full market report; diminishing returns above 262k.
    points = 25.0 * min(1.0, ctx / 262144.0)
    points += 15.0 * min(1.0, out / 16384.0)
    if "response_format" in params or "structured_outputs" in params:
        points += 14.0                       # agents request JSON
    if "tools" in params or "tool_choice" in params:
        points += 6.0
    if "temperature" in params:
        points += 3.0

    created = _int(m.get("created"))
    if created:
        age_days = max(0.0, (now - created) / 86400.0)
        points += 12.0 * max(0.0, 1.0 - age_days / 540.0)   # newer is better

    # OpenRouter publishes Artificial Analysis benchmark scores for some
    # models. When present, this is a stronger quality signal than metadata.
    bench = m.get("benchmarks")
    aa = (bench.get("artificial_analysis") or {}) if isinstance(bench, dict) else {}
    if isinstance(aa, dict):
        try:
            index = float(aa.get("intelligence_index") or 0)
            points += min(15.0, max(0.0, index) * 0.25)
        except (TypeError, ValueError):
            pass

    if mid.endswith(":free"):
        points += 4.0                         # explicitly free variant
    else:
        points -= 3.0                         # zero-priced preview, may vanish
    if any(f in mid for f in _STRONG_FAMILIES):
        points += 4.0
    tiny = _TINY_MODEL.search(mid)
    if tiny:
        try:
            if float(tiny.group(1).rstrip("b")) <= 3.0:
                points -= 8.0
        except ValueError:
            pass
    if any(w in mid for w in _TINY_WORDS):
        points -= 6.0
    if any(w in mid for w in _PREVIEW_WORDS):
        points -= 10.0                        # anonymous / time-limited previews
    return round(points, 1)


def _to_free_model(m: Dict[str, Any], now: float) -> FreeModel:
    top = m.get("top_provider") or {}
    return FreeModel(
        id=str(m["id"]),
        name=str(m.get("name") or m["id"])[:120],
        context_length=_int(m.get("context_length")),
        max_completion_tokens=_int(top.get("max_completion_tokens") if isinstance(top, dict) else 0),
        created=_int(m.get("created")),
        supported_parameters=tuple(str(p) for p in (m.get("supported_parameters") or [])),
        score=_score(m, now),
    )


def _rank(raw: Sequence[Dict[str, Any]]) -> List[FreeModel]:
    now = time.time()
    models = [_to_free_model(m, now) for m in raw if _is_free_chat_model(m, now)]
    return sorted(models, key=lambda x: (-x.score, x.id))


def _fetch_models() -> List[Dict[str, Any]]:
    """Public catalogue — no credentials are attached to this request."""
    resp = requests.get(
        MODELS_URL,
        params={"output_modalities": "text"},
        headers={"Accept": "application/json", "User-Agent": "Meridian/1.0"},
        timeout=max(1.0, settings.openrouter_catalog_timeout),
    )
    resp.raise_for_status()
    payload = resp.json()
    data = payload.get("data") if isinstance(payload, dict) else payload
    if not isinstance(data, list):
        raise ValueError("unexpected /models payload shape")
    return [m for m in data if isinstance(m, dict)]


def _empty_catalog(now: float, error: str = "", source: str = "fallback") -> Catalog:
    """No ranked candidates: the built-in free router becomes the only choice."""
    return Catalog((), source, now, error)


def _fallback_catalog(now: float, error: str) -> Catalog:
    # Reuse a previously successful live snapshot if we have one.
    if _cache is not None and _cache.models and _cache.source != "fallback":
        return Catalog(_cache.models, "cache", _cache.fetched_at, error)
    return _empty_catalog(now, error)


def catalog(force: bool = False) -> Catalog:
    """Return the ranked free catalogue, cached for ``MERIDIAN_OPENROUTER_CATALOG_TTL`` s."""
    global _cache, _force_refresh
    with _lock:
        now = time.time()
        if not settings.openrouter_auto_enabled:
            return _empty_catalog(now, "auto-selection disabled", "disabled")
        refresh = force or _force_refresh
        _force_refresh = False
        if _cache is not None and not refresh:
            ttl = (max(30, settings.openrouter_catalog_ttl)
                   if _cache.source == "live" else 60)
            if now - _cache.fetched_at < ttl:
                return _cache
        try:
            ranked = tuple(_rank(_fetch_models()))
            if not ranked:
                raise ValueError("catalogue contained no free text chat models")
            _cache = Catalog(ranked, "live", now)
            logger.info("OpenRouter free catalogue: %d models, best=%s (%.1f)",
                        len(ranked), ranked[0].id, ranked[0].score)
            return _cache
        except Exception as exc:
            reason = _safe_error(exc)
            logger.info("OpenRouter catalogue unavailable (%s); using free fallback", reason)
            _cache = _fallback_catalog(now, reason)
            return _cache


# --------------------------------------------------------------------------- #
# Resolution
# --------------------------------------------------------------------------- #
def _candidates(cat: Catalog, *, json_mode: bool, max_tokens: int,
                avoid: Set[str]) -> List[FreeModel]:
    now = time.time()
    scored: List[Tuple[float, FreeModel]] = []
    for m in cat.models:
        if m.id in avoid or _cooldowns.get(m.id, 0.0) > now:
            continue
        if max_tokens and m.max_completion_tokens and m.max_completion_tokens < max_tokens:
            continue
        bonus = 0.0
        if json_mode and m.supports_json:
            bonus += 20.0                    # structured output matters for agents
        if _last_success[0] == m.id and now - _last_success[1] < STICKY_S:
            bonus += 6.0                     # prefer a model already proven alive
        scored.append((m.score + bonus, m))
    scored.sort(key=lambda t: (-t[0], t[1].id))
    return [m for _, m in scored]


def resolve(model: str, *, json_mode: bool = False, max_tokens: int = 1600,
            avoid: Iterable[str] = ()) -> Resolution:
    """Turn ``auto:best-free`` (or ``openrouter/free``) into a live, all-free chain."""
    requested = (model or AUTO_MODEL).strip()
    if requested not in (AUTO_MODEL, ROUTER_MODEL):
        # User pinned a specific model — never override their choice.
        return Resolution(requested, (), False, "pinned", requested, (), True)

    cat = catalog()
    cands = _candidates(cat, json_mode=json_mode, max_tokens=max_tokens,
                        avoid=set(avoid))
    ids = [m.id for m in cands]
    max_n = max(1, min(settings.openrouter_max_fallbacks, 8))

    # Without a live catalogue the built-in free router is the only always-
    # current choice: hard-coded :free slugs may have been retired upstream.
    stale = cat.source in ("fallback", "disabled")
    if requested == ROUTER_MODEL or stale or not ids:
        primary = ROUTER_MODEL
        chain: List[str] = [ROUTER_MODEL] + [i for i in ids if i != ROUTER_MODEL][:max_n]
    else:
        primary = ids[0]
        chain = ids[:max_n + 1]

    if ROUTER_MODEL not in chain:
        chain.append(ROUTER_MODEL)           # last-resort capability-aware router
    chain = list(dict.fromkeys(chain))       # stable de-duplication
    json_supported = (True if primary == ROUTER_MODEL else
                      next((m.supports_json for m in cands if m.id == primary), False))
    return Resolution(primary, tuple(chain), True, cat.source, requested,
                      tuple(ids[:max_n + 1]), json_supported)


def note_failure(model: str, status: int) -> None:
    """Cool down a dead/rate-limited free model; refresh the catalogue on 404."""
    global _force_refresh
    if status not in _FAILURE_STATUSES:
        return
    with _lock:
        _cooldowns[model] = time.time() + COOLDOWN_S
        if status in _REFRESH_STATUSES:
            _force_refresh = True
        logger.info("OpenRouter model %s cooled down (HTTP %s)", model, status)


def note_success(model: str) -> None:
    global _last_success
    with _lock:
        _last_success = (model, time.time())


# --------------------------------------------------------------------------- #
# UI / API payload
# --------------------------------------------------------------------------- #
def describe(force: bool = False) -> Dict[str, Any]:
    """Safe, serialisable snapshot for the Settings screen (no credentials)."""
    cat = catalog(force=force)
    stamp = datetime.fromtimestamp(cat.fetched_at, timezone.utc).isoformat()
    return {
        "provider": "openrouter_free",
        "auto_model": AUTO_MODEL,
        "auto_label": AUTO_MODEL_LABELS[AUTO_MODEL],
        "router_model": ROUTER_MODEL,
        "router_label": AUTO_MODEL_LABELS[ROUTER_MODEL],
        "enabled": settings.openrouter_auto_enabled,
        "source": cat.source,
        "error": cat.error or None,
        "fetched_at": stamp,
        "ttl_s": max(30, settings.openrouter_catalog_ttl),
        "count": len(cat.models),
        "recommended": (ROUTER_MODEL if cat.source in ("fallback", "disabled")
                        else cat.models[0].id if cat.models else ROUTER_MODEL),
        "recommended_label": (AUTO_MODEL_LABELS[ROUTER_MODEL]
                              if cat.source in ("fallback", "disabled") else
                              cat.models[0].id if cat.models
                              else AUTO_MODEL_LABELS[ROUTER_MODEL]),
        "models": [m.as_dict() for m in cat.models],
    }


def reset() -> None:
    """Clear all module state — used by tests and the Settings refresh action."""
    global _cache, _last_success, _force_refresh
    with _lock:
        _cache = None
        _cooldowns.clear()
        _last_success = ("", 0.0)
        _force_refresh = False
