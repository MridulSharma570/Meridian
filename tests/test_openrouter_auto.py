"""Regression tests for OpenRouter's live, zero-cost free-model auto-selection.

All HTTP traffic is mocked: these tests never contact OpenRouter and never
require an API key. They verify that auto mode stays free, honours the live
catalogue, reports the model that actually answered, and fails over when a
free model is retired or rate-limited.

Developed by Mridul Sharma
"""
from __future__ import annotations

import json
import time
from types import SimpleNamespace

import pytest

from app.api import key_manager, llm_router, openrouter_auto as auto
from app.api.providers import (OPENROUTER_AUTO_MODEL, OPENROUTER_FREE_ROUTER,
                               OPENROUTER_LEGACY_MODELS, get_provider,
                               is_allowed_model, list_providers, model_label,
                               normalize_model)
from fastapi.testclient import TestClient

from app.api.server import app


def _model(mid: str, **over) -> dict:
    row = {
        "id": mid, "canonical_slug": mid, "name": mid.split("/")[-1],
        "created": int(time.time()) - 86400 * 30,
        "pricing": {"prompt": "0", "completion": "0", "request": "0",
                    "image": "0", "discount": "0"},
        "context_length": 131072,
        "architecture": {"input_modalities": ["text"],
                         "output_modalities": ["text"], "modality": "text->text",
                         "tokenizer": "GPT"},
        "supported_parameters": ["temperature", "max_tokens", "response_format",
                                 "tools", "top_p"],
        "top_provider": {"context_length": 131072, "max_completion_tokens": 8192,
                         "is_moderated": False},
        "endpoints": ["/api/v1/chat/completions"],
        "expiration_date": None,
        "per_request_limits": None,
    }
    row.update(over)
    return row


BEST = "vendor/alpha-70b:free"
SECOND = "vendor/beta-30b:free"
THIRD = "vendor/gamma-8b:free"


def _live_catalogue() -> list[dict]:
    return [
        _model(BEST, context_length=262144,
               top_provider={"max_completion_tokens": 32768}),
        _model(SECOND, context_length=131072,
               supported_parameters=["temperature", "max_tokens"]),
        _model(THIRD, context_length=32768,
               supported_parameters=["temperature", "max_tokens"]),
        # ---- everything below must be rejected -----------------------------
        _model("vendor/paid-chat", pricing={"prompt": "0.000003",
                                            "completion": "0.000006", "request": "0"}),
        _model("vendor/embedding", architecture={"input_modalities": ["text"],
                                                "output_modalities": ["embedding"]}),
        _model("vendor/image-model", architecture={"input_modalities": ["image"],
                                                  "output_modalities": ["text"]}),
        _model("vendor/vanished:free", expiration_date="2020-01-01"),
        _model("openrouter/free", pricing={"prompt": "0", "completion": "0"}),
        _model("openrouter/auto"),
        _model("vendor/tts-free", endpoints=["/api/v1/audio/speech"]),
    ]


class FakeResponse:
    def __init__(self, status: int = 200, data: dict | None = None, text: str = ""):
        self.status_code = status
        self._data = data if data is not None else {}
        self.text = text or json.dumps(self._data)
        self.headers = {"x-ratelimit-remaining": "19"}

    def json(self):
        return self._data


def _completion(model: str, text: str = "OK") -> FakeResponse:
    return FakeResponse(200, {
        "model": model,
        "choices": [{"message": {"role": "assistant", "content": text}}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 4},
    })


@pytest.fixture(autouse=True)
def _clean_state(monkeypatch):
    auto.reset()
    monkeypatch.setattr(auto, "settings", SimpleNamespace(
        openrouter_auto_enabled=True, openrouter_catalog_ttl=900,
        openrouter_catalog_timeout=5.0, openrouter_max_fallbacks=4))
    monkeypatch.setattr(auto, "_fetch_models", lambda: _live_catalogue())
    yield
    auto.reset()
    try:
        key_manager.delete_key("writer")
    except Exception:
        pass


# --------------------------------------------------------------------------- #
# Catalogue / ranking
# --------------------------------------------------------------------------- #
def test_catalogue_keeps_only_currently_free_text_chat_models():
    cat = auto.catalog()
    ids = {m.id for m in cat.models}
    assert cat.source == "live" and len(ids) == 3
    assert ids == {BEST, SECOND, THIRD}
    assert all(m.score > 0 for m in cat.models)
    assert cat.models[0].id == BEST          # largest context + structured output
    assert cat.models[0].supports_json
    assert cat.models[0].supports_tools


def test_ranking_prefers_new_large_context_model_and_penalises_previews():
    raw = [
        _model("vendor/tiny-preview:free", context_length=8192),
        _model("vendor/preview-stealth", context_length=262144,
               supported_parameters=["response_format", "tools", "temperature"]),
        _model("vendor/solid-70b:free", context_length=262144,
               supported_parameters=["response_format", "tools", "temperature"]),
    ]
    ranked = auto._rank(raw)
    assert ranked[0].id == "vendor/solid-70b:free"
    assert [m.id for m in ranked][-1] == "vendor/tiny-preview:free"


def test_real_openrouter_catalogue_shape_is_accepted():
    """The live /api/v1/models payload omits `request`, lists 4 endpoints and
    may carry Artificial Analysis benchmarks — parsing must tolerate all that."""
    real_free = {
        "id": "baidu/ernie-5.5-flash-preview:free",
        "canonical_slug": "baidu/ernie-5.5-flash-preview-20261110",
        "name": "Baidu: ERNIE-5.5-Flash-Preview (free)",
        "created": int(time.time()) - 86400 * 2,
        "context_length": 1024000,
        "architecture": {"modality": "text->text", "input_modalities": ["text"],
                         "output_modalities": ["text"], "tokenizer": "Other",
                         "instruct_type": None},
        "pricing": {"prompt": "0", "completion": "0"},
        "top_provider": {"context_length": 1024000,
                         "max_completion_tokens": 921600, "is_moderated": False},
        "supported_parameters": ["include_reasoning", "max_tokens", "reasoning",
                                 "response_format", "structured_outputs",
                                 "temperature", "tool_choice", "tools", "top_p"],
        "expiration_date": None,
        "endpoints": ["/api/v1/chat/completions", "/api/v1/completions",
                      "/api/v1/messages", "/api/v1/responses"],
        "benchmarks": {"artificial_analysis": {"intelligence_index": 60,
                                               "coding_index": None}},
    }
    real_paid = dict(real_free, id="baidu/ernie-light-dt-1.0-intl",
                     pricing={"prompt": "0.00000113", "completion": "0.00000394",
                              "input_cache_read": "0.000000113"})
    real_batch = dict(real_free, id="baidu/ernie-5.5-flash-preview:batch",
                      endpoints=["/api/v1/batches"])
    zero_price_preview = dict(real_free, id="vendor/zero-cost-preview",
                              pricing={"prompt": "0", "completion": "0"})
    hidden_charge = dict(real_free, id="vendor/hidden-charge:free",
                         pricing={"prompt": "0", "completion": "0",
                                  "request": "0.01"})
    assert auto._is_free_chat_model(real_free, time.time())
    # A $0 preview without the :free suffix can still demand a funded
    # OpenRouter account and produce HTTP 402; it is not a free variant.
    assert not auto._is_free_chat_model(zero_price_preview, time.time())
    assert not auto._is_free_chat_model(hidden_charge, time.time())
    assert not auto._is_free_chat_model(real_paid, time.time())
    assert not auto._is_free_chat_model(real_batch, time.time())
    ranked = auto._rank([real_free, real_paid, real_batch, zero_price_preview])
    assert ranked[0].id == real_free["id"]        # :free + benchmarks wins
    assert ranked[0].supports_json and ranked[0].supports_tools
    assert {m.id for m in ranked} == {real_free["id"]}


def test_quality_benchmark_bonus_breaks_a_metadata_tie():
    plain = _model("vendor/plain:free")
    bench = _model("vendor/benchmarked:free",
                   benchmarks={"artificial_analysis": {"intelligence_index": 60}})
    ranked = auto._rank([plain, bench])
    assert ranked[0].id == "vendor/benchmarked:free"
    assert ranked[0].score > ranked[1].score


def test_describe_is_json_safe_and_contains_no_credentials():
    payload = auto.describe()
    text = json.dumps(payload)
    assert payload["recommended"] == BEST
    assert payload["auto_model"] == OPENROUTER_AUTO_MODEL
    assert payload["count"] == 3 and payload["source"] == "live"
    assert all(m["free"] is True for m in payload["models"])
    assert "sk-or" not in text and "Bearer" not in text


def test_catalogue_failure_degrades_to_free_router_without_stale_slugs(monkeypatch):
    def boom():
        raise OSError("offline")
    monkeypatch.setattr(auto, "_fetch_models", boom)
    cat = auto.catalog()
    assert cat.source == "fallback" and cat.error and cat.models == ()
    res = auto.resolve(OPENROUTER_AUTO_MODEL)
    assert res.primary == OPENROUTER_FREE_ROUTER
    assert res.fallbacks == (OPENROUTER_FREE_ROUTER,)
    assert res.source == "fallback"
    payload = auto.describe()
    assert payload["recommended"] == OPENROUTER_FREE_ROUTER
    assert payload["recommended_label"] != OPENROUTER_FREE_ROUTER


def test_disabled_auto_never_calls_the_catalogue(monkeypatch):
    monkeypatch.setattr(auto, "settings", SimpleNamespace(
        openrouter_auto_enabled=False, openrouter_catalog_ttl=900,
        openrouter_catalog_timeout=5.0, openrouter_max_fallbacks=4))
    monkeypatch.setattr(auto, "_fetch_models",
                        lambda: pytest.fail("catalogue must not be queried"))
    res = auto.resolve(OPENROUTER_AUTO_MODEL)
    assert res.primary == OPENROUTER_FREE_ROUTER
    assert res.source == "disabled"


# --------------------------------------------------------------------------- #
# Resolution
# --------------------------------------------------------------------------- #
def test_auto_resolves_to_best_live_free_model_with_free_only_fallbacks():
    res = auto.resolve(OPENROUTER_AUTO_MODEL, json_mode=True, max_tokens=1600)
    assert res.auto and res.source == "live"
    assert res.primary == BEST
    assert res.fallbacks[0] == BEST
    assert res.json_supported is True
    assert all(m == OPENROUTER_FREE_ROUTER or m.endswith(":free")
               for m in res.fallbacks)
    assert OPENROUTER_FREE_ROUTER in res.fallbacks or len(res.fallbacks) >= 2


def test_free_router_mode_uses_openrouters_own_router_first():
    res = auto.resolve(OPENROUTER_FREE_ROUTER)
    assert res.primary == OPENROUTER_FREE_ROUTER
    assert res.fallbacks[0] == OPENROUTER_FREE_ROUTER
    assert BEST in res.fallbacks


def test_pinned_model_is_never_overridden():
    pinned = "vendor/beta-30b:free"
    res = auto.resolve(pinned, json_mode=True)
    assert res.auto is False and res.source == "pinned"
    assert res.primary == pinned and res.fallbacks == ()


def test_failed_model_is_cooled_down_and_skipped():
    auto.catalog()
    auto.note_failure(BEST, 404)
    res = auto.resolve(OPENROUTER_AUTO_MODEL)
    assert res.primary != BEST
    assert BEST not in res.candidates
    assert res.source == "live"


def test_max_tokens_filters_out_models_with_small_output_limits():
    res = auto.resolve(OPENROUTER_AUTO_MODEL, max_tokens=30000)
    assert res.primary == BEST    # only BEST declares 32768 output tokens
    assert SECOND not in res.fallbacks


def test_json_mode_prefers_a_structured_output_capable_model():
    res = auto.resolve(OPENROUTER_AUTO_MODEL, json_mode=True)
    assert res.primary == BEST and res.json_supported
    res2 = auto.resolve(OPENROUTER_AUTO_MODEL, json_mode=False)
    assert res2.primary == BEST


# --------------------------------------------------------------------------- #
# Provider registry / key safety
# --------------------------------------------------------------------------- #
def test_provider_catalogue_exposes_auto_as_default_and_labels():
    row = next(p for p in list_providers() if p["key"] == "openrouter_free")
    assert row["default_model"] == OPENROUTER_AUTO_MODEL
    assert row["auto_select"] is True
    assert OPENROUTER_AUTO_MODEL in row["models"]
    assert "best free" in row["model_labels"][OPENROUTER_AUTO_MODEL].lower()
    assert get_provider("openrouter_free").tier == "free"
    assert model_label("openrouter_free", OPENROUTER_AUTO_MODEL) != OPENROUTER_AUTO_MODEL


def test_free_provider_accepts_any_free_slug_but_rejects_paid_slugs():
    assert is_allowed_model("openrouter_free", OPENROUTER_AUTO_MODEL)
    assert is_allowed_model("openrouter_free", "future/model-99b:free")
    assert not is_allowed_model("openrouter_free", "anthropic/claude-sonnet-4.5")
    assert not is_allowed_model("openrouter_free", "vendor/paid-chat")
    assert not is_allowed_model("groq", "totally-made-up-model")


def test_retired_hard_coded_slugs_are_upgraded_to_auto():
    for old in OPENROUTER_LEGACY_MODELS:
        assert normalize_model("openrouter_free", old) == OPENROUTER_AUTO_MODEL
    # $0 previews and paid slugs saved by an older build are unsafe on a
    # free slot: they can trigger OpenRouter's funded-account 402 gate.
    assert normalize_model("openrouter_free", "vendor/zero-cost-preview") == OPENROUTER_AUTO_MODEL
    assert normalize_model("openrouter_free", "openai/gpt-4o") == OPENROUTER_AUTO_MODEL
    assert normalize_model("groq", OPENROUTER_LEGACY_MODELS[0]) == OPENROUTER_LEGACY_MODELS[0]


def test_save_key_stores_auto_and_normalizes_existing_legacy_models():
    for model in (OPENROUTER_AUTO_MODEL, OPENROUTER_LEGACY_MODELS[0]):
        key_manager.save_key("writer", "openrouter_free",
                             "test-dummy-key-openrouter-000111", model)
        creds = key_manager.get_credentials("writer")
        assert creds["model"] == OPENROUTER_AUTO_MODEL
        status = next(s for s in key_manager.key_status() if s["slot"] == "writer")
        assert status["model_label"].startswith("Auto")
        assert "test-dummy-key" not in status["masked_key"]
    # A paid slug submitted to the free provider is upgraded to the safe
    # auto selector rather than ever being sent to OpenRouter as-is.
    key_manager.save_key("writer", "openrouter_free",
                         "test-dummy-key-openrouter-000111", "openai/gpt-4o")
    assert key_manager.get_credentials("writer")["model"] == OPENROUTER_AUTO_MODEL


def test_blank_key_save_keeps_the_existing_encrypted_key():
    key_manager.save_key("writer", "groq", "gsk_test_dummy_key_000111",
                         "llama-3.3-70b-versatile")
    key_manager.save_key("writer", "groq", "", "gemma2-9b-it")
    creds = key_manager.get_credentials("writer")
    assert creds["api_key"] == "gsk_test_dummy_key_000111"
    assert creds["model"] == "gemma2-9b-it"


# --------------------------------------------------------------------------- #
# Router behaviour (mocked HTTP)
# --------------------------------------------------------------------------- #
def test_call_llm_sends_live_free_model_and_reports_openrouters_actual_model(monkeypatch):
    key_manager.save_key("writer", "openrouter_free",
                         "test-dummy-key-openrouter-000111", OPENROUTER_AUTO_MODEL)
    seen = []

    def post(url, *, headers, json, timeout):
        seen.append({"url": url, "headers": headers, "body": json})
        assert "openrouter.ai/api/v1/chat/completions" in url
        # A fallback can fire; OpenRouter returns the model that really served it.
        return _completion(SECOND, "A live answer")

    monkeypatch.setattr(llm_router.requests, "post", post)
    result = llm_router.call_llm("writer", "sys", "user", json_mode=True)

    body = seen[0]["body"]
    assert body["model"] == BEST
    assert body["models"] and all(m.endswith(":free") for m in body["models"])
    assert OPENROUTER_FREE_ROUTER not in body["models"]
    assert body["models"][0] == SECOND
    assert body["response_format"] == {"type": "json_object"}
    assert "Authorization" in seen[0]["headers"] and "HTTP-Referer" in seen[0]["headers"]
    assert result["text"] == "A live answer"
    assert result["model"] == SECOND                  # authoritative, not requested
    assert result["requested_model"] == OPENROUTER_AUTO_MODEL
    assert result["auto_selected"] and result["selection_source"] == "live"
    assert result["input_tokens"] == 10 and result["output_tokens"] == 4
    assert "x-ratelimit-remaining" in result["quota_headers"]


def test_call_llm_retries_retired_free_model_without_ever_billing(monkeypatch):
    key_manager.save_key("writer", "openrouter_free",
                         "test-dummy-key-openrouter-000111", OPENROUTER_AUTO_MODEL)
    bodies = []
    served = BEST

    def post(url, *, headers, json, timeout):
        bodies.append(json)
        if json["model"] == BEST:
            return FakeResponse(404, text='{"error":"No endpoints found"}')
        return _completion(json["model"], "Recovered on free model")

    monkeypatch.setattr(llm_router.requests, "post", post)
    result = llm_router.call_llm("writer", "sys", "user", json_mode=True)

    assert len(bodies) == 2
    assert bodies[0]["model"] == BEST and bodies[1]["model"] == SECOND
    for body in bodies:
        assert body["model"].endswith(":free")
        assert all(m == OPENROUTER_FREE_ROUTER or m.endswith(":free")
                   for m in body.get("models", []))
    assert result["model"] == SECOND and result["text"] == "Recovered on free model"
    assert served == BEST


def test_last_attempt_falls_back_to_openrouters_free_router(monkeypatch):
    key_manager.save_key("writer", "openrouter_free",
                         "test-dummy-key-openrouter-000111", OPENROUTER_AUTO_MODEL)
    bodies = []
    served = "vendor/zeta-20b:free"

    def post(url, *, headers, json, timeout):
        bodies.append(json)
        if json["model"] == OPENROUTER_FREE_ROUTER:
            return _completion(served, "Answered by the free router")
        return FakeResponse(429, text='{"error":"Rate limit exceeded"}')

    monkeypatch.setattr(llm_router.requests, "post", post)
    result = llm_router.call_llm("writer", "sys", "user")

    assert len(bodies) == 3
    assert bodies[0]["model"] == BEST and bodies[1]["model"] == SECOND
    assert bodies[2]["model"] == OPENROUTER_FREE_ROUTER
    assert "models" not in bodies[2]
    assert result["model"] == served and result["text"] == "Answered by the free router"


def test_auth_failure_is_not_retried_and_does_not_leak_the_key(monkeypatch):
    key_manager.save_key("writer", "openrouter_free",
                         "test-dummy-key-openrouter-000111", OPENROUTER_AUTO_MODEL)
    calls = []
    # Built at runtime so no credential-shaped literal is committed.
    fake_secret = "sk-" + "or-v1-" + "testvalue123"

    def post(url, *, headers, json, timeout):
        calls.append(json)
        return FakeResponse(401, text="invalid api key " + fake_secret)

    monkeypatch.setattr(llm_router.requests, "post", post)
    with pytest.raises(llm_router.LLMError) as exc:
        llm_router.call_llm("writer", "sys", "user")
    assert len(calls) == 1
    assert "testvalue123" not in str(exc.value)
    assert fake_secret not in str(exc.value)
    assert exc.value.category == "authentication"
    assert "testvalue123" not in (exc.value.provider_message or "")


def test_openrouter_402_is_actionable_and_never_dumps_raw_billing_json(monkeypatch):
    key_manager.save_key("writer", "openrouter_free",
                         "test-dummy-key-openrouter-000111", OPENROUTER_AUTO_MODEL)
    calls = []
    raw = json.dumps({"error": {
        "message": "Insufficient credits. This account never purchased credits.",
        "code": 402,
        "metadata": {"limit_source": "openrouter_credits",
                     "remedy_hint": "Add credits at https://openrouter.ai/settings/credits"},
    }})

    def post(url, *, headers, json, timeout):
        calls.append(json)
        return FakeResponse(402, text=raw)

    monkeypatch.setattr(llm_router.requests, "post", post)
    with pytest.raises(llm_router.LLMError) as exc:
        llm_router.call_llm("writer", "sys", "user")

    # A billing/account gate is not retried against every free model, and the
    # UI receives a concise explanation rather than nested provider JSON.
    assert len(calls) == 1
    assert exc.value.status == 402
    assert exc.value.category == "openrouter_credit_gate"
    assert ":free" in str(exc.value) and "per-key credit limit" in str(exc.value)
    assert "limit_source" not in str(exc.value) and "remedy_hint" not in str(exc.value)
    assert "openrouter.ai/settings/credits" not in str(exc.value)


def test_pinned_free_model_reaches_openrouter_unchanged(monkeypatch):
    pinned = "vendor/beta-30b:free"
    key_manager.save_key("writer", "openrouter_free",
                         "test-dummy-key-openrouter-000111", pinned)
    seen = []

    def post(url, *, headers, json, timeout):
        seen.append(json)
        return _completion(pinned)

    monkeypatch.setattr(llm_router.requests, "post", post)
    result = llm_router.call_llm("writer", "sys", "user")
    assert seen[0]["model"] == pinned and "models" not in seen[0]
    assert result["auto_selected"] is False and result["model"] == pinned


def test_offline_auto_request_never_sends_a_stale_fallback_chain(monkeypatch):
    monkeypatch.setattr(auto, "_fetch_models", lambda: (_ for _ in ()).throw(
        OSError("offline")))
    auto.reset()
    key_manager.save_key("writer", "openrouter_free",
                         "test-dummy-key-openrouter-000111", OPENROUTER_AUTO_MODEL)
    seen = []

    def post(url, *, headers, json, timeout):
        seen.append(json)
        return _completion(OPENROUTER_FREE_ROUTER)

    monkeypatch.setattr(llm_router.requests, "post", post)
    result = llm_router.call_llm("writer", "sys", "user")
    assert seen[0]["model"] == OPENROUTER_FREE_ROUTER
    assert "models" not in seen[0]
    assert result["model"] == OPENROUTER_FREE_ROUTER
    assert result["selection_source"] == "fallback"


def test_response_format_omitted_when_best_free_model_lacks_json_support(monkeypatch):
    weak = "vendor/no-json:free"
    monkeypatch.setattr(auto, "_fetch_models", lambda: [
        _model(weak, supported_parameters=["temperature", "max_tokens"])])
    auto.reset()
    key_manager.save_key("writer", "openrouter_free",
                         "test-dummy-key-openrouter-000111", OPENROUTER_AUTO_MODEL)
    seen = []

    def post(url, *, headers, json, timeout):
        seen.append(json)
        return _completion(weak)

    monkeypatch.setattr(llm_router.requests, "post", post)
    llm_router.call_llm("writer", "sys", "user", json_mode=True)
    assert "response_format" not in seen[0]


# --------------------------------------------------------------------------- #
# HTTP API
# --------------------------------------------------------------------------- #
def test_settings_endpoint_exposes_live_free_catalogue():
    with TestClient(app) as c:
        data = c.get("/api/settings/openrouter/models").json()
        assert data["provider"] == "openrouter_free" and data["enabled"]
        assert data["source"] == "live" and data["count"] == 3
        assert data["recommended"] == BEST
        assert all(m["free"] for m in data["models"])
        assert "sk-or" not in json.dumps(data)
        refreshed = c.get("/api/settings/openrouter/models?refresh=true").json()
        assert refreshed["recommended"] == BEST


def test_provider_catalogue_endpoint_advertises_auto_mode():
    with TestClient(app) as c:
        rows = c.get("/api/providers").json()
        row = next(r for r in (rows if isinstance(rows, list) else rows["providers"])
                   if r["key"] == "openrouter_free")
        assert row["auto_select"] is True
        assert row["default_model"] == OPENROUTER_AUTO_MODEL
