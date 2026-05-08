"""
Configuration management for KinJo platform
"""
from typing import Any, List, Tuple, Type

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic_settings import EnvSettingsSource


# ---------------------------------------------------------------------------
# Custom env source: falls back to comma-split when JSON-decode fails
# This lets us write  CORS_ALLOWED_ORIGINS=url1,url2  in .env without JSON
# ---------------------------------------------------------------------------

class _CommaSplitEnvSource(EnvSettingsSource):
    """EnvSettingsSource that accepts comma-separated strings for List fields."""

    def decode_complex_value(self, field_name: str, field: Any, value: Any) -> Any:
        try:
            return super().decode_complex_value(field_name, field, value)
        except Exception:
            if isinstance(value, str):
                return [s.strip() for s in value.split(",") if s.strip()]
            raise


class Settings(BaseSettings):
    """Application settings"""

    # Database
    DATABASE_URL: str = "postgresql://user:password@localhost:5432/kinjo_db"
    TESTING: bool = False

    # Security
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    ACCESS_TOKEN_EXPIRE_MINUTES_REMEMBER: int = 60 * 24 * 7

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # Application
    APP_NAME: str = "KinJo"
    ENVIRONMENT: str = "development"
    DEBUG: bool = True

    # CORS / trusted hosts — accept comma-separated strings from .env
    CORS_ALLOWED_ORIGINS: List[str] = ["http://localhost:8000", "http://127.0.0.1:8000"]
    TRUSTED_HOSTS: List[str] = ["localhost", "127.0.0.1"]

    # API / docs flags
    API_DOCS_ENABLED: bool = True

    # Cookie security
    SESSION_COOKIE_SAMESITE: str = "lax"

    # SMTP (required in production)
    SMTP_HOST: str = ""
    SMTP_FROM: str = ""

    @field_validator("DEBUG", mode="before")
    @classmethod
    def parse_debug(cls, value: Any) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, int):
            return bool(value)
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"true", "1", "t", "yes", "y", "on", "debug", "dev", "development"}:
                return True
            if normalized in {"false", "0", "f", "no", "n", "off", "release", "prod", "production"}:
                return False
        raise ValueError("DEBUG must be a boolean-like value")

    # Localization
    DEFAULT_LANGUAGE: str = "ar"
    SUPPORTED_LANGUAGES: List[str] = ["ar", "en"]

    # Business Rules
    MIN_CHILD_AGE_DAYS: int = 70
    MAX_CHILD_AGE_MONTHS: int = 56  # 4 years 8 months
    WAITLIST_OFFER_EXPIRY_HOURS: int = 48

    # Ollama (local LLM / embedding inference — Phase 3 & 5)
    OLLAMA_URL: str = "http://localhost:11434"
    OLLAMA_LLM_MODEL: str = "llama3.2"
    OLLAMA_EMBED_MODEL: str = "nomic-embed-text"
    OLLAMA_TIMEOUT_SECONDS: int = 120
    OLLAMA_EMBED_DIM: int = 768

    # Jordan-specific
    JORDAN_PHONE_PATTERN: str = r"^(\+962|00962|0)[0-9]{9}$"
    JORDAN_GOVERNORATES: List[str] = [
        "عمان", "إربد", "الزرقاء", "العقبة", "المفرق",
        "جرش", "عجلون", "الطفيلة", "الكرك", "معان", "السلط", "مادبا"
    ]

    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=True,
        extra="ignore",
    )

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: Type[BaseSettings],
        init_settings: Any,
        env_settings: Any,
        dotenv_settings: Any,
        file_secret_settings: Any,
    ) -> Tuple[Any, ...]:
        return (
            init_settings,
            _CommaSplitEnvSource(settings_cls),
            dotenv_settings,
            file_secret_settings,
        )


settings = Settings()


def validate_production_settings() -> None:
    """Raise RuntimeError for any production mis-configuration.

    Call on startup when ENVIRONMENT='production'.
    """
    if settings.ENVIRONMENT.lower() != "production":
        return
    if settings.DEBUG:
        raise RuntimeError(
            "DEBUG_ENABLED: DEBUG must be False in production."
        )
    if settings.API_DOCS_ENABLED:
        raise RuntimeError(
            "API_DOCS_EXPOSED: API_DOCS_ENABLED must be False in production."
        )
    if not settings.SMTP_HOST or not settings.SMTP_FROM:
        raise RuntimeError(
            "SMTP_UNCONFIGURED: SMTP_HOST and SMTP_FROM must be set in production."
        )


# Standalone DEBUG flag for contexts that import config without pydantic-settings
# (e.g. Alembic env.py, shell scripts). Matches the validator logic above.
import os as _os
DEBUG: bool = _os.getenv("DEBUG", "True").strip().lower() in ("true", "1", "t", "yes", "on")
