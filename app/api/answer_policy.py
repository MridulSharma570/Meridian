"""Verified-answer policy: Meridian never answers without a real API.

Historically the product shipped a deterministic "local analytical engine"
that produced a complete, plausible-looking intelligence report from a hash of
the query — including invented market sizes and citations bearing real
publisher names — even when zero API keys were configured. That is exactly the
behaviour this module removes.

Rules (production defaults):

* At least one active **LLM provider key** must be configured before a report,
  chat answer, translation or comparison can be produced. A failed provider
  call is an error, never a licence to fall back to canned text.
* A report additionally needs **real evidence** from a live connector. Numbers
  that no source supplied are never presented as facts.
* The deterministic engine survives only as an explicitly enabled, loudly
  labelled **sample mode** (``MERIDIAN_SAMPLE_MODE=1``), intended for tests and
  offline UI demos. It is off by default.

All policy checks are evaluated at call time so tests can flip the mode with
``monkeypatch.setenv`` without reloading the application.
"""
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from app.config import settings

SAMPLE_ENV = "MERIDIAN_SAMPLE_MODE"
SETUP_PATH = "#/settings"

_NO_KEY_HINT = (
    "Open Settings → API Keys and save at least one provider key (OpenRouter "
    "free models work without billing). Meridian will not answer from "
    "templates while no API is configured."
)
_NO_EVIDENCE_HINT = (
    "Configure TAVILY_API_KEY or NEWS_API_KEY (or allow the keyless live "
    "connectors through your network) so Meridian can cite real sources. "
    "Set MERIDIAN_REQUIRE_LIVE_EVIDENCE=false only if you explicitly accept "
    "model-knowledge answers that are labelled as unverified."
)


class AnswerUnavailable(RuntimeError):
    """Raised instead of fabricating an answer.

    Carries a UI-friendly, structured payload; the HTTP layer maps it to 409.
    """

    status_code = 409

    def __init__(self, message: str, hint: str = _NO_KEY_HINT,
                 reason: str = "api_key_required") -> None:
        super().__init__(message)
        self.message = message
        self.hint = hint
        self.reason = reason

    def as_dict(self) -> Dict[str, Any]:
        return {"error": "answer_unavailable", "reason": self.reason,
                "message": self.message, "hint": self.hint,
                "setup_path": SETUP_PATH}


def _flag(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


def sample_mode() -> bool:
    """Explicit, loudly labelled offline sample mode (off by default)."""
    return _flag(SAMPLE_ENV, False)


def require_live_evidence() -> bool:
    """Whether a report must cite at least one real, live source."""
    return _flag("MERIDIAN_REQUIRE_LIVE_EVIDENCE", settings.require_live_evidence)


def configured_llm_slots() -> List[str]:
    """Active provider slots, safe to call before the schema exists."""
    try:
        from app.api.llm_router import configured_slots
        return configured_slots()
    except Exception:
        return []


def data_connectors() -> Dict[str, bool]:
    return {
        "tavily": bool(settings.tavily_api_key.strip()),
        "newsapi": bool(settings.news_api_key.strip()),
        "duckduckgo_html": settings.enable_live_data,
        "world_bank": settings.enable_live_data and settings.world_bank_enabled,
        "reddit": settings.enable_live_data,
    }


def readiness() -> Dict[str, Any]:
    """Cheap, structured status consumed by the SPA and Streamlit UI."""
    slots = configured_llm_slots()
    sample = sample_mode()
    llm_configured = bool(slots)
    connectors = data_connectors()
    live_possible = any(connectors.values())
    answers_enabled = sample or (
        llm_configured and not (require_live_evidence() and not live_possible))
    if sample:
        reason = "sample_mode"
        message = ("SAMPLE MODE — offline, deterministic data. Nothing here is "
                   "verified and no external API is being used.")
    elif not llm_configured:
        reason = "api_key_required"
        message = "No provider API key is configured. Answers are disabled."
    elif require_live_evidence() and not live_possible:
        reason = "no_live_connector"
        message = ("An LLM API key is configured but every live data connector "
                   "is disabled. Reports will be refused unless real sources "
                   "can be collected.")
    else:
        reason = ""
        message = "Answers are generated from your configured API and live sources."
    return {
        "answers_enabled": answers_enabled,
        "llm_configured": llm_configured,
        "llm_slots": slots,
        "sample_mode": sample,
        "require_live_evidence": require_live_evidence(),
        "live_data_enabled": settings.enable_live_data,
        "data_connectors": connectors,
        "reason": reason,
        "message": message,
        "hint": _NO_KEY_HINT if reason == "api_key_required" else _NO_EVIDENCE_HINT,
        "setup_path": SETUP_PATH,
    }


def require_api(feature: str = "answer") -> None:
    """Hard gate: no configured API means no answer, ever."""
    if sample_mode():
        return
    if configured_llm_slots():
        return
    raise AnswerUnavailable(
        f"Cannot generate a {feature}: no provider API key is configured.",
        _NO_KEY_HINT, "api_key_required")


def require_evidence(dataset: Dict[str, Any]) -> None:
    """Hard gate: without real sources we will not publish invented figures."""
    if sample_mode() or not require_live_evidence():
        return
    sources = dataset.get("verified_sources") or []
    if not sources:
        raise AnswerUnavailable(
            "No live sources could be collected, so Meridian will not guess "
            "market sizes, competitors or citations.",
            _NO_EVIDENCE_HINT, "no_live_evidence")


def provenance_note(dataset: Dict[str, Any]) -> str:
    """One honest sentence describing where the numbers came from."""
    sources = dataset.get("verified_sources") or []
    if sample_mode():
        return ("SAMPLE MODE: every figure is deterministic demo data, not "
                "research. Do not use it for decisions.")
    if sources:
        return (f"{len(sources)} live source(s) were retrieved. Any other "
                "numeric series shown in charts are illustrative placeholders "
                "and are not verified figures — check the cited sources.")
    if not require_live_evidence():
        return ("No live sources were available. Narrative answers come only "
                "from the configured LLM and are labelled unverified; chart "
                "series are placeholders, not measurements.")
    return "No verified figures are available."


def strict_mode() -> bool:
    """True whenever answers must come from a real provider API."""
    return not sample_mode()


def verified_source_ids(dataset: Optional[Dict[str, Any]]) -> List[str]:
    """Ids of real sources only; used to reject hallucinated citations."""
    if not dataset:
        return []
    return [str(s.get("id")) for s in (dataset.get("verified_sources") or [])
            if isinstance(s, dict) and s.get("id")]
