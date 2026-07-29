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


def _valid_production_settings(monkeypatch):
    """Everything validate_production_settings() requires, so a test can fail one thing."""
    monkeypatch.setattr(config.settings, "ENVIRONMENT", "production")
    monkeypatch.setattr(config.settings, "DEBUG", False)
    monkeypatch.setattr(config.settings, "API_DOCS_ENABLED", False)
    monkeypatch.setattr(config.settings, "SECRET_KEY", "x" * 48)
    monkeypatch.setattr(config.settings, "DATABASE_URL", "postgresql://u:p@db:5432/kinjo")
    monkeypatch.setattr(config.settings, "CORS_ALLOWED_ORIGINS", ["https://app.example.com"])
    monkeypatch.setattr(config.settings, "SESSION_COOKIE_SAMESITE", "strict")


def test_production_validation_requires_smtp(monkeypatch):
    _valid_production_settings(monkeypatch)
    monkeypatch.setattr(config.settings, "SMTP_HOST", "")
    monkeypatch.setattr(config.settings, "SMTP_FROM", "")

    with pytest.raises(RuntimeError, match="SMTP_UNCONFIGURED"):
        config.validate_production_settings()


def test_production_rejects_sqlite(monkeypatch):
    """SQLite drops tzinfo, so Jordan/UTC timestamps skew 3h — never allow it in prod."""
    _valid_production_settings(monkeypatch)
    monkeypatch.setattr(config.settings, "DATABASE_URL", "sqlite:///./data/kinjo.db")

    with pytest.raises(RuntimeError, match="SQLite is not supported in production"):
        config.validate_production_settings()


def test_production_accepts_postgres(monkeypatch):
    """The Postgres URL must clear the database guard (it may still fail on later checks)."""
    _valid_production_settings(monkeypatch)
    monkeypatch.setattr(config.settings, "SMTP_HOST", "")
    monkeypatch.setattr(config.settings, "SMTP_FROM", "")

    # Reaches the SMTP check, i.e. the database guard let PostgreSQL through.
    with pytest.raises(RuntimeError, match="SMTP_UNCONFIGURED"):
        config.validate_production_settings()


# --------------------------------------------------------------------------
# Non-canonical child-age policy must be visible at startup.
#
# The setting is deliberately overridable (it is policy, not a constant), so
# this warns rather than refusing to start. Without it, a .env carrying the
# superseded MIN_CHILD_AGE_DAYS=70 refused children aged 1-69 days with no
# signal in any log.
# --------------------------------------------------------------------------


def _reaches_child_age_check(monkeypatch):
    """Valid production settings that get past every hard guard before the warning."""
    _valid_production_settings(monkeypatch)
    monkeypatch.setattr(config.settings, "SMTP_HOST", "smtp.example.com")
    monkeypatch.setattr(config.settings, "SMTP_FROM", "noreply@example.com")
    monkeypatch.setattr(config.settings, "CAPTCHA_ENABLED", False)
    monkeypatch.setattr(config.settings, "REDIS_URL", "redis://cache:6379/0")


def test_noncanonical_minimum_child_age_warns_at_startup(monkeypatch, caplog):
    _reaches_child_age_check(monkeypatch)
    monkeypatch.setattr(config.settings, "MIN_CHILD_AGE_DAYS", 70)

    with caplog.at_level("WARNING", logger=config.logger.name):
        config.validate_production_settings()

    warnings = [r for r in caplog.records if "NONCANONICAL_CHILD_AGE_POLICY" in r.getMessage()]
    assert len(warnings) == 1, [r.getMessage() for r in caplog.records]

    message = warnings[0].getMessage()
    assert "MIN_CHILD_AGE_DAYS=70" in message
    assert f"canonical={config.CANONICAL_MIN_CHILD_AGE_DAYS}" in message
    # The operator needs the impact and the exact remedy, not just a flag.
    assert "1-69 days will be refused" in message
    assert "remove the override" in message
    assert warnings[0].levelname == "WARNING"


def test_noncanonical_maximum_child_age_warns_at_startup(monkeypatch, caplog):
    _reaches_child_age_check(monkeypatch)
    monkeypatch.setattr(config.settings, "MAX_CHILD_AGE_MONTHS", 48)

    with caplog.at_level("WARNING", logger=config.logger.name):
        config.validate_production_settings()

    warnings = [r for r in caplog.records if "MAX_CHILD_AGE_MONTHS" in r.getMessage()]
    assert len(warnings) == 1
    assert f"canonical={config.CANONICAL_MAX_CHILD_AGE_MONTHS}" in warnings[0].getMessage()


def test_canonical_child_age_policy_is_silent(monkeypatch, caplog):
    """The happy path must not warn, or the signal is worthless."""
    _reaches_child_age_check(monkeypatch)
    monkeypatch.setattr(config.settings, "MIN_CHILD_AGE_DAYS", config.CANONICAL_MIN_CHILD_AGE_DAYS)
    monkeypatch.setattr(config.settings, "MAX_CHILD_AGE_MONTHS", config.CANONICAL_MAX_CHILD_AGE_MONTHS)

    with caplog.at_level("WARNING", logger=config.logger.name):
        config.validate_production_settings()

    assert not [r for r in caplog.records if "CHILD_AGE_POLICY" in r.getMessage()]


def test_child_age_defaults_are_the_canonical_constants():
    """The default and the policy of record cannot drift apart."""
    fields = Settings.model_fields
    assert fields["MIN_CHILD_AGE_DAYS"].default == config.CANONICAL_MIN_CHILD_AGE_DAYS
    assert fields["MAX_CHILD_AGE_MONTHS"].default == config.CANONICAL_MAX_CHILD_AGE_MONTHS
