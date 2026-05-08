"""
Test for AdvancedAnalyticsCache compute/store logic in AnalyticsService
"""
import pytest
from datetime import date, timedelta
from sqlalchemy.orm import Session
import models
from analytics_service import AnalyticsService
from kpi_service import KPIService

def test_compute_and_retrieve_advanced_analytics_cache(test_db):
    # Setup: create a kindergarten and minimal data
    kg = models.Kindergarten(
        name_ar="KG Test",
        name_en="KG Test",
        governorate="TestGov",
        city="TestCity",
        area="TestArea",
        address_line="Test Address",
        contact_phone="1234567890",
        status=models.KindergartenStatus.ACTIVE
    )
    test_db.add(kg)
    test_db.commit()

    # Compute and store advanced analytics cache
    period_start = date.today() - timedelta(days=30)
    period_end = date.today()
    cache = AnalyticsService.compute_advanced_analytics(
        test_db,
        models.AnalyticsDimensionType.KINDERGARTEN,
        str(kg.id),
        models.AnalyticsPeriodType.MONTHLY,
        period_start,
        period_end
    )
    assert cache is not None
    assert cache.dimension_type == models.AnalyticsDimensionType.KINDERGARTEN
    assert cache.dimension_id == str(kg.id)
    assert cache.period_type == models.AnalyticsPeriodType.MONTHLY
    assert cache.period_start == period_start
    assert cache.period_end == period_end

    # Retrieve the cache
    retrieved = AnalyticsService.get_advanced_analytics_cache(
        test_db,
        models.AnalyticsDimensionType.KINDERGARTEN,
        str(kg.id),
        models.AnalyticsPeriodType.MONTHLY,
        period_start,
        period_end
    )
    assert retrieved is not None
    assert retrieved.id == cache.id
    assert retrieved.attendance_rate == cache.attendance_rate
    # Clean up
    test_db.delete(retrieved)
    test_db.delete(kg)
    test_db.commit()
