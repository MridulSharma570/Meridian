#!/usr/bin/env python3
"""External keep-alive pinger for Render Free (and similar idle-spinning hosts).

Run this from a scheduler OUTSIDE the app — GitHub Actions, cron-job.org,
UptimeRobot or any cron. It must be external: when Render spins a free service
down, every thread inside it disappears too.

    RENDER_APP_URL=https://meridian.onrender.com python scripts/keepalive.py

It retries patiently because a sleeping instance can take ~60 s to spin back
up. Uses only the Python standard library, so it needs no install step.

Developed by Mridul Sharma
"""
from __future__ import annotations

import os
import sys
import time
import urllib.error
import urllib.request

DEFAULT_ATTEMPTS = 8
DEFAULT_BACKOFF = 12          # seconds between attempts
REQUEST_TIMEOUT = 25         # seconds per attempt (Render cold start ~60 s total)


def normalise_url(raw: str) -> str:
    """Accept a bare host, an http(s) URL or a URL that already has a path."""
    value = (raw or "").strip().rstrip("/")
    if not value:
        raise ValueError("Set RENDER_APP_URL (or MERIDIAN_URL) to your public app URL")
    if not value.startswith(("http://", "https://")):
        value = "https://" + value
    if value.endswith(("/api/ping", "/api/health")):
        return value
    return value + "/api/ping"


def ping_once(url: str, timeout: int = REQUEST_TIMEOUT) -> tuple[bool, str]:
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Meridian-KeepAlive/1.0",
                 "Cache-Control": "no-cache", "Accept": "application/json"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read(256).decode("utf-8", "replace")
            ok = 200 <= resp.status < 300
            return ok, f"HTTP {resp.status} · {body[:100]}"
    except urllib.error.HTTPError as exc:
        return False, f"HTTP {exc.code}"
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"


def main() -> int:
    raw = os.getenv("RENDER_APP_URL") or os.getenv("MERIDIAN_URL") or ""
    try:
        url = normalise_url(raw)
    except ValueError as exc:
        print(f"✗ {exc}", file=sys.stderr)
        return 2

    attempts = int(os.getenv("KEEPALIVE_ATTEMPTS", str(DEFAULT_ATTEMPTS)))
    backoff = int(os.getenv("KEEPALIVE_BACKOFF", str(DEFAULT_BACKOFF)))
    print(f"◆ Meridian keep-alive → {url}")
    for i in range(1, attempts + 1):
        ok, detail = ping_once(url)
        print(f"  attempt {i}/{attempts}: {detail}")
        if ok:
            print("✓ Service is awake and healthy")
            return 0
        if i < attempts:
            time.sleep(backoff)
    print("✗ Service did not respond; check the Render deploy logs", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
