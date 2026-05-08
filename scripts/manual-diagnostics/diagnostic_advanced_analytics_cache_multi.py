"""
Test advanced analytics cache for multiple dimension types and periods
"""
import pytest
from datetime import date, timedelta
import models
from analytics_service import AnalyticsService

@pytest.mark.parametrize("dimension_type,dimension_id", [
    (models.AnalyticsDimensionType.KINDERGARTEN, "1"),
    (models.AnalyticsDimensionType.GOVERNORATE, "TestGov"),
    (models.AnalyticsDimensionType.NETWORK, "NETWORK"),
])
def test_advanced_analytics_cache_multi_dim(test_db, dimension_type, dimension_id):
    # Create minimal kindergarten for KINDERGARTEN type
    if dimension_type == models.AnalyticsDimensionType.KINDERGARTEN:
        kg = models.Kindergarten(
            name_ar="KG Multi",
            name_en="KG Multi",
            governorate="TestGov",
            city="TestCity",
            area="TestArea",
            address_line="Test Address",
            contact_phone="1234567890",
            status=models.KindergartenStatus.ACTIVE
        )
        test_db.add(kg)
        test_db.commit()
        dimension_id = str(kg.id)
    period_start = date.today() - timedelta(days=60)
    period_end = date.today() - timedelta(days=30)
    period_type = models.AnalyticsPeriodType.MONTHLY
    # Compute and store
    cache = AnalyticsService.compute_advanced_analytics(
        test_db,
        dimension_type,
        dimension_id,
        period_type,
        period_start,
        period_end
    )
    assert cache is not None
    assert cache.dimension_type == dimension_type
    assert cache.dimension_id == dimension_id
    # Retrieve
    retrieved = AnalyticsService.get_advanced_analytics_cache(
        test_db,
        dimension_type,
        dimension_id,
        period_type,
        period_start,
        period_end
    )
    assert retrieved is not None
    assert retrieved.id == cache.id
    # Clean up
    test_db.delete(retrieved)
    if dimension_type == models.AnalyticsDimensionType.KINDERGARTEN:
        test_db.delete(kg)
    test_db.commit()
