"""Rate-limit decorators must wrap handlers before FastAPI registers them."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_impersonation_routes_register_the_rate_limited_wrapper():
    source = (ROOT / "routers" / "admin_impersonation.py").read_text(encoding="utf-8")
    assert '@router.post("/impersonate"' in source
    assert '@router.post("/impersonate", status_code=status.HTTP_200_OK)\n@limiter.limit(' in source
    assert '@router.post("/exit-impersonation", status_code=status.HTTP_200_OK)\n@limiter.limit(' in source
    assert '@router.get("/impersonate/audit")\n@limiter.limit(' in source
