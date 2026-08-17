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


def test_comma_separated_list_values_parse_from_a_dotenv_file(tmp_path, monkeypatch):
    """.env is the path almost everyone uses, and it used to reject comma lists.

    The comma-list source subclassed only EnvSettingsSource, so a real environment
    variable accepted `ar,en` while the identical line in a .env file raised
    SettingsError. `.env.example` shipped exactly that form, so copying the
    documented example produced an app that would not boot.
    """
    env_file = tmp_path / ".env"
    env_file.write_text(
        "SECRET_KEY=" + "x" * 48 + "\n"
        "SUPPORTED_LANGUAGES=ar,en\n"
        "CORS_ALLOWED_ORIGINS=https://a.example.com, https://b.example.com\n"
        "TRUSTED_HOSTS=a.example.com,b.example.com\n",
        encoding="utf-8",
    )
    # Env vars would otherwise satisfy the fields and mask a dotenv-only failure.
    for var in ("SUPPORTED_LANGUAGES", "CORS_ALLOWED_ORIGINS", "TRUSTED_HOSTS", "SECRET_KEY"):
        monkeypatch.delenv(var, raising=False)

    settings = Settings(_env_file=str(env_file))

    assert settings.SUPPORTED_LANGUAGES == ["ar", "en"]
    assert settings.CORS_ALLOWED_ORIGINS == ["https://a.example.com", "https://b.example.com"]
    assert settings.TRUSTED_HOSTS == ["a.example.com", "b.example.com"]


def test_json_list_values_still_parse_from_a_dotenv_file(tmp_path, monkeypatch):
    """The droplet env file uses JSON form; adding comma support must not break it."""
    env_file = tmp_path / ".env"
    env_file.write_text(
        "SECRET_KEY=" + "x" * 48 + "\n"
        'SUPPORTED_LANGUAGES=["ar","en"]\n'
        'TRUSTED_HOSTS=["159.223.16.33","localhost"]\n',
        encoding="utf-8",
    )
    for var in ("SUPPORTED_LANGUAGES", "TRUSTED_HOSTS", "SECRET_KEY"):
        monkeypatch.delenv(var, raising=False)

    settings = Settings(_env_file=str(env_file))

    assert settings.SUPPORTED_LANGUAGES == ["ar", "en"]
    assert settings.TRUSTED_HOSTS == ["159.223.16.33", "localhost"]


def test_shipped_env_examples_are_actually_bootable(monkeypatch):
    """Every committed .env template must parse. These files exist to be copied."""
    root = pathlib.Path(__file__).resolve().parent.parent
    for name in (".env.example", ".env.local.example", ".env.production.template"):
        candidate = root / name
        if not candidate.exists():
            continue
        for var in ("SUPPORTED_LANGUAGES", "CORS_ALLOWED_ORIGINS", "TRUSTED_HOSTS", "SECRET_KEY"):
            monkeypatch.delenv(var, raising=False)
        # Must not raise. A template that cannot be loaded is a broken template.
        Settings(_env_file=str(candidate))


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
        