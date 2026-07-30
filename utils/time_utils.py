from datetime import datetime, timezone, date, time, timedelta
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

def jordan_day_bounds(target_date: date) -> tuple[datetime, datetime]:
    """
    Returns the start and end of a Jordan-local day as timezone-aware datetimes.
    
    This is critical for CHART-013: when filtering DateTime columns by date,
    we must use half-open intervals [start_of_day, next_day) in Jordan time,
    not func.date() which extracts dates in UTC.
    
    Args:
        target_date: The date to get bounds for (in Jordan time)
    
    Returns:
        Tuple of (start_datetime, end_datetime_exclusive) in Jordan timezone
        
    Example:
        start, end = jordan_day_bounds(date(2026, 7, 30))
        # start = 2026-07-30 00:00:00+03:00
        # end = 2026-07-31 00:00:00+03:00
        # Query: column >= start AND column < end
    """
    amman_tz = get_amman_tz()
    start = datetime.combine(target_date, time.min, tzinfo=amman_tz)
    end = datetime.combine(target_date + timedelta(days=1), time.min, tzinfo=amman_tz)
    return start, end

def jordan_date_range_filter(column, start_date: date, end_date: date):
    """
    Returns SQLAlchemy filter conditions for a date range in Jordan time.
    
    This replaces the buggy pattern:
        func.date(column) >= start_date, func.date(column) <= end_date
    
    With the correct pattern:
        column >= start_of_start_date, column < start_of_end_date_plus_1
    
    The filter converts Jordan-local dates to UTC for comparison with
    timezone-aware DateTime columns stored in the database.
    
    Args:
        column: SQLAlchemy column (DateTime type)
        start_date: Inclusive start date (Jordan time)
        end_date: Inclusive end date (Jordan time)
    
    Returns:
        List of SQLAlchemy filter conditions
        
    Example:
        filters = jordan_date_range_filter(
            models.Incident.occurred_at,
            date(2026, 7, 1),
            date(2026, 7, 31)
        )
        query = query.filter(*filters)
    """
    amman_tz = get_amman_tz()
    # Create Jordan-local datetimes
    start_dt = datetime.combine(start_date, time.min, tzinfo=amman_tz)
    end_dt = datetime.combine(end_date + timedelta(days=1), time.min, tzinfo=amman_tz)
    # Convert to UTC for database comparison (SQLite stores in UTC)
    start_dt_utc = start_dt.astimezone(timezone.utc).replace(tzinfo=None)
    end_dt_utc = end_dt.astimezone(timezone.utc).replace(tzinfo=None)
    return [column >= start_dt_utc, column < end_dt_utc]
