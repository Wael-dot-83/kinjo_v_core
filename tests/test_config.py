import pathlib
import secrets

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


# --- SECRET_KEY: published keys must never boot production ----------------------
# .env.production.template shipped this exact key for months. It is 64 hex chars,
# so it passes both the length check and the placeholder-substring check — the two
# guards that existed before. Only an explicit by-value rejection catches it, and
# these tests are the regression fence for that.
PUBLISHED_TEMPLATE_KEY = "6a1a47bb478d99b9c9000d903abb948521944583f769da8b81e15423d8900d4e"
PUBLISHED_DEV_KEY = "06cbc1392801a25aea2fe304cde7c0402378ef556896a63087dda41c7edb1683"


@pytest.mark.security
@pytest.mark.parametrize(
    "leaked_key",
    [PUBLISHED_TEMPLATE_KEY, PUBLISHED_DEV_KEY],
    ids=["env_production_template", "deploy_sh_dev_default"],
)
def test_production_rejects_keys_published_in_this_repo(monkeypatch, leaked_key):
    """A key that is public in git history can forge any JWT or session cookie."""
    _valid_production_settings(monkeypatch)
    monkeypatch.setattr(config.settings, "SECRET_KEY", leaked_key)

    with pytest.raises(RuntimeError, match="published in this repository"):
        config.validate_production_settings()


@pytest.mark.security
def test_production_rejects_unreplaced_placeholder_key(monkeypatch):
    """A forgotten REPLACE_ME must fail the boot, not sign real sessions."""
    _valid_production_settings(monkeypatch)
    monkeypatch.setattr(config.settings, "SECRET_KEY", "REPLACE_ME_RUN_THE_COMMAND_ABOVE")

    with pytest.raises(RuntimeError, match="development default"):
        config.validate_production_settings()


@pytest.mark.security
def test_production_accepts_a_freshly_generated_key(monkeypatch):
    """The blocklist must reject only the published keys, not every 64-hex key."""
    _valid_production_settings(monkeypatch)
    monkeypatch.setattr(config.settings, "SECRET_KEY", secrets.token_hex(32))
    monkeypatch.setattr(config.settings, "SMTP_HOST", "")
    monkeypatch.setattr(config.settings, "SMTP_FROM", "")

    # Reaches the SMTP check, i.e. a fresh key cleared the SECRET_KEY guards.
    with pytest.raises(RuntimeError, match="SMTP_UNCONFIGURED"):
        config.validate_production_settings()


# --- JWT algorithm -------------------------------------------------------------
@pytest.mark.security
@pytest.mark.parametrize("algorithm", ["none", "None", "ES256", "ES512", "EdDSA", "RS256"])
def test_production_rejects_non_hmac_jwt_algorithms(monkeypatch, algorithm):
    """'none' forges tokens outright; ES*/EdDSA reach the vulnerable ecdsa backend."""
    _valid_production_settings(monkeypatch)
    monkeypatch.setattr(config.settings, "ALGORITHM", algorithm)

    with pytest.raises(RuntimeError, match="ALGORITHM must be one of"):
        config.validate_production_settings()


@pytest.mark.security
@pytest.mark.parametrize("algorithm", ["HS256", "HS384", "HS512", "hs256"])
def test_production_accepts_hmac_algorithms(monkeypatch, algorithm):
    _valid_production_settings(monkeypatch)
    monkeypatch.setattr(config.settings, "ALGORITHM", algorithm)
    monkeypatch.setattr(config.settings, "SMTP_HOST", "")
    monkeypatch.setattr(config.settings, "SMTP_FROM", "")

    # Reaches the SMTP check, i.e. the algorithm guard let HMAC through.
    with pytest.raises(RuntimeError, match="SMTP_UNCONFIGURED"):
        config.validate_production_settings()


@pytest.mark.security
def test_production_template_no_longer_ships_a_usable_key():
    """The template on disk must not contain a real key for someone to copy."""
    template = pathlib.Path(__file__).resolve().parent.parent / ".env.production.template"
    shipped = next(
        line.split("=", 1)[1].strip()
        for line in template.read_text(encoding="utf-8").splitlines()
        if line.startswith("SECRET_KEY=")
    )

    assert shipped.startswith("REPLACE_ME"), f"template ships a usable SECRET_KEY: {shipped!r}"
        