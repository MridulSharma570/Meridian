#!/usr/bin/env python3
"""Container HEALTHCHECK probe.

Uses the same ``PORT`` resolution as the entrypoint, so it works both locally
(8000) and on Render (10000). Hits ``/api/ping``, which does no database work.

    python -m scripts.healthcheck   # exit 0 = healthy, 1 = unhealthy
"""
from __future__ import annotations

import os
import sys
import urllib.request


def probe() -> bool:
    port = os.getenv("PORT") or os.getenv("MERIDIAN_PORT") or "8000"
    url = f"http://127.0.0.1:{port}/api/ping"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Meridian-Healthcheck/1.0"})
        with urllib.request.urlopen(req, timeout=4) as resp:
            return 200 <= resp.status < 300
    except Exception as exc:
        print(f"healthcheck failed: {exc}", file=sys.stderr)
        return False


if __name__ == "__main__":
    raise SystemExit(0 if probe() else 1)
