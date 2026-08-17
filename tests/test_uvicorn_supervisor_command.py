"""The uvicorn launch command is a production correctness surface, not glue.

Two things here are load-bearing behind the nginx reverse proxy:

* ``--proxy-headers`` + ``--forwarded-allow-ips`` decide whether the app sees the
  real client IP or the proxy's. Without them every request shares one per-IP
  rate-limit bucket and every audit row records the proxy address.
* ``--workers`` decides whether requests can be served concurrently at all.

Both were absent, and neither fails loudly — the app boots and serves traffic
either way. These tests are the only thing that makes a regression visible.
"""

import importlib.util
import pathlib

import pytest

_LAUNCHER = pathlib.Path(__file__).resolve().parent.parent / "scripts" / "run_uvicorn_supervised.py"
_spec = importlib.util.spec_from_file_location("run_uvicorn_supervised", _LAUNCHER)
run_uvicorn_supervised = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(run_uvicorn_supervised)


@pytest.fixture
def clean_env(monkeypatch):
    for var in (
        "KINJO_HOST",
        "KINJO_PORT",
        "KINJO_WORKERS",
        "KINJO_FORWARDED_ALLOW_IPS",
    ):
        monkeypatch.delenv(var, raising=False)
    return monkeypatch


def test_defaults_stay_single_worker_and_direct(clean_env):
    """Local runs and the test harness must be unaffected by the proxy support."""
    command = run_uvicorn_supervised._build_command()

    assert "--workers" not in command
    assert "--proxy-headers" not in command
    assert command[-4:] == ["--host", "0.0.0.0", "--port", "8000"]


def test_proxy_headers_enabled_only_with_an_explicit_trusted_source(clean_env):
    clean_env.setenv("KINJO_FORWARDED_ALLOW_IPS", "172.18.0.5")
    command = run_uvicorn_supervised._build_command()

    assert "--proxy-headers" in command
    assert command[command.index("--forwarded-allow-ips") + 1] == "172.18.0.5"


def test_trusted_source_is_never_implicitly_wildcarded(clean_env):
    """A wildcard lets any client spoof X-Forwarded-For; it must be opt-in only."""
    command = run_uvicorn_supervised._build_command()

    assert "*" not in command


def test_worker_count_is_applied_when_scaled_up(clean_env):
    clean_env.setenv("KINJO_WORKERS", "5")
    command = run_uvicorn_supervised._build_command()

    assert command[command.index("--workers") + 1] == "5"


@pytest.mark.parametrize("bad", ["0", "1", "", "two", "-4"])
def test_invalid_or_pointless_worker_counts_do_not_reach_uvicorn(clean_env, bad):
    """A malformed value must fall back to the default, not crash the container."""
    clean_env.setenv("KINJO_WORKERS", bad)
    command = run_uvicorn_supervised._build_command()

    assert "--workers" not in command
