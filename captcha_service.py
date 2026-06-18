"""Pluggable CAPTCHA verification (hCaptcha or reCAPTCHA v2).

Disabled by default (``CAPTCHA_ENABLED=False``) so self-hosted/dev
deployments are completely unaffected until an operator opts in with real
provider credentials. When enabled, verification fails closed: a missing
secret key, an unsupported provider, or a failed upstream call all reject
the submission rather than silently letting it through.
"""
from __future__ import annotations

import logging
from typing import Optional

import httpx

from config import settings

logger = logging.getLogger(__name__)

_VERIFY_URLS = {
    "hcaptcha": "https://hcaptcha.com/siteverify",
    "recaptcha": "https://www.google.com/recaptcha/api/siteverify",
}


def captcha_required() -> bool:
    """Whether CAPTCHA verification should be enforced for this request.

    Always False under the test suite (TESTING=true), mirroring the existing
    TESTING-bypass pattern used elsewhere (database.py, main.py guards).
    """
    return bool(settings.CAPTCHA_ENABLED) and not settings.TESTING


def verify_captcha(token: Optional[str]) -> bool:
    """Verify a CAPTCHA response token with the configured provider.

    Returns True immediately when CAPTCHA is disabled or under TESTING.
    Fails closed (returns False) on any misconfiguration or upstream error —
    never silently treats an unverifiable submission as valid.
    """
    if not captcha_required():
        return True

    provider = (settings.CAPTCHA_PROVIDER or "hcaptcha").lower()
    verify_url = _VERIFY_URLS.get(provider)
    if not verify_url:
        logger.error("CAPTCHA_ENABLED but CAPTCHA_PROVIDER=%r is not supported", provider)
        return False

    if not settings.CAPTCHA_SECRET_KEY:
        logger.error("CAPTCHA_ENABLED but CAPTCHA_SECRET_KEY is not configured; rejecting submission")
        return False

    if not token:
        return False

    try:
        response = httpx.post(
            verify_url,
            data={"secret": settings.CAPTCHA_SECRET_KEY, "response": token},
            timeout=10.0,
        )
        response.raise_for_status()
        result = response.json()
        return bool(result.get("success"))
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("CAPTCHA verification request failed: %s", exc)
        return False


def captcha_error_message(lang: str = "ar") -> str:
    if lang == "en":
        return "CAPTCHA verification failed. Please try again."
    return "فشل التحقق من رمز الحماية (CAPTCHA). يرجى المحاولة مرة أخرى."


__all__ = ["captcha_required", "verify_captcha", "captcha_error_message"]
