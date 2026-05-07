import pytest

import config
from config import Settings


def test_comma_separated_origin_and_host_env_values_parse(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "x" * 48)
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "https://app.example.com, https://admin.example.com")
    monkeypatch.setenv("TRUSTED_HOSTS", "app.example.com,admin.example.com")

    settings = Settings(_env_file=None)

    assert settings.CORS_ALLOWED_ORIGINS == ["https://app.example.com", "https://admin.example.com"]
    assert settings.TRUSTED_HOSTS == ["app.example.com", "admin.example.com"]


def test_production_validation_requires_smtp(monkeypatch):
    monkeypatch.setattr(config.settings, "ENVIRONMENT", "production")
    monkeypatch.setattr(config.settings, "DEBUG", False)
    monkeypatch.setattr(config.settings, "API_DOCS_ENABLED", False)
    monkeypatch.setattr(config.settings, "SECRET_KEY", "x" * 48)
    monkeypatch.setattr(config.settings, "CORS_ALLOWED_ORIGINS", ["https://app.example.com"])
    monkeypatch.setattr(config.settings, "SESSION_COOKIE_SAMESITE", "strict")
    monkeypatch.setattr(config.settings, "SMTP_HOST", "")
    monkeypatch.setattr(config.settings, "SMTP_FROM", "")

    with pytest.raises(RuntimeError, match="SMTP_UNCONFIGURED"):
        config.validate_production_settings()
