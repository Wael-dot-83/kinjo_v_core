"""Minimal process supervisor for uvicorn in local/dev containers."""

from __future__ import annotations

import os
import subprocess
import sys
import time


def main() -> int:
    command = [
        sys.executable,
        "-m",
        "uvicorn",
        "main:app",
        "--host",
        os.getenv("KINJO_HOST", "0.0.0.0"),
        "--port",
        os.getenv("KINJO_PORT", "8000"),
    ]
    restart_delay = float(os.getenv("KINJO_RESTART_DELAY_SECONDS", "2"))
    max_restarts = int(os.getenv("KINJO_MAX_RESTARTS", "25"))
    restart_count = 0

    while True:
        process = subprocess.Popen(command)
        exit_code = process.wait()
        if exit_code == 0:
            return 0
        restart_count += 1
        if restart_count > max_restarts:
            return exit_code
        time.sleep(restart_delay)


if __name__ == "__main__":
    raise SystemExit(main())

