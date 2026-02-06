"""
Configuration management for KinJo platform
"""
from pydantic_settings import BaseSettings
from pydantic import ConfigDict
from typing import Dict, List


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
    STORAGE_PROVIDER: str = "local"  # local or s3
    ATTACHMENTS_DIR: str = "data/attachments"
    MAX_ATTACHMENT_SIZE_MB: int = 10
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
        "جرش", "عجلون", "الطفيلة", "الكرك", "معان", "السلط", "مادبا"
    ]
    JORDAN_GOVERNORATES_ENGLISH: List[str] = [
        "Amman", "Irbid", "Zarqa", "Aqaba", "Mafraq",
        "Jerash", "Ajloun", "Tafilah", "Karak", "Ma'an", "Salt", "Madaba"
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
        "salt": "السلط",
        "السلط": "السلط",
        "madaba": "مادبا",
        "مادبا": "مادبا"
    }
    ACTIVE_LIKE_ENROLLMENT_STATUSES: List[str] = [
        "ACTIVE",
        "ACCEPTED",
        "PENDING_REVIEW"
    ]

    # Message limits
    MAX_MESSAGE_RECIPIENTS: int = 10000

    # Backup Configuration
    BACKUP_DIR: str = "backups"
    BACKUP_RETENTION_DAYS: int = 30
    BACKUP_SCHEDULE_HOUR: int = 2  # 2 AM
    BACKUP_CLEANUP_HOUR: int = 3   # 3 AM

    model_config = ConfigDict(
        env_file=".env",
        case_sensitive=True,
        extra="ignore"
    )


settings = Settings()
