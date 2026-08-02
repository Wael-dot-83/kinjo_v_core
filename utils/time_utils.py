from datetime import datetime, timezone, date, time, timedelta
from typing import Optional
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
    # Convert to UTC and keep tzinfo. The offset is deliberately NOT stripped:
    # a naive bound leaves its meaning to the database session, which made this
    # filter silently lose 21:00-24:00 Jordan on SQLite and on any PostgreSQL
    # session whose TimeZone was not UTC. Aware bounds are unambiguous everywhere,
    # and db_types.UTCDateTime normalises them per dialect on bind. See D-11.
    start_dt_utc = start_dt.astimezone(timezone.utc)
    end_dt_utc = end_dt.astimezone(timezone.utc)
    return [column >= start_dt_utc, column < end_dt_utc]


# ---------------------------------------------------------------------------
# Presentation-boundary helpers (N16).
#
# Storage is aware UTC (db_types.UTCDateTime). These convert at the point of
# output, so the decision "UTC or Jordan?" is made once per consumer instead of
# being reimplemented inline. Which to use:
#
#   to_utc_iso      machine/API timestamps, and anything a browser will localise
#                   itself via `new Date(...)` + toLocaleString().
#   to_jordan_iso   a Jordan-facing datetime the server renders as text.
#   to_jordan_date  ANY server-side calendar derivation — day grouping, month
#                   buckets, export date columns. This is the one that matters:
#                   taking .date() straight off a UTC value puts every event
#                   between 21:00 and 24:00 Jordan on the previous day.
#
# Date-only columns (Column(Date)) carry no time or zone. Never pass them
# through these helpers; converting a date-only business value is a bug.
# ---------------------------------------------------------------------------


def parse_stored_utc(value: Optional[datetime]) -> Optional[datetime]:
    """Normalise a stored timestamp to aware UTC.

    Naive input is treated as UTC, matching ``db_types.UTCDateTime``'s own
    convention for legacy rows. Aware input is converted, so calling this twice
    is harmless. The input is never mutated.
    """
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def to_utc_iso(value: Optional[datetime]) -> Optional[str]:
    """ISO-8601 in UTC with an explicit ``+00:00`` offset.

    The offset is the point: a date-time string without one is parsed by
    JavaScript's ``new Date()`` as *local* time, which silently misreads the
    instant in every browser outside UTC.
    """
    normalised = parse_stored_utc(value)
    return None if normalised is None else normalised.isoformat()


def to_jordan_iso(value: Optional[datetime]) -> Optional[str]:
    """ISO-8601 in Asia/Amman, with the offset included."""
    normalised = parse_stored_utc(value)
    return None if normalised is None else normalised.astimezone(get_amman_tz()).isoformat()


def to_jordan_date(value: Optional[datetime]) -> Optional[date]:
    """The Jordan calendar date of a stored instant.

    Use for every server-side date or month derivation. ``get_amman_tz()``
    resolves through the tz database rather than a hardcoded +03:00, so
    historical instants (Jordan observed DST until 2022) are handled correctly.
    """
    normalised = parse_stored_utc(value)
    return None if normalised is None else normalised.astimezone(get_amman_tz()).date()
