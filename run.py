#!/usr/bin/env python3
"""One-command launcher for Meridian.

    python run.py                 # http://localhost:8000
    python run.py --port 9000
    python run.py --streamlit     # launch the Streamlit frontend instead
"""
from __future__ import annotations

import argparse
import subprocess
import sys


def main() -> None:
    p = argparse.ArgumentParser(description="Launch Meridian")
    p.add_argument("--host", default="0.0.0.0")
    p.add_argument("--port", type=int, default=8000)
    p.add_argument("--reload", action="store_true")
    p.add_argument("--streamlit", action="store_true",
                   help="Run the Streamlit frontend instead of the premium web app")
    args = p.parse_args()
    if args.streamlit:
        cmd = [sys.executable, "-m", "streamlit", "run", "app/main.py",
               "--server.address", args.host, "--server.port", "8501",
               "--server.headless", "true", "--browser.gatherUsageStats", "false"]
    else:
        cmd = [sys.executable, "-m", "uvicorn", "app.api.server:app",
               "--host", args.host, "--port", str(args.port),
               "--workers", "1"] + (["--reload"] if args.reload else [])
    print("◆  MERIDIAN — Market Intelligence, Redefined.")
    print(f"   Starting: {' '.join(cmd)}")
    print(f"   Developed by Mridul Sharma\n")
    raise SystemExit(subprocess.call(cmd))


if __name__ == "__main__":
    main()
