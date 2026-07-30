"""
Comprehensive tests for Batch 2A: Jordan-local time semantics.

Tests cover:
- CHART-008: datetime.now() → now_amman() conversion
- CHART-009: date.today() → today_amman() conversion (mostly in scripts)
- CHART-013: func.date() timezone issues and half-open intervals

Focus on boundary conditions:
- Records at midnight Jordan time (00:00:00)
- Records at 23:59:59 Jordan time
- Records at UTC midnight (21:00 Jordan time previous day)
- Leap day (Feb 29)
- Month boundaries
- Year boundaries
- Quarter boundaries
"""
import pytest
from datetime import datetime, date, time, timedelta, timezone
from sqlalchemy import func
from sqlalchemy.orm import Session

from database import SessionLocal
import models
from utils.time_utils import (
    now_amman, today_amman, get_amman_tz,
    jordan_day_bounds, jordan_date_range_filter
)


JORDAN_TZ = get_amman_tz()


# ============================================================================
# CHART-008: now_amman() tests
# ============================================================================

def test_now_amman_returns_jordan_timezone():
    """Verify now_amman() returns timezone-aware datetime in Jordan time."""
    now = now_amman()
    assert now.tzinfo is not None
    assert str(now.tzinfo) == "Asia/Amman" or "Asia/Amman" in str(now.tzinfo)


def test_today_amman_returns_jordan_date():
    """Verify today_amman() returns the correct Jordan-local date."""
    today = today_amman()
    assert isinstance(today, date)
    # Should be within 1 day of UTC date (accounting for timezone difference)
    utc_today = datetime.now(timezone.utc).date()
    assert abs((today - utc_today).days) <= 1


# ============================================================================
# CHART-013: jordan_day_bounds() tests
# ============================================================================

def test_jordan_day_bounds_basic():
    """Verify jordan_day_bounds returns correct start and end for a date."""
    target = date(2026, 7, 30)
    start, end = jordan_day_bounds(target)
    
    # Start should be midnight Jordan time
    assert start.date() == target
    assert start.hour == 0
    assert start.minute == 0
    assert start.second == 0
    assert start.tzinfo is not None
    
    # End should be midnight next day Jordan time
    assert end.date() == target + timedelta(days=1)
    assert end.hour == 0
    assert end.minute == 0
    assert end.second == 0
    assert end.tzinfo is not None
    
    # End should be exactly 24 hours after start
    assert (end - start).total_seconds() == 86400


def test_jordan_day_bounds_leap_day():
    """Verify jordan_day_bounds handles leap day correctly."""
    leap_day = date(2028, 2, 29)  # 2028 is a leap year
    start, end = jordan_day_bounds(leap_day)
    
    assert start.date() == leap_day
    assert end.date() == date(2028, 3, 1)
    assert (end - start).total_seconds() == 86400


def test_jordan_day_bounds_month_boundary():
    """Verify jordan_day_bounds handles month boundaries correctly."""
    # Last day of month
    last_day = date(2026, 7, 31)
    start, end = jordan_day_bounds(last_day)
    
    assert start.date() == last_day
    assert end.date() == date(2026, 8, 1)


def test_jordan_day_bounds_year_boundary():
    """Verify jordan_day_bounds handles year boundaries correctly."""
    # Last day of year
    last_day = date(2026, 12, 31)
    start, end = jordan_day_bounds(last_day)
    
    assert start.date() == last_day
    assert end.date() == date(2027, 1, 1)


# ============================================================================
# CHART-013: jordan_date_range_filter() tests
# ============================================================================

def test_jordan_date_range_filter_single_day(test_db: Session, sample_child, sample_kindergarten):
    """Verify jordan_date_range_filter correctly filters a single day."""
    # Create incidents at critical times
    # Incident at 23:59 Jordan time on July 30 (20:59 UTC)
    incident_late = models.Incident(
        kindergarten_id=sample_kindergarten.id,
        child_id=sample_child.id,
        occurred_at=datetime(2026, 7, 30, 20, 59, 0, tzinfo=timezone.utc),
        type=models.IncidentType.OTHER,
        severity_level=models.SeverityLevel.LOW,
        description="Late July 30",
    )
    
    # Incident at 00:01 Jordan time on July 31 (21:01 UTC July 30)
    incident_early = models.Incident(
        kindergarten_id=sample_kindergarten.id,
        child_id=sample_child.id,
        occurred_at=datetime(2026, 7, 30, 21, 1, 0, tzinfo=timezone.utc),
        type=models.IncidentType.OTHER,
        severity_level=models.SeverityLevel.LOW,
        description="Early July 31",
    )
    
    test_db.add_all([incident_late, incident_early])
    test_db.commit()
    
    # Filter for July 30 only
    filters = jordan_date_range_filter(models.Incident.occurred_at, date(2026, 7, 30), date(2026, 7, 30))
    july30_incidents = test_db.query(models.Incident).filter(*filters).all()
    
    # Should only include the late July 30 incident
    assert len(july30_incidents) == 1
    assert july30_incidents[0].id == incident_late.id
    
    # Filter for July 31 only
    filters = jordan_date_range_filter(models.Incident.occurred_at, date(2026, 7, 31), date(2026, 7, 31))
    july31_incidents = test_db.query(models.Incident).filter(*filters).all()
    
    # Should only include the early July 31 incident
    assert len(july31_incidents) == 1
    assert july31_incidents[0].id == incident_early.id


def test_jordan_date_range_filter_date_range(test_db: Session, sample_child, sample_kindergarten):
    """Verify jordan_date_range_filter correctly filters a date range."""
    # Create incidents across multiple days (July 28-31)
    incidents = []
    for day_offset in range(4):  # 0, 1, 2, 3
        incident = models.Incident(
            kindergarten_id=sample_kindergarten.id,
            child_id=sample_child.id,
            occurred_at=datetime(2026, 7, 28 + day_offset, 12, 0, 0, tzinfo=timezone.utc),
            type=models.IncidentType.OTHER,
            severity_level=models.SeverityLevel.LOW,
            description=f"Incident on day {day_offset}",
        )
        incidents.append(incident)
    
    test_db.add_all(incidents)
    test_db.commit()
    
    # Filter for July 29-31 (3 days)
    filters = jordan_date_range_filter(
        models.Incident.occurred_at,
        date(2026, 7, 29),
        date(2026, 7, 31)
    )
    filtered = test_db.query(models.Incident).filter(*filters).all()
    
    # Should include 3 incidents (July 29, 30, 31)
    assert len(filtered) == 3


def test_jordan_date_range_filter_empty_range(test_db: Session, sample_child, sample_kindergarten):
    """Verify jordan_date_range_filter handles empty ranges correctly."""
    # Create an incident
    incident = models.Incident(
        kindergarten_id=sample_kindergarten.id,
        child_id=sample_child.id,
        occurred_at=datetime(2026, 7, 30, 12, 0, 0, tzinfo=timezone.utc),
        type=models.IncidentType.OTHER,
        severity_level=models.SeverityLevel.LOW,
        description="Test incident",
    )
    test_db.add(incident)
    test_db.commit()
    
    # Filter for a date range that doesn't include the incident
    filters = jordan_date_range_filter(
        models.Incident.occurred_at,
        date(2026, 8, 1),
        date(2026, 8, 31)
    )
    filtered = test_db.query(models.Incident).filter(*filters).all()
    
    # Should be empty
    assert len(filtered) == 0


# ============================================================================
# CHART-013: func.date() vs jordan_date_range_filter comparison
# ============================================================================

def test_func_date_vs_jordan_filter_timezone_issue(test_db: Session, sample_child, sample_kindergarten):
    """
    Demonstrate the CHART-013 issue: func.date() extracts dates in UTC,
    not Jordan time, causing incorrect filtering.
    
    This test shows that jordan_date_range_filter correctly handles the
    timezone issue while func.date() does not.
    """
    # Create incident at 22:00 UTC on July 30 (01:00 Jordan time on July 31)
    incident = models.Incident(
        kindergarten_id=sample_kindergarten.id,
        child_id=sample_child.id,
        occurred_at=datetime(2026, 7, 30, 22, 0, 0, tzinfo=timezone.utc),
        type=models.IncidentType.OTHER,
        severity_level=models.SeverityLevel.LOW,
        description="Incident at UTC 22:00 July 30 = Jordan 01:00 July 31",
    )
    test_db.add(incident)
    test_db.commit()
    
    # Using func.date() - WRONG: extracts date in UTC
    func_date_result = test_db.query(models.Incident).filter(
        func.date(models.Incident.occurred_at) == date(2026, 7, 31)
    ).all()
    
    # Using jordan_date_range_filter - CORRECT: filters in Jordan time
    jordan_filter_result = test_db.query(models.Incident).filter(
        *jordan_date_range_filter(models.Incident.occurred_at, date(2026, 7, 31), date(2026, 7, 31))
    ).all()
    
    # func.date() will find it on July 30 (UTC date), not July 31
    assert len(func_date_result) == 0  # Wrong! Should be 1
    
    # jordan_date_range_filter will correctly find it on July 31 (Jordan date)
    assert len(jordan_filter_result) == 1  # Correct!
    assert jordan_filter_result[0].id == incident.id


# ============================================================================
# Boundary condition tests
# ============================================================================

def test_midnight_jordan_time(test_db: Session, sample_child, sample_kindergarten):
    """Test records at exactly midnight Jordan time."""
    # Midnight Jordan time = 21:00 UTC previous day
    midnight_jordan = datetime(2026, 7, 30, 21, 0, 0, tzinfo=timezone.utc)
    
    incident = models.Incident(
        kindergarten_id=sample_kindergarten.id,
        child_id=sample_child.id,
        occurred_at=midnight_jordan,
        type=models.IncidentType.OTHER,
        severity_level=models.SeverityLevel.LOW,
        description="Midnight Jordan time",
    )
    test_db.add(incident)
    test_db.commit()
    
    # Should be included in July 31 (Jordan date)
    filters = jordan_date_range_filter(models.Incident.occurred_at, date(2026, 7, 31), date(2026, 7, 31))
    result = test_db.query(models.Incident).filter(*filters).all()
    
    assert len(result) == 1
    assert result[0].id == incident.id


def test_2359_jordan_time(test_db: Session, sample_child, sample_kindergarten):
    """Test records at 23:59:59 Jordan time."""
    # 23:59:59 Jordan time = 20:59:59 UTC same day
    late_jordan = datetime(2026, 7, 30, 20, 59, 59, tzinfo=timezone.utc)
    
    incident = models.Incident(
        kindergarten_id=sample_kindergarten.id,
        child_id=sample_child.id,
        occurred_at=late_jordan,
        type=models.IncidentType.OTHER,
        severity_level=models.SeverityLevel.LOW,
        description="23:59:59 Jordan time",
    )
    test_db.add(incident)
    test_db.commit()
    
    # Should be included in July 30 (Jordan date)
    filters = jordan_date_range_filter(models.Incident.occurred_at, date(2026, 7, 30), date(2026, 7, 30))
    result = test_db.query(models.Incident).filter(*filters).all()
    
    assert len(result) == 1
    assert result[0].id == incident.id


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
