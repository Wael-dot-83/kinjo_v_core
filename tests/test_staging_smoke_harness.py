import importlib.util
import sys
from pathlib import Path

import requests


def _load_harness():
    path = Path(__file__).parents[1] / "scripts" / "manual-diagnostics" / "staging_smoke_test.py"
    spec = importlib.util.spec_from_file_location("staging_smoke_test", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_smoke_session_never_follows_redirects(monkeypatch):
    harness = _load_harness()
    captured = {}

    def fake_request(self, method, url, **kwargs):
        captured.update(kwargs)
        return object()

    monkeypatch.setattr(requests.Session, "request", fake_request)
    harness.NoRedirectSession().get("https://staging.example/redirect")

    assert captured["allow_redirects"] is False


def test_smoke_harness_requires_mutation_acknowledgement(monkeypatch):
    harness = _load_harness()
    monkeypatch.setattr(sys, "argv", ["staging_smoke_test.py"])
    monkeypatch.setattr(harness, "ADMIN_PASSWORD", "not-used")
    monkeypatch.setattr(harness, "ALLOW_MUTATIONS", False)

    assert harness.main() == 2


def test_smoke_harness_rejects_nonlocal_http(monkeypatch):
    harness = _load_harness()
    monkeypatch.setattr(sys, "argv", ["staging_smoke_test.py"])
    monkeypatch.setattr(harness, "ADMIN_PASSWORD", "not-used")
    monkeypatch.setattr(harness, "ALLOW_MUTATIONS", True)
    monkeypatch.setattr(harness, "BASE_URL", "http://staging.example")
    monkeypatch.setattr(harness, "EXPECTED_HOST", "staging.example")

    assert harness.main() == 2


def test_smoke_harness_requires_exact_nonlocal_host(monkeypatch):
    harness = _load_harness()
    monkeypatch.setattr(sys, "argv", ["staging_smoke_test.py"])
    monkeypatch.setattr(harness, "ADMIN_PASSWORD", "not-used")
    monkeypatch.setattr(harness, "ALLOW_MUTATIONS", True)
    monkeypatch.setattr(harness, "BASE_URL", "https://staging.example")
    monkeypatch.setattr(harness, "EXPECTED_HOST", "other.example")

    assert harness.main() == 2


def test_cleanup_fails_when_artifact_lookup_is_unresolved():
    harness = _load_harness()

    class Response:
        status_code = 503

    class Session:
        def get(self, *args, **kwargs):
            return Response()

    report = harness.Report()
    harness.cleanup(
        report,
        Session(),
        [{"username": "csrf_probe_unknown", "id": None}],
    )

    assert report.checks[-1]["status"] == "fail"
    assert "lookup-503" in report.checks[-1]["detail"]
