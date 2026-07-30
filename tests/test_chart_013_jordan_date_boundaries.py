"""
Comprehensive tests for CHART-013: Jordan-local date boundary correctness.

Tests verify that date filtering uses Jordan timezone (UTC+3) correctly,
not UTC or server local time.
"""
import pytest
from datetime import date, datetime, time, timedelta, timezone
from sqlalchemy import func

from database import SessionLocal
import models
from utils.time_utils import (
    today_amman, now_amman, get_amman_tz,
    jordan_day_bounds, jordan_date_range_filter
)


JORDAN_TZ = get_amman_tz()


@pytest.fixture
def test_incidents_for_boundaries(test_db, sample_child, sample_kindergarten):
    """Create incidents at critical timezone boundaries for testing."""
    incidents = []
    
    # Test case 1: Incident at 2026-07-30 23:59:59 Jordan time (20:59:59 UTC)
    # Should be counted for July 30 in Jordan time
    incidents.append(models.Incident(
        kindergarten_id=sample_kindergarten.id,
        child_id=sample_child.id,
        occurred_at=datetime(2026, 7, 30, 20, 59, 59, tzinfo=timezone.utc),
        type=models.IncidentType.OTHER,
        severity_level=models.SeverityLevel.LOW,
        description="Late July 30 Jordan",
    ))
    
    # Test case 2: Incident at 2026-07-31 00:00:00 Jordan time (21:00:00 UTC July 30)
    # Should be counted for July 31 in Jordan time, NOT July 30
    incidents.append(models.Incident(
        kindergarten_id=sample_kindergarten.id,
        child_id=sample_child.id,
        occurred_at=datetime(2026, 7, 30, 21, 0, 0, tzinfo=timezone.utc),
        type=models.IncidentType.OTHER,
        severity_level=models.SeverityLevel.LOW,
        description="Midnight July 31 Jordan",
    ))
    
    # Test case 3: Incident at 2026-07-31 01:00:00 Jordan time (22:00:00 UTC July 30)
    # Should be counted for July 31 in Jordan time
    incidents.append(models.Incident(
        kindergarten_id=sample_kindergarten.id,
        child_id=sample_child.id,
        occurred_at=datetime(2026, 7, 30, 22, 0, 0, tzinfo=timezone.utc),
        type=models.IncidentType.OTHER,
        severity_level=models.SeverityLevel.LOW,
        description="Early July 31 Jordan",
    ))
    
    # Test case 4: Incident at 2026-07-30 20:59:59 UTC (23:59:59 Jordan July 30)
    # Should be counted for July 30 in Jordan time
    incidents.append(models.Incident(
        kindergarten_id=sample_kindergarten.id,
        child_id=sample_child.id,
        occurred_at=datetime(2026, 7, 30, 20, 59, 59, tzinfo=timezone.utc),
        type=models.IncidentType.OTHER,
        severity_level=models.SeverityLevel.LOW,
        description="Late July 30 UTC",
    ))
    
    test_db.add_all(incidents)
    test_db.commit()
    return incidents


def test_jordan_day_bounds_basic():
    """Test that jordan_day_bounds returns correct timezone-aware bounds."""
    target = date(2026, 7, 30)
    start, end = jordan_day_bounds(target)
    
    # Start should be 2026-07-30 00:00:00 Jordan time
    assert start.date() == target
    assert start.hour == 0
    assert start.minute == 0
    assert start.second == 0
    assert start.tzinfo is not None
    
    # End should be 2026-07-31 00:00:00 Jordan time (exclusive)
    assert end.date() == date(2026, 7, 31)
    assert end.hour == 0
    assert end.minute == 0
    assert end.second == 0
    assert end.tzinfo is not None
    
    # End should be exactly 24 hours after start
    assert (end - start).total_seconds() == 86400


def test_jordan_date_range_filter_basic():
    """Test that jordan_date_range_filter returns correct filter conditions."""
    column = models.Incident.occurred_at
    start_date = date(2026, 7, 1)
    end_date = date(2026, 7, 31)
    
    filters = jordan_date_range_filter(column, start_date, end_date)
    
    # Should return exactly 2 filter conditions
    assert len(filters) == 2
    
    # First filter: column >= start_of_start_date
    # Second filter: column < start_of_end_date_plus_1
    # We can't easily inspect SQLAlchemy filter objects, but we can verify they exist


def test_same_day_inclusion(test_db, test_incidents_for_boundaries):
    """Test that incidents on the same Jordan day are correctly included."""
    # Query for July 30 using Jordan date range filter
    filters = jordan_date_range_filter(
        models.Incident.occurred_at,
        date(2026, 7, 30),
        date(2026, 7, 30)
    )
    
    count = test_db.query(func.count(models.Incident.id)).filter(*filters).scalar()
    
    # Should include incidents at 23:59:59 Jordan time on July 30
    # But NOT incidents at 00:00:00 Jordan time on July 31
    assert count == 2  # Two incidents at 20:59:59 UTC (23:59:59 Jordan)


def test_end_date_inclusion(test_db, test_incidents_for_boundaries):
    """Test that incidents on the end date are correctly included."""
    # Query for July 30 to July 31
    filters = jordan_date_range_filter(
        models.Incident.occurred_at,
        date(2026, 7, 30),
        date(2026, 7, 31)
    )
    
    count = test_db.query(func.count(models.Incident.id)).filter(*filters).scalar()
    
    # Should include all 4 incidents
    assert count == 4


def test_cross_midnight_records(test_db, test_incidents_for_boundaries):
    """Test that records crossing midnight are correctly assigned to Jordan days."""
    # Query for July 31 only
    filters = jordan_date_range_filter(
        models.Incident.occurred_at,
        date(2026, 7, 31),
        date(2026, 7, 31)
    )
    
    count = test_db.query(func.count(models.Incident.id)).filter(*filters).scalar()
    
    # Should include incidents at 00:00:00 and 01:00:00 Jordan time on July 31
    # These are stored as 21:00:00 and 22:00:00 UTC on July 30
    assert count == 2


def test_month_boundary(test_db, sample_child, sample_kindergarten):
    """Test that month boundaries are handled correctly."""
    # Create incidents at month boundary
    incidents = [
        # Last moment of July 31 (23:59:59 Jordan = 20:59:59 UTC)
        models.Incident(
            kindergarten_id=sample_kindergarten.id,
            child_id=sample_child.id,
            occurred_at=datetime(2026, 7, 31, 20, 59, 59, tzinfo=timezone.utc),
            type=models.IncidentType.OTHER,
            severity_level=models.SeverityLevel.LOW,
            description="Last moment July",
        ),
        # First moment of August 1 (00:00:00 Jordan = 21:00:00 UTC July 31)
        models.Incident(
            kindergarten_id=sample_kindergarten.id,
            child_id=sample_child.id,
            occurred_at=datetime(2026, 7, 31, 21, 0, 0, tzinfo=timezone.utc),
            type=models.IncidentType.OTHER,
            severity_level=models.SeverityLevel.LOW,
            description="First moment August",
        ),
    ]
    test_db.add_all(incidents)
    test_db.commit()
    
    # Query for July only
    july_filters = jordan_date_range_filter(
        models.Incident.occurred_at,
        date(2026, 7, 1),
        date(2026, 7, 31)
    )
    july_count = test_db.query(func.count(models.Incident.id)).filter(*july_filters).scalar()
    
    # Query for August 1 only
    aug1_filters = jordan_date_range_filter(
        models.Incident.occurred_at,
        date(2026, 8, 1),
        date(2026, 8, 1)
    )
    aug1_count = test_db.query(func.count(models.Incident.id)).filter(*aug1_filters).scalar()
    
    assert july_count == 1  # Only the July 31 incident
    assert aug1_count == 1  # Only the August 1 incident


def test_quarter_boundary(test_db, sample_child, sample_kindergarten):
    """Test that quarter boundaries are handled correctly."""
    # Create incidents at quarter boundary (end of Q3, start of Q4)
    incidents = [
        # Last moment of September 30 (23:59:59 Jordan)
        models.Incident(
            kindergarten_id=sample_kindergarten.id,
            child_id=sample_child.id,
            occurred_at=datetime(2026, 9, 30, 20, 59, 59, tzinfo=timezone.utc),
            type=models.IncidentType.OTHER,
            severity_level=models.SeverityLevel.LOW,
            description="Last moment Q3",
        ),
        # First moment of October 1 (00:00:00 Jordan)
        models.Incident(
            kindergarten_id=sample_kindergarten.id,
            child_id=sample_child.id,
            occurred_at=datetime(2026, 9, 30, 21, 0, 0, tzinfo=timezone.utc),
            type=models.IncidentType.OTHER,
            severity_level=models.SeverityLevel.LOW,
            description="First moment Q4",
        ),
    ]
    test_db.add_all(incidents)
    test_db.commit()
    
    # Query for Q3 (July-September)
    q3_filters = jordan_date_range_filter(
        models.Incident.occurred_at,
        date(2026, 7, 1),
        date(2026, 9, 30)
    )
    q3_count = test_db.query(func.count(models.Incident.id)).filter(*q3_filters).scalar()
    
    # Query for October 1 only
    oct1_filters = jordan_date_range_filter(
        models.Incident.occurred_at,
        date(2026, 10, 1),
        date(2026, 10, 1)
    )
    oct1_count = test_db.query(func.count(models.Incident.id)).filter(*oct1_filters).scalar()
    
    assert q3_count == 1  # Only the September 30 incident
    assert oct1_count == 1  # Only the October 1 incident


def test_year_boundary(test_db, sample_child, sample_kindergarten):
    """Test that year boundaries are handled correctly."""
    # Create incidents at year boundary
    incidents = [
        # Last moment of December 31 (23:59:59 Jordan)
        models.Incident(
            kindergarten_id=sample_kindergarten.id,
            child_id=sample_child.id,
            occurred_at=datetime(2026, 12, 31, 20, 59, 59, tzinfo=timezone.utc),
            type=models.IncidentType.OTHER,
            severity_level=models.SeverityLevel.LOW,
            description="Last moment 2026",
        ),
        # First moment of January 1, 2027 (00:00:00 Jordan)
        models.Incident(
            kindergarten_id=sample_kindergarten.id,
            child_id=sample_child.id,
            occurred_at=datetime(2026, 12, 31, 21, 0, 0, tzinfo=timezone.utc),
            type=models.IncidentType.OTHER,
            severity_level=models.SeverityLevel.LOW,
            description="First moment 2027",
        ),
    ]
    test_db.add_all(incidents)
    test_db.commit()
    
    # Query for 2026 only
    y2026_filters = jordan_date_range_filter(
        models.Incident.occurred_at,
        date(2026, 1, 1),
        date(2026, 12, 31)
    )
    y2026_count = test_db.query(func.count(models.Incident.id)).filter(*y2026_filters).scalar()
    
    # Query for January 1, 2027 only
    jan1_2027_filters = jordan_date_range_filter(
        models.Incident.occurred_at,
        date(2027, 1, 1),
        date(2027, 1, 1)
    )
    jan1_2027_count = test_db.query(func.count(models.Incident.id)).filter(*jan1_2027_filters).scalar()
    
    assert y2026_count == 1  # Only the December 31, 2026 incident
    assert jan1_2027_count == 1  # Only the January 1, 2027 incident


def test_leap_day(test_db, sample_child, sample_kindergarten):
    """Test that leap day (February 29) is handled correctly."""
    # Create incidents on leap day (2028 is a leap year)
    incidents = [
        # February 29, 2028 at 12:00:00 Jordan time (09:00:00 UTC)
        models.Incident(
            kindergarten_id=sample_kindergarten.id,
            child_id=sample_child.id,
            occurred_at=datetime(2028, 2, 29, 9, 0, 0, tzinfo=timezone.utc),
            type=models.IncidentType.OTHER,
            severity_level=models.SeverityLevel.LOW,
            description="Leap day noon",
        ),
    ]
    test_db.add_all(incidents)
    test_db.commit()
    
    # Query for February 29, 2028
    leap_day_filters = jordan_date_range_filter(
        models.Incident.occurred_at,
        date(2028, 2, 29),
        date(2028, 2, 29)
    )
    leap_day_count = test_db.query(func.count(models.Incident.id)).filter(*leap_day_filters).scalar()
    
    assert leap_day_count == 1


def test_utc_vs_jordan_conversion(test_db, sample_child, sample_kindergarten):
    """Test that UTC timestamps are correctly converted to Jordan time for filtering."""
    # Create an incident at 2026-07-30 22:00:00 UTC (2026-07-31 01:00:00 Jordan)
    incident = models.Incident(
        kindergarten_id=sample_kindergarten.id,
        child_id=sample_child.id,
        occurred_at=datetime(2026, 7, 30, 22, 0, 0, tzinfo=timezone.utc),
        type=models.IncidentType.OTHER,
        severity_level=models.SeverityLevel.LOW,
        description="UTC July 30, Jordan July 31",
    )
    test_db.add(incident)
    test_db.commit()
    
    # Query for July 30 in Jordan time - should NOT include this incident
    july30_filters = jordan_date_range_filter(
        models.Incident.occurred_at,
        date(2026, 7, 30),
        date(2026, 7, 30)
    )
    july30_count = test_db.query(func.count(models.Incident.id)).filter(*july30_filters).scalar()
    
    # Query for July 31 in Jordan time - SHOULD include this incident
    july31_filters = jordan_date_range_filter(
        models.Incident.occurred_at,
        date(2026, 7, 31),
        date(2026, 7, 31)
    )
    july31_count = test_db.query(func.count(models.Incident.id)).filter(*july31_filters).scalar()
    
    assert july30_count == 0  # Incident is in Jordan July 31, not July 30
    assert july31_count == 1  # Incident is in Jordan July 31


def test_aggregation_counts(test_db, sample_child, sample_kindergarten):
    """Test that aggregation counts are correct when using Jordan date filters."""
    # Create multiple incidents across different Jordan days
    incidents = [
        # July 30 at 23:00 Jordan (20:00 UTC)
        models.Incident(
            kindergarten_id=sample_kindergarten.id,
            child_id=sample_child.id,
            occurred_at=datetime(2026, 7, 30, 20, 0, 0, tzinfo=timezone.utc),
            type=models.IncidentType.OTHER,
            severity_level=models.SeverityLevel.LOW,
            description="July 30 evening",
        ),
        # July 31 at 01:00 Jordan (22:00 UTC July 30)
        models.Incident(
            kindergarten_id=sample_kindergarten.id,
            child_id=sample_child.id,
            occurred_at=datetime(2026, 7, 30, 22, 0, 0, tzinfo=timezone.utc),
            type=models.IncidentType.OTHER,
            severity_level=models.SeverityLevel.LOW,
            description="July 31 early morning",
        ),
        # July 31 at 15:00 Jordan (12:00 UTC)
        models.Incident(
            kindergarten_id=sample_kindergarten.id,
            child_id=sample_child.id,
            occurred_at=datetime(2026, 7, 31, 12, 0, 0, tzinfo=timezone.utc),
            type=models.IncidentType.OTHER,
            severity_level=models.SeverityLevel.LOW,
            description="July 31 afternoon",
        ),
    ]
    test_db.add_all(incidents)
    test_db.commit()
    
    # Query for July 30
    july30_filters = jordan_date_range_filter(
        models.Incident.occurred_at,
        date(2026, 7, 30),
        date(2026, 7, 30)
    )
    july30_count = test_db.query(func.count(models.Incident.id)).filter(*july30_filters).scalar()
    
    # Query for July 31
    july31_filters = jordan_date_range_filter(
        models.Incident.occurred_at,
        date(2026, 7, 31),
        date(2026, 7, 31)
    )
    july31_count = test_db.query(func.count(models.Incident.id)).filter(*july31_filters).scalar()
    
    # Query for July 30-31
    july30_31_filters = jordan_date_range_filter(
        models.Incident.occurred_at,
        date(2026, 7, 30),
        date(2026, 7, 31)
    )
    july30_31_count = test_db.query(func.count(models.Incident.id)).filter(*july30_31_filters).scalar()
    
    assert july30_count == 1  # Only the July 30 evening incident
    assert july31_count == 2  # The July 31 early morning and afternoon incidents
    assert july30_31_count == 3  # All three incidents


def test_export_date_correctness(test_db, sample_child, sample_kindergarten):
    """Test that export date ranges are correct when using Jordan date filters."""
    # Create incidents at timezone boundaries
    incidents = [
        # July 30 at 23:59 Jordan (20:59 UTC)
        models.Incident(
            kindergarten_id=sample_kindergarten.id,
            child_id=sample_child.id,
            occurred_at=datetime(2026, 7, 30, 20, 59, 0, tzinfo=timezone.utc),
            type=models.IncidentType.OTHER,
            severity_level=models.SeverityLevel.LOW,
            description="July 30 late",
        ),
        # July 31 at 00:01 Jordan (21:01 UTC July 30)
        models.Incident(
            kindergarten_id=sample_kindergarten.id,
            child_id=sample_child.id,
            occurred_at=datetime(2026, 7, 30, 21, 1, 0, tzinfo=timezone.utc),
            type=models.IncidentType.OTHER,
            severity_level=models.SeverityLevel.LOW,
            description="July 31 early",
        ),
    ]
    test_db.add_all(incidents)
    test_db.commit()
    
    # Simulate export for July 30 only
    export_filters = jordan_date_range_filter(
        models.Incident.occurred_at,
        date(2026, 7, 30),
        date(2026, 7, 30)
    )
    export_incidents = test_db.query(models.Incident).filter(*export_filters).all()
    
    # Should only include the July 30 incident, not the July 31 incident
    assert len(export_incidents) == 1
    assert "July 30 late" in export_incidents[0].description


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
