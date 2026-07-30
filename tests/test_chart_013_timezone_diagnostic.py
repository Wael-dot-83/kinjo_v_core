"""
Diagnostic test to verify func.date() timezone behavior.

This test demonstrates the CHART-013 issue: when DateTime columns store UTC timestamps,
func.date() extracts the date in UTC, not Jordan time, causing a 3-hour skew.
"""
import pytest
from datetime import datetime, date, time, timedelta, timezone
from sqlalchemy import func
from sqlalchemy.orm import Session

from database import SessionLocal
import models
from utils.time_utils import now_amman, today_amman, get_amman_tz


JORDAN_TZ = get_amman_tz()


@pytest.fixture
def test_incidents(test_db: Session, sample_child, sample_kindergarten):
    """Create test incidents at critical timezone boundaries."""
    # Incident at 2026-07-30 22:00 Jordan time (19:00 UTC)
    # In Jordan: July 30 at 22:00
    # In UTC: July 30 at 19:00
    # func.date() in UTC: July 30 ✓
    incident_july30_late = models.Incident(
        kindergarten_id=sample_kindergarten.id,
        child_id=sample_child.id,
        occurred_at=datetime(2026, 7, 30, 19, 0, 0, tzinfo=timezone.utc),  # 22:00 Jordan
        type=models.IncidentType.OTHER,
        severity_level=models.SeverityLevel.LOW,
        description="Test incident late July 30",
    )
    
    # Incident at 2026-07-31 01:00 Jordan time (2026-07-30 22:00 UTC)
    # In Jordan: July 31 at 01:00
    # In UTC: July 30 at 22:00
    # func.date() in UTC: July 30 ✗ (should be July 31)
    incident_july31_early = models.Incident(
        kindergarten_id=sample_kindergarten.id,
        child_id=sample_child.id,
        occurred_at=datetime(2026, 7, 30, 22, 0, 0, tzinfo=timezone.utc),  # 01:00 Jordan July 31
        type=models.IncidentType.OTHER,
        severity_level=models.SeverityLevel.LOW,
        description="Test incident early July 31",
    )
    
    test_db.add_all([incident_july30_late, incident_july31_early])
    test_db.commit()
    
    return incident_july30_late, incident_july31_early


def test_func_date_utc_vs_jordan(test_db: Session, test_incidents):
    """Verify that func.date() extracts dates in UTC, not Jordan time."""
    incident_late, incident_early = test_incidents
    
    # Query using func.date() - this extracts date in DB timezone (UTC)
    results = test_db.query(
        models.Incident.id,
        func.date(models.Incident.occurred_at).label('extracted_date')
    ).filter(
        models.Incident.id.in_([incident_late.id, incident_early.id])
    ).all()
    
    # Both incidents will show July 30 when using func.date() in UTC
    # This is WRONG for the second incident (should be July 31 in Jordan time)
    
    extracted_dates = {row.id: row.extracted_date for row in results}
    
    print("\n=== func.date() Behavior Test ===")
    print(f"Incident 1 (22:00 Jordan July 30): extracted date = {extracted_dates[incident_late.id]}")
    print(f"Incident 2 (01:00 Jordan July 31): extracted date = {extracted_dates[incident_early.id]}")
    print("\nExpected in Jordan time:")
    print(f"  Incident 1: July 30")
    print(f"  Incident 2: July 31")
    print("\nActual (UTC extraction):")
    print(f"  Incident 1: {extracted_dates[incident_late.id]}")
    print(f"  Incident 2: {extracted_dates[incident_early.id]}")
    
    # This test documents the bug - both will show July 30 in UTC
    # The second incident should be July 31 in Jordan time
    assert extracted_dates[incident_late.id] == date(2026, 7, 30)
    assert extracted_dates[incident_early.id] == date(2026, 7, 30)  # BUG: should be July 31
    
    print("\n⚠️  CHART-013 CONFIRMED: func.date() extracts UTC dates, not Jordan dates")
    print("   This causes incidents between 21:00-23:59 Jordan time to be counted for the wrong day")


def test_correct_jordan_date_extraction(test_db: Session, test_incidents):
    """Demonstrate the correct way to extract Jordan-local dates."""
    incident_late, incident_early = test_incidents
    
    # Correct approach: convert to Jordan timezone before extracting date
    # In PostgreSQL: DATE(occurred_at AT TIME ZONE 'UTC' AT TIME ZONE 'Asia/Amman')
    # In SQLAlchemy: func.date(func.timezone('Asia/Amman', func.timezone('UTC', occurred_at)))
    
    # For now, we'll do this in Python to demonstrate the correct behavior
    incidents = test_db.query(models.Incident).filter(
        models.Incident.id.in_([incident_late.id, incident_early.id])
    ).all()
    
    print("\n=== Correct Jordan Date Extraction ===")
    for incident in incidents:
        # Convert UTC timestamp to Jordan time
        jordan_time = incident.occurred_at.astimezone(JORDAN_TZ)
        jordan_date = jordan_time.date()
        
        print(f"Incident {incident.id}:")
        print(f"  UTC time: {incident.occurred_at}")
        print(f"  Jordan time: {jordan_time}")
        print(f"  Jordan date: {jordan_date}")
    
    # This shows the correct dates
    assert incidents[0].occurred_at.astimezone(JORDAN_TZ).date() == date(2026, 7, 30)
    assert incidents[1].occurred_at.astimezone(JORDAN_TZ).date() == date(2026, 7, 31)  # Correct!
    
    print("\n✓ Correct approach: convert to Jordan timezone before extracting date")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
