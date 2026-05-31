"""
Configuration management for KinJo platform
"""
import logging
import os
from typing import Any, Dict, List, Tuple, Type

# Absolute path to the project root (directory containing this file)
_PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))

from pydantic import ConfigDict, field_validator
from pydantic.fields import FieldInfo
from pydantic_settings import BaseSettings, EnvSettingsSource, PydanticBaseSettingsSource


class _CommaListEnvSource(EnvSettingsSource):
    """Env source that accepts comma-separated strings for List[str] fields."""

    def prepare_field_value(
        self, field_name: str, field: FieldInfo, value: Any, value_is_complex: bool
    ) -> Any:
        if isinstance(value, str):
            is_complex, _ = self._field_is_complex(field)
            if is_complex or value_is_complex:
                stripped = value.strip()
                if not stripped:
                    return None
                if not stripped.startswith(("[", "{")):
                    return [item.strip().strip("\"'") for item in stripped.split(",") if item.strip()]
        return super().prepare_field_value(field_name, field, value, value_is_complex)

logger = logging.getLogger(__name__)


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

    # IAM Hardening
    ACCOUNT_LOCKOUT_THRESHOLD: int = 5          # Lock after N consecutive failures
    ACCOUNT_LOCKOUT_DURATION_MINUTES: int = 30  # Lock duration in minutes
    PASSWORD_MIN_LENGTH: int = 8
    PASSWORD_REQUIRE_UPPERCASE: bool = True
    PASSWORD_REQUIRE_LOWERCASE: bool = True
    PASSWORD_REQUIRE_DIGIT: bool = True
    PASSWORD_REQUIRE_SPECIAL: bool = True
    PASSWORD_MAX_AGE_DAYS: int = 90             # Force change after 90 days (0 = disabled)

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # Application
    APP_NAME: str = "KinJo"
    ENVIRONMENT: str = "development"
    DEBUG: bool = True
    API_DOCS_ENABLED: bool = True
    CORS_ALLOWED_ORIGINS: List[str] = ["http://127.0.0.1:8000", "http://localhost:8000"]
    TRUSTED_HOSTS: List[str] = ["127.0.0.1", "localhost", "testserver"]
    COOKIE_DOMAIN: str = ""
    SESSION_COOKIE_NAME: str = "kinjo_session"
    SESSION_COOKIE_SAMESITE: str = "strict"
    CSRF_COOKIE_NAME: str = "kinjo_csrf_token"
    REQUEST_TIMEOUT_SECONDS: int = 30
    PUBLIC_REGISTRATION_ENABLED: bool = False
    MFA_TOTP_ISSUER: str = "KinJo"
    MFA_TICKET_EXPIRE_MINUTES: int = 10

    # AI Integration
    GOOGLE_API_KEY: str = ""

    # Rate Limiting Configuration
    RATE_LIMIT_STORAGE_URI: str = "memory://"
    RATE_LIMIT_PASSWORD_RESET: str = "3/minute"
    RATE_LIMIT_PASSWORD_RESET_REQUEST: str = "5/minute"
    RATE_LIMIT_BULK_CREATE: str = "10/minute"
    RATE_LIMIT_BULK_UPDATE: str = "10/minute"
    RATE_LIMIT_BULK_DELETE: str = "5/minute"
    RATE_LIMIT_CSV_IMPORT: str = "5/minute"
    RATE_LIMIT_ADMIN_READ: str = "60/minute"
    RATE_LIMIT_ADMIN_WRITE: str = "30/minute"
    RATE_LIMIT_MESSAGES_SEND: str = "30/minute"
    RATE_LIMIT_MESSAGES_SEND_ADMIN: str = "120/minute"
    RATE_LIMIT_MESSAGES_SEND_MANAGER: str = "60/minute"
    RATE_LIMIT_MESSAGES_SEND_SUPERVISOR: str = "20/minute"
    RATE_LIMIT_MESSAGES_SEND_PARENT: str = "15/minute"
    RATE_LIMIT_MESSAGES_LIST: str = "60/minute"
    RATE_LIMIT_MESSAGES_GET: str = "120/minute"
    RATE_LIMIT_MESSAGES_READ: str = "120/minute"
    RATE_LIMIT_MESSAGES_REPLY: str = "30/minute"
    RATE_LIMIT_MESSAGES_REPLY_ADMIN: str = "120/minute"
    RATE_LIMIT_MESSAGES_REPLY_MANAGER: str = "60/minute"
    RATE_LIMIT_MESSAGES_REPLY_SUPERVISOR: str = "20/minute"
    RATE_LIMIT_MESSAGES_REPLY_PARENT: str = "15/minute"
    RATE_LIMIT_MESSAGES_BULK: str = "10/minute"
    RATE_LIMIT_MESSAGES_DELETE: str = "30/minute"
    RATE_LIMIT_MESSAGES_ARCHIVE: str = "30/minute"
    RATE_LIMIT_MESSAGES_UPLOAD: str = "10/minute"

    # Pagination Configuration
    DEFAULT_PAGE_SIZE: int = 25
    MAX_PAGE_SIZE: int = 100

    # Logging
    LOG_LEVEL: str = "INFO"  # Set to DEBUG, INFO, WARNING, ERROR, CRITICAL
    LOG_FILE: str = "kinjo.log"  # Log file path for production

    # Bulk Operation Limits
    MAX_BULK_CREATE: int = 100
    MAX_BULK_UPDATE: int = 500
    MAX_BULK_DELETE: int = 100
    BULK_CONFIRMATION_THRESHOLD: int = 10
    MAX_BULK_MESSAGES: int = 200

    # Audit Configuration
    AUDIT_LOG_MAX_DETAILS_SIZE: int = 10000  # 10KB

    # Storage (attachments)
    BASE_DIR: str = _PROJECT_ROOT  # absolute project root; all relative paths resolve from here
    STORAGE_PROVIDER: str = "local"  # local or s3
    ATTACHMENTS_DIR: str = "data/attachments"
    MAX_ATTACHMENT_SIZE_MB: int = 10
    UPLOADS_DIR: str = "data/uploads"  # child photos & documents
    STATIC_DIR: str = "static"  # static files directory
    ALLOWED_IMAGE_TYPES: list = ["image/jpeg", "image/png", "image/webp"]
    ALLOWED_DOCUMENT_TYPES: list = ["application/pdf", "image/jpeg", "image/png", "image/webp",
                                    "application/msword",
                                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document"]
    MAX_UPLOAD_SIZE_MB: int = 10
    VALID_DOCUMENT_TYPES: list = ["birth_certificate", "health_certificate", "permission_form",
                                  "id_copy", "photo", "vaccination_record", "other"]
    REQUIRED_ENROLLMENT_DOCUMENTS: list = ["birth_certificate", "health_certificate"]
    S3_BUCKET: str = ""
    S3_REGION: str = "us-east-1"
    S3_ACCESS_KEY: str = ""
    S3_SECRET_KEY: str = ""
    S3_ENDPOINT_URL: str = ""

    # Notifications
    NOTIFICATIONS_EMAIL_ENABLED: bool = False
    NOTIFICATIONS_PUSH_ENABLED: bool = False
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USERNAME: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM: str = ""
    FCM_SERVER_KEY: str = ""
    CELERY_BROKER_URL: str = "redis://localhost:6379/0"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/0"

    # Localization
    DEFAULT_LANGUAGE: str = "ar"
    SUPPORTED_LANGUAGES: List[str] = ["ar", "en"]

    # Business Rules
    MIN_CHILD_AGE_DAYS: int = 70
    MAX_CHILD_AGE_MONTHS: int = 56  # 4 years 8 months
    WAITLIST_OFFER_EXPIRY_HOURS: int = 48
    MANAGER_TO_MANAGER_ENABLED: bool = False
    MANAGER_TO_MANAGER_SCOPE: str = "same_kg"

    # Jordan-specific
    JORDAN_PHONE_PATTERN: str = r"^(\+962|00962|0)[0-9]{9}$"
    JORDAN_GOVERNORATES: List[str] = [
        "عمان", "إربد", "الزرقاء", "العقبة", "المفرق",
        "جرش", "عجلون", "الطفيلة", "الكرك", "معان", "البلقاء", "مادبا"
    ]
    JORDAN_GOVERNORATES_ENGLISH: List[str] = [
        "Amman", "Irbid", "Zarqa", "Aqaba", "Mafraq",
        "Jerash", "Ajloun", "Tafilah", "Karak", "Ma'an", "Balqa", "Madaba"
    ]
    JORDAN_GOVERNORATE_ALIASES: Dict[str, str] = {
        "amman": "عمان",
        "عمان": "عمان",
        "irbid": "إربد",
        "إربد": "إربد",
        "zarqa": "الزرقاء",
        "zarqaa": "الزرقاء",
        "الزرقاء": "الزرقاء",
        "aqaba": "العقبة",
        "al aqaba": "العقبة",
        "العقبة": "العقبة",
        "mafraq": "المفرق",
        "المفرق": "المفرق",
        "jerash": "جرش",
        "جرش": "جرش",
        "ajloun": "عجلون",
        "عجلون": "عجلون",
        "tafilah": "الطفيلة",
        "al tafilah": "الطفيلة",
        "الطفيلة": "الطفيلة",
        "karak": "الكرك",
        "الكرك": "الكرك",
        "maan": "معان",
        "ma'an": "معان",
        "معان": "معان",
        "salt": "البلقاء",
        "السلط": "البلقاء",
        "balqa": "البلقاء",
        "البلقاء": "البلقاء",
        "madaba": "مادبا",
        "مادبا": "مادبا"
    }
    JORDAN_CITIES: Dict[str, List[str]] = {
        "عمان": ["عمان", "الجبيهة", "القويسمة", "وادي السير", "صويلح", "ماركا", "أبو نصير", "طبربور"],
        "إربد": ["إربد", "الحصن", "الرمثا", "الكورة", "بني كنانة", "الأغوار الشمالية"],
        "الزرقاء": ["الزرقاء", "الرصيفة", "الهاشمية", "الأزرق"],
        "العقبة": ["العقبة", "وادي رم", "القويرة"],
        "المفرق": ["المفرق", "البادية الشمالية", "الروحاء"],
        "جرش": ["جرش", "سوف", "الكفارات", "المصطبة"],
        "عجلون": ["عجلون", "صخرة", "عنجرة", "كفرنجة"],
        "الطفيلة": ["الطفيلة", "بصيرا", "الحسا"],
        "الكرك": ["الكرك", "المزار الجنوبي", "عي", "القصر", "الأغوار الجنوبية"],
        "معان": ["معان", "الشوبك", "الطيبة", "وادي موسى"],
        "البلقاء": ["السلط", "عين الباشا", "دير علا", "الشونة الجنوبية"],
        "مادبا": ["مادبا", "ذيبان"],
    }
    ACTIVE_LIKE_ENROLLMENT_STATUSES: List[str] = [
        "SUBMITTED",
        "PENDING_REVIEW",
        "ACCEPTED",
        "ACTIVE",
    ]

    # Message limits
    MAX_MESSAGE_RECIPIENTS: int = 10000
    DUPLICATE_MESSAGE_CHECK_MINUTES: int = 5

    # Backup Configuration
    BACKUP_DIR: str = "backups"
    BACKUP_RETENTION_DAYS: int = 30
    BACKUP_SCHEDULE_HOUR: int = 2  # 2 AM
    BACKUP_CLEANUP_HOUR: int = 3   # 3 AM

    # Governance / Daily Report KPIs
    GOVERNANCE_MIN_REPORTS_FOR_RANKING: int = 5
    GOVERNANCE_SMOOTHING_K: int = 10
    GOVERNANCE_LOW_PERF_THRESHOLD: float = 0.5
    GOVERNANCE_REMINDER_COOLDOWN_HOURS: int = 48
    GOVERNANCE_REPORT_DEADLINE_HOUR: int = 16  # 4 PM Amman time
    AMMAN_TIMEZONE: str = "Asia/Amman"

    @field_validator("DEBUG", mode="before")
    @classmethod
    def normalize_debug_flag(cls, value):
        """Accept deployment-style env values such as `release`."""
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"release", "prod", "production"}:
                return False
            if normalized in {"debug", "dev", "development"}:
                return True
        return value

    @field_validator("CORS_ALLOWED_ORIGINS", "TRUSTED_HOSTS", mode="before")
    @classmethod
    def parse_string_list(cls, value: Any):
        """Allow comma-separated env values for list settings."""
        if isinstance(value, str):
            stripped = value.strip()
            if not stripped:
                return []
            if stripped.startswith("[") and stripped.endswith("]"):
                stripped = stripped[1:-1]
            return [item.strip().strip("\"'") for item in stripped.split(",") if item.strip()]
        return value

    @field_validator("SESSION_COOKIE_SAMESITE", mode="before")
    @classmethod
    def normalize_cookie_samesite(cls, value: Any) -> str:
        normalized = str(value or "strict").strip().lower()
        if normalized not in {"lax", "strict", "none"}:
            return "strict"
        return normalized

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT.lower() == "production"

    @property
    def secure_cookies(self) -> bool:
        """True in production (HTTPS); False in dev so HTTP cookies work."""
        return self.is_production

    model_config = ConfigDict(
        env_file=".env",
        case_sensitive=True,
        extra="ignore"
    )

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: Type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> Tuple[PydanticBaseSettingsSource, ...]:
        return (
            init_settings,
            _CommaListEnvSource(settings_cls),
            dotenv_settings,
            file_secret_settings,
        )


def validate_production_settings():
    """Validate critical settings for production environment."""
    if settings.ENVIRONMENT.lower() != "production":
        return

    logger.info("Validating production configuration...")

    # Validate DEBUG is OFF
    if settings.DEBUG:
        raise RuntimeError(
            "CRITICAL: DEBUG must be False in production. "
            "Disable in .env: DEBUG=false"
        )

    # Validate API docs disabled
    if settings.API_DOCS_ENABLED:
        raise RuntimeError(
            "CRITICAL: API_DOCS_ENABLED must be False in production. "
            "Disable in .env: API_DOCS_ENABLED=false"
        )

    # Validate SECRET_KEY is secure
    if not settings.SECRET_KEY or len(settings.SECRET_KEY) < 32:
        raise RuntimeError(
            "CRITICAL: SECRET_KEY must be at least 32 characters. "
            "Set a strong SECRET_KEY in .env"
        )

    weak_markers = {"changeme", "change-me", "development-only", "test-secret-key", "your-secret-key"}
    if any(marker in settings.SECRET_KEY.lower() for marker in weak_markers):
        raise RuntimeError(
            "CRITICAL: SECRET_KEY appears to be a development default. "
            "Set a unique SECRET_KEY in .env for production"
        )

    # Validate CORS origins
    if not settings.CORS_ALLOWED_ORIGINS:
        raise RuntimeError(
            "CRITICAL: CORS_ALLOWED_ORIGINS must be specified for production"
        )

    # Validate session cookie settings for HTTPS
    if settings.SESSION_COOKIE_SAMESITE != "strict":
        logger.warning(
            "WARNING: SESSION_COOKIE_SAMESITE should be 'strict' in production. "
            "Currently set to: " + settings.SESSION_COOKIE_SAMESITE
        )

    # Raise when SMTP is not configured — password reset emails will not be delivered
    if not (settings.SMTP_HOST and settings.SMTP_FROM):
        raise RuntimeError(
            "SMTP_UNCONFIGURED: SMTP_HOST or SMTP_FROM is not set in production. "
            "Password reset emails WILL NOT be delivered. "
            "Set SMTP_HOST, SMTP_PORT, SMTP_FROM (and optionally SMTP_USERNAME/SMTP_PASSWORD) in .env."
        )

    logger.info("✓ Production configuration validation passed")


settings = Settings()
validate_production_settings()
