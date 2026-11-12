# Contributing to Meridian

Thank you for helping make Meridian better. This project is a BCA minor project
built to enterprise standards, and thoughtful contributions are very welcome.

**Developed by Mridul Sharma**

---

## Getting set up

```bash
git clone https://github.com/MridulSharma570/Meridian.git
cd Meridian
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env               # optional
python run.py                      # http://localhost:8000
pytest -q                          # must be green before you open a PR
```

## Repository layout

| Path | Responsibility |
|------|----------------|
| `app/api/server.py` | FastAPI routes, static SPA, SSE streaming |
| `app/services.py` | All product behaviour (jobs, chat, exports, settings) |
| `app/agents/` | Six agents + translator + orchestrator |
| `app/data_sources/` | Live connectors and deterministic offline engine |
| `app/export/` | PDF / PowerPoint / Excel generators |
| `app/database/` | SQLAlchemy models, sessions, CRUD |
| `app/web/` | Premium SPA (`index.html`, `app.css`, `app.js`) |
| `app/ui/` | Streamlit theme, components and pages |
| `tests/` | Pytest suite (isolated temporary database) |
| `docs/` | Architecture, API, deployment, guides |

## Code style

- **PEP 8**, 100-character lines, 4-space indentation, type hints on public functions.
- `from __future__ import annotations` at the top of every module.
- Every external call gets a timeout and a try/except with a useful message.
- **An agent or connector must never crash a report.** Wrap it in an isolation
  boundary and return a usable fallback (see `app/agents/base.py`).
- No `TODO`, no placeholder returns, no bare `except:`.
- Never log, print or persist an API key in plaintext. Use `app/api/key_manager.py`.
- Frontend code stays dependency-free: no build step, no CDN JS, relative `/api` URLs only.

## Adding a provider

1. Add a `Provider(...)` entry to `app/api/providers.py` with `base_url`,
   `models`, `api_style` and `signup_url`.
2. If its wire format differs, extend `_endpoint`, `_headers`, `_payload` and
   `_extract` in `app/api/llm_router.py`.
3. Add the setup steps to `docs/API_KEYS_SETUP.md`.
4. Add a case to `tests/test_api_router.py`.

## Pull request process

1. Create a branch from `main`: `git checkout -b feature/your-change`.
2. Keep commits atomic and descriptive (`Add Cohere quota parsing`).
3. Run `pytest -q` and `python -m compileall app` locally.
4. Update `CHANGELOG.md` under **Unreleased**.
5. Open a PR with: what changed, why, how you tested it, and a screenshot for UI work.
6. One approval is required. CI (tests + import smoke check) must pass.

## Reporting bugs

Open an issue with the exact steps, the endpoint or view, the full error text
(never include an API key), your OS/Python version, and your `data_mode`
(simulated / hybrid / live). Security issues go through [SECURITY.md](SECURITY.md),
not public issues.
