"""Provider registry for every supported LLM vendor.

Each provider exposes an OpenAI-compatible (or close) chat-completions
endpoint. The router normalises the differences so agents never care which
vendor is behind a key slot.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Tuple


@dataclass(frozen=True)
class Provider:
    key: str
    label: str
    tier: str                 # "free" | "paid"
    base_url: str
    default_model: str
    models: Tuple[str, ...]
    api_style: str = "openai"  # openai | anthropic | gemini | cohere
    key_hint: str = ""
    signup_url: str = ""
    quota_supported: bool = False
    headers: Dict[str, str] = field(default_factory=dict)

    @property
    def group(self) -> str:
        return "FREE" if self.tier == "free" else "PAID"


_PROVIDERS: List[Provider] = [
    Provider("groq", "Groq", "free", "https://api.groq.com/openai/v1",
             "llama-3.3-70b-versatile",
             ("llama-3.3-70b-versatile", "mixtral-8x7b-32768", "gemma2-9b-it"),
             key_hint="gsk_…", signup_url="https://console.groq.com/keys", quota_supported=True),
    Provider("gemini", "Google Gemini", "free", "https://generativelanguage.googleapis.com/v1beta/openai",
             "gemini-2.0-flash",
             ("gemini-2.0-flash", "gemini-1.5-flash", "gemini-1.5-flash-8b"),
             key_hint="AIza…", signup_url="https://aistudio.google.com/app/apikey"),
    Provider("openrouter_free", "OpenRouter (Free)", "free", "https://openrouter.ai/api/v1",
             "meta-llama/llama-3-8b-instruct:free",
             ("meta-llama/llama-3-8b-instruct:free", "mistralai/mistral-7b-instruct:free"),
             key_hint="sk-or-v1-…", signup_url="https://openrouter.ai/keys", quota_supported=True),
    Provider("huggingface", "Hugging Face", "free", "https://api-inference.huggingface.co/v1",
             "Qwen/Qwen2.5-72B-Instruct",
             ("Qwen/Qwen2.5-72B-Instruct", "mistralai/Mistral-7B-Instruct-v0.3"),
             key_hint="hf_…", signup_url="https://huggingface.co/settings/tokens"),
    Provider("cohere", "Cohere (Trial)", "free", "https://api.cohere.com/v2",
             "command-r", ("command-r", "command-r-plus"), api_style="cohere",
             key_hint="…", signup_url="https://dashboard.cohere.com/api-keys"),
    Provider("cerebras", "Cerebras", "free", "https://api.cerebras.ai/v1",
             "llama-3.1-70b", ("llama-3.1-70b", "llama3.1-8b"),
             key_hint="csk_…", signup_url="https://cloud.cerebras.ai/"),
    Provider("openai", "OpenAI", "paid", "https://api.openai.com/v1",
             "gpt-4o-mini", ("gpt-4o", "gpt-4o-mini", "gpt-4-turbo"),
             key_hint="sk-…", signup_url="https://platform.openai.com/api-keys", quota_supported=True),
    Provider("anthropic", "Anthropic", "paid", "https://api.anthropic.com/v1",
             "claude-3-5-sonnet-20241022",
             ("claude-3-5-sonnet-20241022", "claude-3-haiku-20240307"),
             api_style="anthropic", key_hint="sk-ant-…",
             signup_url="https://console.anthropic.com/settings/keys"),
    Provider("openrouter_paid", "OpenRouter (Paid)", "paid", "https://openrouter.ai/api/v1",
             "anthropic/claude-3.5-sonnet",
             ("anthropic/claude-3.5-sonnet", "openai/gpt-4o", "google/gemini-1.5-pro"),
             key_hint="sk-or-v1-…", signup_url="https://openrouter.ai/keys", quota_supported=True),
    Provider("gemini_pro", "Google Gemini Pro", "paid",
             "https://generativelanguage.googleapis.com/v1beta/openai",
             "gemini-1.5-pro", ("gemini-1.5-pro", "gemini-2.0-flash-thinking-exp"),
             key_hint="AIza…", signup_url="https://aistudio.google.com/app/apikey"),
    Provider("mistral", "Mistral AI", "paid", "https://api.mistral.ai/v1",
             "mistral-large-latest",
             ("mistral-large-latest", "mistral-medium-latest", "open-mistral-nemo"),
             key_hint="…", signup_url="https://console.mistral.ai/api-keys"),
    Provider("perplexity", "Perplexity", "paid", "https://api.perplexity.ai",
             "pplx-70b-online", ("pplx-70b-online", "sonar", "sonar-pro"),
             key_hint="pplx-…", signup_url="https://www.perplexity.ai/settings/api"),
    Provider("together", "Together AI", "paid", "https://api.together.xyz/v1",
             "meta-llama/Llama-3.3-70B-Instruct-Turbo",
             ("meta-llama/Llama-3.3-70B-Instruct-Turbo", "mistralai/Mixtral-8x22B-Instruct-v0.1"),
             key_hint="…", signup_url="https://api.together.ai/settings/api-keys"),
    Provider("fireworks", "Fireworks AI", "paid", "https://api.fireworks.ai/inference/v1",
             "accounts/fireworks/models/llama-v3p1-70b-instruct",
             ("accounts/fireworks/models/llama-v3p1-70b-instruct",
              "accounts/fireworks/models/mixtral-8x7b-instruct"),
             key_hint="…", signup_url="https://fireworks.ai/account/api-keys"),
    Provider("deepseek", "DeepSeek", "paid", "https://api.deepseek.com/v1",
             "deepseek-chat", ("deepseek-chat", "deepseek-reasoner"),
             key_hint="sk-…", signup_url="https://platform.deepseek.com/api_keys"),
    Provider("ollama", "Ollama (Local)", "free", "http://localhost:11434/v1",
             "llama3.1", ("llama3.1", "mistral", "phi3"),
             key_hint="no key required", signup_url="https://ollama.com/"),
]

PROVIDERS: Dict[str, Provider] = {p.key: p for p in _PROVIDERS}


def list_providers() -> List[dict]:
    """Serialisable provider catalogue for the settings UI."""
    return [
        {
            "key": p.key, "label": p.label, "group": p.group, "tier": p.tier,
            "models": list(p.models), "default_model": p.default_model,
            "key_hint": p.key_hint, "signup_url": p.signup_url,
            "quota_supported": p.quota_supported, "base_url": p.base_url,
        }
        for p in _PROVIDERS
    ]


def get_provider(key: str) -> Provider:
    p = PROVIDERS.get(key)
    if p is None:
        raise ValueError(f"Unknown provider: {key!r}")
    return p


def free_providers() -> List[Provider]:
    return [p for p in _PROVIDERS if p.tier == "free"]


def paid_providers() -> List[Provider]:
    return [p for p in _PROVIDERS if p.tier == "paid"]
