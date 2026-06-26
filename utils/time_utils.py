from datetime import datetime, timezone, date
import zoneinfo
from config import settings

def get_amman_tz() -> zoneinfo.ZoneInfo:
    """Safely retrieves the Amman timezone, falling back to UTC if not found."""
    try:
        return zoneinfo.ZoneInfo(settings.AMMAN_TIMEZONE)
    except zoneinfo.ZoneInfoNotFoundError:
        return timezone.utc

def now_amman() -> datetime:
    """Returns the current datetime in the Amman timezone."""
    return datetime.now(get_amman_tz())

def today_amman() -> date:
    """Returns the current date in the Amman timezone."""
    return now_amman().date()
