"""
Test cache invalidation and warming for AdvancedAnalyticsCache
"""
import pytest
from datetime import date, timedelta
import models
from analytics_service import AnalyticsService

@pytest.fixture
def setup_cache(test_db):
    kg = models.Kindergarten(
        name_ar="KG Cache",
        name_en="KG Cache",
        governorate="TestGov",
        city="TestCity",
        area="TestArea",
        address_line="Test Address",
        contact_phone="1234567890",
        status=models.KindergartenStatus.ACTIVE
    )
    test_db.add(kg)
    test_db.commit()
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
    yield test_db, kg, period_start, period_end
    # Only delete cache if it still exists
    cache2 = AnalyticsService.get_advanced_analytics_cache(
        test_db,
        models.AnalyticsDimensionType.KINDERGARTEN,
        str(kg.id),
        models.AnalyticsPeriodType.MONTHLY,
        period_start,
        period_end
    )
    if cache2:
        test_db.delete(cache2)
    test_db.delete(kg)
    test_db.commit()

def test_invalidate_advanced_analytics_cache(setup_cache):
    test_db, kg, period_start, period_end = setup_cache
    # Invalidate
    count = AnalyticsService.invalidate_advanced_analytics_cache(
        test_db,
        dimension_type=models.AnalyticsDimensionType.KINDERGARTEN,
        dimension_id=str(kg.id),
        period_type=models.AnalyticsPeriodType.MONTHLY,
        period_start=period_start,
        period_end=period_end
    )
    assert count == 1
    # Confirm deletion
    cache = AnalyticsService.get_advanced_analytics_cache(
        test_db,
        models.AnalyticsDimensionType.KINDERGARTEN,
        str(kg.id),
        models.AnalyticsPeriodType.MONTHLY,
        period_start,
        period_end
    )
    assert cache is None

def test_warm_advanced_analytics_cache(test_db):
    kg = models.Kindergarten(
        name_ar="KG Warm",
        name_en="KG Warm",
        governorate="TestGov",
        city="TestCity",
        area="TestArea",
        address_line="Test Address",
        contact_phone="1234567890",
        status=models.KindergartenStatus.ACTIVE
    )
    test_db.add(kg)
    test_db.commit()
    period_start = date.today() - timedelta(days=30)
    period_end = date.today()
    count = AnalyticsService.warm_advanced_analytics_cache(
        test_db,
        models.AnalyticsDimensionType.KINDERGARTEN,
        [str(kg.id)],
        models.AnalyticsPeriodType.MONTHLY,
        period_start,
        period_end
    )
    assert count == 1
    # Confirm cache exists
    cache = AnalyticsService.get_advanced_analytics_cache(
        test_db,
        models.AnalyticsDimensionType.KINDERGARTEN,
        str(kg.id),
        models.AnalyticsPeriodType.MONTHLY,
        period_start,
        period_end
    )
    assert cache is not None
    # Clean up
    test_db.delete(cache)
    test_db.delete(kg)
    test_db.commit()
