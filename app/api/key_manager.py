"""Encrypted API-key vault.

Keys are encrypted with Fernet (AES-128-CBC + HMAC) *before* they reach the
database. The Fernet key comes from ``MERIDIAN_FERNET_KEY`` or from a local
0600 file that is never committed. Decrypted values never leave this module
except through :func:`get_credentials`, which is used only by the LLM router.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from cryptography.fernet import Fernet, InvalidToken

from app.api.providers import get_provider
from app.config import settings
from app.database import queries

logger = logging.getLogger("meridian.keys")

_cipher: Optional[Fernet] = None


def _load_fernet_key() -> bytes:
    env = settings.fernet_key.strip()
    if env:
        try:
            Fernet(env.encode())
            return env.encode()
        except Exception as exc:
            raise RuntimeError("MERIDIAN_FERNET_KEY is not a valid Fernet key") from exc

    path: Path = settings.fernet_key_file
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            raw = path.read_bytes().strip()
            if raw:
                Fernet(raw)
                return raw
        key = Fernet.generate_key()
        # Write atomically with restrictive permissions.
        tmp = path.with_suffix(".tmp")
        fd = os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "wb") as fh:
            fh.write(key)
        os.replace(str(tmp), str(path))
        os.chmod(str(path), 0o600)
        return key
    except OSError as exc:
        raise RuntimeError(f"Unable to initialise encryption key file: {exc}") from exc


def get_cipher() -> Fernet:
    global _cipher
    if _cipher is None:
        _cipher = Fernet(_load_fernet_key())
    return _cipher


def encrypt(plaintext: str) -> str:
    if not plaintext:
        raise ValueError("Cannot encrypt an empty key")
    return get_cipher().encrypt(plaintext.encode()).decode()


def decrypt(ciphertext: str) -> str:
    try:
        return get_cipher().decrypt(ciphertext.encode()).decode()
    except (InvalidToken, ValueError) as exc:
        raise ValueError("Stored credential could not be decrypted. "
                         "Re-enter the key in Settings.") from exc


def mask(secret: str) -> str:
    if not secret:
        return "—"
    s = secret.strip()
    if len(s) <= 10:
        return s[:2] + "••••"
    return f"{s[:5]}••••••••{s[-4:]}"


def save_key(agent_name: str, provider: str, api_key: str, model: str = "",
             is_active: bool = True) -> Dict[str, Any]:
    """Validate, encrypt and persist a key for one of the six agent slots."""
    from app.config import AGENT_SLOTS
    if agent_name not in {slot[0] for slot in AGENT_SLOTS}:
        raise ValueError(f"Unknown agent slot: {agent_name}")
    p = get_provider(provider)
    clean = (api_key or "").strip()
    if not clean and provider != "ollama":
        raise ValueError("API key cannot be empty")
    effective_model = model or p.default_model
    if effective_model not in p.models and p.models:
        effective_model = p.default_model
    token = encrypt(clean) if clean else encrypt("local-no-key-required")
    return queries.upsert_api_key(agent_name, provider, token, effective_model, is_active)


def get_credentials(agent_name: str) -> Optional[Dict[str, Any]]:
    """Return decrypted config for internal use only."""
    row = queries.get_api_key_row(agent_name)
    if row is None or not row["is_active"]:
        return None
    try:
        secret = decrypt(row["encrypted"])
    except ValueError:
        logger.warning("Undecryptable key for %s", agent_name)
        return None
    if secret == "local-no-key-required":
        secret = ""
    p = get_provider(row["provider"])
    return {
        "provider": row["provider"], "model": row["model"] or p.default_model,
        "api_key": secret, "spec": p,
    }


def key_status() -> List[Dict[str, Any]]:
    """Safe, masked view for the UI — never returns plaintext."""
    from app.config import AGENT_SLOTS
    rows = {r["agent_name"]: r for r in queries.list_api_key_rows()}
    out = []
    for slot, label, icon, desc in AGENT_SLOTS:
        r = rows.get(slot)
        if r:
            try:
                plain = decrypt(r["encrypted"])
            except ValueError:
                plain = ""
            out.append({
                "slot": slot, "name": label, "icon": icon, "description": desc,
                "configured": True, "masked_key": mask(plain),
                "provider": r["provider"], "model": r["model"],
                "is_active": r["is_active"], "quota_info": r["quota_info"],
                "last_tested_at": r["last_tested_at"], "last_test_ok": r["last_test_ok"],
            })
        else:
            out.append({
                "slot": slot, "name": label, "icon": icon, "description": desc,
                "configured": False, "masked_key": "—", "provider": "",
                "model": "", "is_active": False, "quota_info": None,
                "last_tested_at": None, "last_test_ok": None,
            })
    return out


def delete_key(agent_name: str) -> bool:
    return queries.delete_api_key(agent_name)


def apply_to_all(provider: str, api_key: str, model: str = "") -> int:
    """Convenience: put one key into every slot (fully supported)."""
    from app.config import AGENT_SLOTS
    for slot, *_ in AGENT_SLOTS:
        save_key(slot, provider, api_key, model)
    return len(AGENT_SLOTS)
