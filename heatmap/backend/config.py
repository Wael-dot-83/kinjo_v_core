"""Heatmap module configuration loaded from environment variables."""
from __future__ import annotations
import os
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent

class HeatmapSettings:
    # API
    API_PREFIX: str = os.getenv("HEATMAP_API_PREFIX", "/api/heatmap")

    # Scheduler
    CRON_HOUR:   int = int(os.getenv("HEATMAP_CRON_HOUR", "2"))
    CRON_MINUTE: int = int(os.getenv("HEATMAP_CRON_MINUTE", "0"))

    # Paths
    DATA_DIR:          Path = Path(os.getenv("HEATMAP_DATA_DIR",   str(BASE_DIR / "data")))
    GEOJSON_OUT_DIR:   Path = Path(os.getenv("GEOJSON_OUTPUT_DIR", "static/heatmap"))
    LOG_DIR:           Path = Path(os.getenv("HEATMAP_LOG_DIR",    "logs"))

    # Alerts
    SENDGRID_API_KEY:  str  = os.getenv("SENDGRID_API_KEY", "")
    ALERT_EMAIL_TO:    str  = os.getenv("ALERT_EMAIL_TO",   "admin@kinjo.jo")
    ALERT_EMAIL_FROM:  str  = os.getenv("ALERT_EMAIL_FROM", "alerts@kinjo.jo")
    TWILIO_ACCOUNT_SID:str  = os.getenv("TWILIO_ACCOUNT_SID", "")
    TWILIO_AUTH_TOKEN: str  = os.getenv("TWILIO_AUTH_TOKEN",  "")
    TWILIO_FROM_NUMBER:str  = os.getenv("TWILIO_FROM_NUMBER", "")
    ALERT_SMS_TO:      str  = os.getenv("ALERT_SMS_TO",       "")
    INAPP_WS_PUSH_URL: str  = os.getenv("INAPP_WS_PUSH_URL",  "")

    # CDN
    CDN_PUSH_URL:  str = os.getenv("CDN_PUSH_URL",  "")
    CDN_API_KEY:   str = os.getenv("CDN_API_KEY",   "")


settings = HeatmapSettings()
