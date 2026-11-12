# API Keys Setup — every provider, step by step

**Meridian v1.0.0 · Developed by Mridul Sharma**

> You do **not** need any of these to use Meridian. With no keys the full
> seven-agent pipeline runs on the local analytical engine. Add keys only when
> you want live LLM-written analysis, full neural translation or real data feeds.
>
> Enter keys in **Settings → API Keys** (web app) or **API Keys** (Streamlit).
> Each of the six agents has its own slot; the Translator is optional and
> inherits the Writer's key when unset. Use **Quick setup** to put one key in
> every slot.

---

## Quick comparison

| Provider | Tier | Free allowance | Best for |
|----------|------|----------------|----------|
| Groq | FREE | Generous rate limits | Fastest inference, great default |
| Google Gemini | FREE | Free tier | Multimodal, huge context |
| OpenRouter (Free) | FREE | Free model catalogue | Trying many models |
| Hugging Face | FREE | Inference credits | Open-source models |
| Cohere (Trial) | FREE | Trial key | Command-R |
| Cerebras | FREE | Free tier | Very fast Llama |
| Ollama | FREE | Local, no key | Fully offline LLM |
| OpenAI | PAID | — | GPT-4o quality |
| Anthropic | PAID | — | Claude 3.5 |
| Gemini Pro | PAID | — | Long-context reasoning |
| Mistral / Perplexity / Together / Fireworks / DeepSeek | PAID | — | Specialist models |

---

## FREE providers

### 1. Groq ⭐ recommended
1. Go to **https://console.groq.com/keys** and sign in with Google/GitHub.
2. Click **Create API Key**, give it a name, copy the `gsk_…` value.
3. In Meridian: provider `Groq`, model `llama-3.3-70b-versatile`, paste the key.
4. Press **Test connection** — expect a sub-second response.
Groq exposes rate-limit headers, which Meridian stores as quota info after a test.

### 2. Google Gemini (free)
1. Visit **https://aistudio.google.com/app/apikey**.
2. Sign in with a Google account → **Create API key** → copy `AIza…`.
3. Select `Google Gemini` and model `gemini-2.0-flash`.
Meridian calls Gemini through its OpenAI-compatible endpoint.

### 3. OpenRouter (Free)
1. Sign up at **https://openrouter.ai/** → **https://openrouter.ai/keys**.
2. Create a key (`sk-or-v1-…`) — no card needed for free models.
3. Choose `OpenRouter (Free)` and `meta-llama/llama-3-8b-instruct:free`.
4. Check your remaining credits at https://openrouter.ai/activity.

### 4. Hugging Face
1. Create an account → **https://huggingface.co/settings/tokens**.
2. New token, **Read** scope, copy `hf_…`.
3. Choose `Hugging Face` and `Qwen/Qwen2.5-72B-Instruct`.
Note: cold model starts can take 20–60 s; Meridian falls back to the local
engine if the request times out.

### 5. Cohere (Trial)
1. **https://dashboard.cohere.com/api-keys** → sign up → copy the trial key.
2. Choose `Cohere (Trial)` and `command-r`.
Meridian uses Cohere's native v2 chat wire format.

### 6. Cerebras
1. **https://cloud.cerebras.ai/** → sign in → API Keys → create.
2. Choose `Cerebras` and `llama-3.1-70b`.

### 7. Ollama (local, no key)
1. Install from **https://ollama.com/** and run `ollama pull llama3.1`.
2. Start the server (`ollama serve`, default `:11434`).
3. Choose `Ollama (Local)` and `llama3.1`. The key field may be left blank.
> In a container, `localhost` refers to the container — use
> `http://host.docker.internal:11434/v1` via a custom provider base URL.

---

## PAID providers

| Provider | Where to get the key | Default model |
|----------|---------------------|---------------|
| OpenAI | https://platform.openai.com/api-keys | `gpt-4o-mini` |
| Anthropic | https://console.anthropic.com/settings/keys | `claude-3-5-sonnet-20241022` |
| OpenRouter (Paid) | https://openrouter.ai/keys (add credits) | `anthropic/claude-3.5-sonnet` |
| Google Gemini Pro | https://aistudio.google.com/app/apikey (billing enabled) | `gemini-1.5-pro` |
| Mistral AI | https://console.mistral.ai/api-keys | `mistral-large-latest` |
| Perplexity | https://www.perplexity.ai/settings/api | `pplx-70b-online` |
| Together AI | https://api.together.ai/settings/api-keys | `meta-llama/Llama-3.3-70B-Instruct-Turbo` |
| Fireworks AI | https://fireworks.ai/account/api-keys | `accounts/fireworks/models/llama-v3p1-70b-instruct` |
| DeepSeek | https://platform.deepseek.com/api_keys | `deepseek-chat` |

For each: create the key, set a spend limit, copy it once, then paste it into
the relevant agent slot in Meridian and press **Save key** → **Test connection**.

---

## Live data connectors (environment variables, not per-agent slots)

These go in `.env` (see [`.env.example`](../.env.example)) rather than Settings:

| Variable | Get it at | Enables |
|----------|-----------|---------|
| `TAVILY_API_KEY` | https://tavily.com/ (free tier) | Real web search results |
| `NEWS_API_KEY` | https://newsapi.org/register | Live news articles |
| `MERIDIAN_WORLD_BANK` | no key | World Bank macro indicators |
| `MERIDIAN_USE_YFINANCE` | no key | Yahoo Finance chart fallback |
| `MERIDIAN_LIVE_DATA` | `false` to disable all | Air-gapped operation |

DuckDuckGo HTML search, Reddit public JSON and the World Bank API are attempted
without keys; if the network blocks them, Meridian continues offline.

Example `.env`:
```env
TAVILY_API_KEY=tvly-xxxxxxxxxxxx
NEWS_API_KEY=xxxxxxxxxxxxxxxxxxxxxxxx
MERIDIAN_LIVE_DATA=true
```

Restart the server after editing `.env`. The data-mode badge changes to
`HYBRID` or `LIVE` when connectors start succeeding.

---

## Recommended configurations

**Zero-cost demo (best for evaluators)**
> Quick setup → `Groq` → one `gsk_…` key in all seven slots.
> Add `TAVILY_API_KEY` for live sources.

**Mixed providers (shows independence)**
| Slot | Provider | Model |
|------|----------|-------|
| Researcher | Perplexity | `pplx-70b-online` |
| Analyst | OpenAI | `gpt-4o` |
| Writer | Anthropic | `claude-3-5-sonnet` |
| Chat | Groq | `llama-3.3-70b-versatile` |
| Forecast | Gemini Pro | `gemini-1.5-pro` |
| Fact-Checker | OpenRouter (Paid) | `openai/gpt-4o` |
| Translator | Gemini | `gemini-2.0-flash` |

**Fully offline**
> Leave all slots empty, set `MERIDIAN_LIVE_DATA=false`, optionally point
> one slot at Ollama. Everything still works.

---

## Security

- Keys are encrypted with **Fernet** *before* the database write; only masked
  values are shown in the UI.
- `data/.fernet_key` is created with mode `0600` and is gitignored. Set a stable
  `MERIDIAN_FERNET_KEY` in production (see [SECURITY.md](../SECURITY.md)).
- **Never paste a real key into a chat message, issue, screenshot or commit.**
  Rotate immediately if one leaks.
- `Test connection` sends only the literal probe text `Reply with exactly: OK`.

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `No key saved in this slot` | Press **Save key** before **Test connection** |
| `HTTP 401` | Key is wrong/expired; regenerate at the provider |
| `HTTP 429` | Quota or rate limit; wait or switch to a free provider |
| `timed out` | Network blocked or model cold-starting; the local engine already completed the agent |
| `returned unusable output` | Model ignored JSON mode; Meridian kept the local analysis |
| `Empty key for Ollama` | Ollama needs no key; leave the field blank on save |
| `Stored credential could not be decrypted` | Fernet key changed — re-enter keys in Settings |

See [TROUBLESHOOTING.md](TROUBLESHOOTING.md) for the full list.
