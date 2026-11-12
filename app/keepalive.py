"""Optional in-process keep-alive watchdog for idle-spinning PaaS hosts.

IMPORTANT — read before enabling:
Render's Free plan spins the whole *process* down after 15 minutes without
inbound traffic. A thread inside that process cannot wake it once it is gone.
This watchdog is therefore **defence in depth only**: while Meridian is running
it generates a steady trickle of real inbound HTTP requests through the public
URL, which reduces the chance that a slightly-late external cron ping leaves a
15-minute idle gap. An external pinger (GitHub Actions / UptimeRobot) is still
required, and a paid Render plan is the only guaranteed always-on fix.

Disabled by default. Enable with MERIDIAN_SELF_PING_URL=https://your-app.onrender.com
"""
from __future__ import annotations

import logging
import threading
import urllib.request
from typing import Optional

from app.config import settings

logger = logging.getLogger("meridian.keepalive")


class KeepAlive:
    """Daemon-thread pinger with graceful start/stop."""

    def __init__(self, url: str = "", interval_s: int = 600, timeout_s: float = 8.0):
        self.url = (url or "").rstrip("/")
        self.interval_s = max(60, int(interval_s or 600))
        self.timeout_s = timeout_s
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self.successes = 0
        self.failures = 0

    @property
    def enabled(self) -> bool:
        return bool(self.url)

    @property
    def target(self) -> str:
        return f"{self.url}/api/ping" if self.url else ""

    def ping_once(self) -> bool:
        """Send one request. Never raises — network problems are non-fatal."""
        if not self.enabled:
            return False
        req = urllib.request.Request(
            self.target,
            headers={"User-Agent": "Meridian-KeepAlive/1.0",
                     "Cache-Control": "no-cache"},
            method="GET",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:
                resp.read(256)
                ok = 200 <= resp.status < 300
        except Exception as exc:
            logger.debug("Keep-alive ping failed: %s", exc)
            ok = False
        if ok:
            self.successes += 1
        else:
            self.failures += 1
        return ok

    def _loop(self) -> None:
        # Stagger the first ping so it never competes with startup/health checks.
        while not self._stop.wait(min(self.interval_s, 30)):
            if self._stop.is_set():
                return
            self.ping_once()

    def start(self) -> bool:
        if not self.enabled or (self._thread and self._thread.is_alive()):
            return False
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True,
                                        name="meridian-keepalive")
        self._thread.start()
        logger.info("Keep-alive enabled → %s every %ss (external pinger still required)",
                    self.target, self.interval_s)
        return True

    def stop(self) -> None:
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2)

    def status(self) -> dict:
        return {"enabled": self.enabled, "interval_s": self.interval_s,
                "target": self.target, "successes": self.successes,
                "failures": self.failures}


_watchdog = KeepAlive(settings.self_ping_url, settings.self_ping_interval_s)


def start_keepalive() -> None:
    try:
        _watchdog.start()
    except Exception as exc:  # pragma: no cover
        logger.warning("Keep-alive could not start: %s", exc)


def stop_keepalive() -> None:
    _watchdog.stop()


def keepalive_status() -> dict:
    return _watchdog.status()
