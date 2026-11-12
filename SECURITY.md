# Security Policy

**Meridian — Market Intelligence, Redefined.** · Developed by Mridul Sharma

## Supported versions

| Version | Supported |
|---------|-----------|
| 1.0.x   | ✅ |
| < 1.0   | ❌ |

## Reporting a vulnerability

Please **do not open a public issue** for security problems. Report privately
through GitHub's "Report a vulnerability" button on the repository Security tab,
or contact the maintainer directly via a private GitHub message. Include:

- the affected component / endpoint,
- reproduction steps and a proof of concept,
- the impact you believe it has,
- **never include a real API key, token or password in the report.**

You will receive an acknowledgement within 7 days and a fix or mitigation plan
within 30 days for confirmed issues.

## API key handling policy

Meridian is designed around a BYOK (bring your own key) model:

1. Keys are entered only in the **Settings → API Keys** page and sent over the
   same origin as the app (`POST /api/settings/keys`).
2. They are encrypted with **Fernet** (AES-128-CBC + HMAC-SHA256) *before* any
   database write. The plaintext key exists only in process memory for the
   duration of a provider call.
3. Only **masked** values (`gsk_T••••••••7890`) are ever returned by the API or
   rendered in a UI. `/api/settings` never exposes ciphertext.
4. The Fernet key comes from `MERIDIAN_FERNET_KEY` or a local file created with
   mode `0600`. It is **never committed** (see `.gitignore`).
5. Keys are never written to logs, reports, exports, error messages or the
   browser's local storage. `app/api/llm_router.py` redacts key-shaped strings
   from provider errors.
6. `data/`, `.env`, `*.db` and `*.fernet_key` are excluded from Git.
7. If a key is accidentally exposed, **rotate it at the provider immediately**,
   remove the slot in Settings, and delete `data/.fernet_key` to force a new key.

## Deployment notes

- Always serve over HTTPS in production; the app itself has no authentication
  layer and is intended for a trusted/local/demo environment. Put it behind your
  organisation's SSO, reverse proxy or VPN.
- Set a stable `MERIDIAN_FERNET_KEY` from a secret manager. Losing it makes
  stored keys undecryptable — they must be re-entered in Settings.
- Use a least-privilege database account; do not expose PostgreSQL or Redis
  ports publicly.
- Live connectors use short timeouts and never receive your LLM keys.

## Out of scope

Reports generated in explicit `sample` data mode are deterministic demo data, not verified
financial facts. See the `confidence_note` and the Fact-Checker's ⚠️ flags before
any external or investment use.
