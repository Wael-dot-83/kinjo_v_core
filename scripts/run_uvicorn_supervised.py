"""Minimal process supervisor for uvicorn in local/dev and container runs."""

from __future__ import annotations

import os
import subprocess
import sys
import time


def _build_command() -> list[str]:
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

    # Worker count. One process serves one request at a time for any CPU-bound
    # section, so a single worker made the whole app serialise behind the slowest
    # dashboard aggregation. Default stays 1 so local runs and the test harness
    # are unchanged; production sets KINJO_WORKERS (2*vCPU+1 is the usual start).
    workers = os.getenv("KINJO_WORKERS")
    if workers and workers.isdigit() and int(workers) > 1:
        command += ["--workers", workers]

    # Behind the nginx reverse proxy the peer address is the proxy, not the user.
    # Without --proxy-headers uvicorn reports that proxy address as the client, so
    # every request shares one per-IP rate-limit bucket and every audit row records
    # the same address. --forwarded-allow-ips names who is trusted to set the
    # X-Forwarded-* headers; it must NOT be "*" on a host whose app port is
    # reachable directly, or a client can spoof its own source IP. The compose
    # network keeps `web` unpublished, and KINJO_FORWARDED_ALLOW_IPS pins the
    # proxy's address on that network.
    forwarded_allow = os.getenv("KINJO_FORWARDED_ALLOW_IPS")
    if forwarded_allow:
        command += ["--proxy-headers", "--forwarded-allow-ips", forwarded_allow]

    return command


def main() -> int:
    command = _build_command()
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
