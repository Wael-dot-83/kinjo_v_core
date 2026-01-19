"""
Configuration management for KinJo platform
"""
from pydantic_settings import BaseSettings
from typing import List


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

    # Localization
    DEFAULT_LANGUAGE: str = "ar"
    SUPPORTED_LANGUAGES: List[str] = ["ar", "en"]

    # Business Rules
    MIN_CHILD_AGE_DAYS: int = 70
    MAX_CHILD_AGE_MONTHS: int = 56  # 4 years 8 months
    WAITLIST_OFFER_EXPIRY_HOURS: int = 48

    # Jordan-specific
    JORDAN_PHONE_PATTERN: str = r"^(\+962|00962|0)[0-9]{9}$"
    JORDAN_GOVERNORATES: List[str] = [
        "عمان", "إربد", "الزرقاء", "العقبة", "المفرق",
        "جرش", "عجلون", "الطفيلة", "الكرك", "معان", "السلط", "مادبا"
    ]

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
