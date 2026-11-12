#!/usr/bin/env python3
"""MERIDIAN — direct, Render-compatible Uvicorn launcher.

    python run.py                                   # local, port 8000
    PORT=10000 python run.py                        # Render / Railway / Fly
    python run.py --port 9000 --workers 1
    python run.py --reload                          # development

The public port is resolved from, in order: --port, PORT (host-injected),
MERIDIAN_PORT, then 8000. Render REQUIRES 0.0.0.0:$PORT; binding 127.0.0.1 or
hardcoding 8000 causes port-scan timeouts and 502s.

Developed by Mridul Sharma
"""
from __future__ import annotations

import argparse
import logging
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import uvicorn

from app.config import server_port, web_concurrency

logger = logging.getLogger("meridian.run")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Run the Meridian API and web app")
    p.add_argument("--host", default=os.getenv("MERIDIAN_HOST", "0.0.0.0"),
                   help="Bind address. NEVER use 127.0.0.1 on a PaaS host.")
    p.add_argument("--port", type=int, default=None,
                   help="Override port (default: $PORT, $MERIDIAN_PORT, or 8000)")
    p.add_argument("--workers", type=int, default=None,
                   help="Worker count. MUST be 1 — jobs/SSE are in-process (default: $WEB_CONCURRENCY or 1)")
    p.add_argument("--reload", action="store_true", help="Auto-reload for development")
    p.add_argument("--streamlit", action="store_true",
                   help="Run the secondary Streamlit frontend on :8501 instead")
    p.add_argument("--log-level", default=os.getenv("MERIDIAN_LOG_LEVEL", "info"),
                   choices=["critical", "error", "warning", "info", "debug", "trace"])
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.streamlit:
        cmd = [sys.executable, "-m", "streamlit", "run", "app/main.py",
               "--server.address", args.host, "--server.port", "8501",
               "--server.headless", "true", "--browser.gatherUsageStats", "false"]
        print("◆  MERIDIAN — Market Intelligence, Redefined.")
        print(f"   Streamlit frontend → http://{args.host}:8501")
        print("   Developed by Mridul Sharma\n")
        return subprocess.call(cmd)

    port = args.port if args.port is not None else server_port()
    workers = args.workers if args.workers is not None else web_concurrency()

    # Export so app.config.Settings, /api/health and the healthcheck all agree.
    os.environ["PORT"] = str(port)
    os.environ["WEB_CONCURRENCY"] = str(workers)

    if args.reload and workers != 1:
        logger.warning("--reload implies a single worker; overriding --workers")
        workers = 1
    if workers != 1:
        logger.warning("Meridian uses in-process jobs and SSE streams; "
                       "multiple workers will produce inconsistent state")

    print("◆  MERIDIAN — Market Intelligence, Redefined.")
    print(f"   Serving http://{args.host}:{port}  ·  workers={workers}")
    if os.getenv("RENDER_SERVICE_NAME"):
        print("   Platform: Render (PORT injected, health check /api/health)")

    uvicorn.run(
        "app.api.server:app",
        host=args.host,
        port=port,
        workers=workers if not args.reload else 1,
        reload=args.reload,
        proxy_headers=True,
        forwarded_allow_ips="*",
        timeout_keep_alive=75,
        access_log=args.log_level == "debug",
        log_level=args.log_level,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
