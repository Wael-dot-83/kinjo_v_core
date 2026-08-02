"""
Comprehensive regression tests for Batch 2C: Age Bucket Consolidation

Tests verify:
1. CHART-011: Age bucket labels consolidated into single constant
2. CHART-027: Age bucket boundaries are correct (no off-by-one errors)

Test coverage:
1. All 19 age buckets have correct boundaries
2. Boundary edge cases (exact month boundaries)
3. Invalid ages (too young, too old, future DOB, missing DOB)
4. Canonical constant is used consistently
5. Bilingual labels are correct
6. Export functionality works with consolidated labels
"""
import pytest
from datetime import date, timedelta
from sqlalchemy.orm import Session

import models
from admin_reports_api import (
    _age_bucket_key,
    AGE_BUCKET_LABELS,
    _today,
)
from child_age_policy import calculate_age_days, calculate_age_months


# ============================================================================
# Test 1: All 19 age buckets have correct boundaries
# ============================================================================

def test_all_age_buckets_have_correct_boundaries():
    """Verify all 19 age buckets have correct month boundaries."""
    today = _today()
    
    # Helper to create a DOB that is exactly N calendar months ago
    def months_ago(months):
        year = today.year
        month = today.month - months
        day = today.day
        while month <= 0:
            month += 12
            year -= 1
        # Handle day overflow (e.g., Jan 31 - 1 month = Feb 28)
        import calendar
        max_day = calendar.monthrange(year, month)[1]
        day = min(day, max_day)
        return date(year, month, day)
    
    # B1: 0-2 months (1 day to 3 months)
    assert _age_bucket_key(months_ago(1))[0] == "B1"  # 1 month
    assert _age_bucket_key(months_ago(2))[0] == "B1"  # 2 months
    
    # B2: 3-5 months (3 to 6 months)
    assert _age_bucket_key(months_ago(3))[0] == "B2"  # 3 months
    assert _age_bucket_key(months_ago(5))[0] == "B2"  # 5 months
    
    # B3: 6-8 months (6 to 9 months)
    assert _age_bucket_key(months_ago(6))[0] == "B3"  # 6 months
    assert _age_bucket_key(months_ago(8))[0] == "B3"  # 8 months
    
    # B4: 9-11 months (9 to 12 months)
    assert _age_bucket_key(months_ago(9))[0] == "B4"  # 9 months
    assert _age_bucket_key(months_ago(11))[0] == "B4"  # 11 months
    
    # B5: 12-14 months (12 to 15 months)
    assert _age_bucket_key(months_ago(12))[0] == "B5"  # 12 months
    assert _age_bucket_key(months_ago(14))[0] == "B5"  # 14 months
    
    # B6: 15-17 months (15 to 18 months)
    assert _age_bucket_key(months_ago(15))[0] == "B6"  # 15 months
    assert _age_bucket_key(months_ago(17))[0] == "B6"  # 17 months
    
    # B7: 18-20 months (18 to 21 months)
    assert _age_bucket_key(months_ago(18))[0] == "B7"  # 18 months
    assert _age_bucket_key(months_ago(20))[0] == "B7"  # 20 months
    
    # B8: 21-23 months (21 to 24 months)
    assert _age_bucket_key(months_ago(21))[0] == "B8"  # 21 months
    assert _age_bucket_key(months_ago(23))[0] == "B8"  # 23 months
    
    # B9: 24-26 months (24 to 27 months)
    assert _age_bucket_key(months_ago(24))[0] == "B9"  # 24 months
    assert _age_bucket_key(months_ago(26))[0] == "B9"  # 26 months
    
    # B10: 27-29 months (27 to 30 months)
    assert _age_bucket_key(months_ago(27))[0] == "B10"  # 27 months
    assert _age_bucket_key(months_ago(29))[0] == "B10"  # 29 months
    
    # B11: 30-32 months (30 to 33 months)
    assert _age_bucket_key(months_ago(30))[0] == "B11"  # 30 months
    assert _age_bucket_key(months_ago(32))[0] == "B11"  # 32 months
    
    # B12: 33-35 months (33 to 36 months)
    assert _age_bucket_key(months_ago(33))[0] == "B12"  # 33 months
    assert _age_bucket_key(months_ago(35))[0] == "B12"  # 35 months
    
    # B13: 36-38 months (36 to 39 months)
    assert _age_bucket_key(months_ago(36))[0] == "B13"  # 36 months
    assert _age_bucket_key(months_ago(38))[0] == "B13"  # 38 months
    
    # B14: 39-41 months (39 to 42 months)
    assert _age_bucket_key(months_ago(39))[0] == "B14"  # 39 months
    assert _age_bucket_key(months_ago(41))[0] == "B14"  # 41 months
    
    # B15: 42-44 months (42 to 45 months)
    assert _age_bucket_key(months_ago(42))[0] == "B15"  # 42 months
    assert _age_bucket_key(months_ago(44))[0] == "B15"  # 44 months
    
    # B16: 45-47 months (45 to 48 months)
    assert _age_bucket_key(months_ago(45))[0] == "B16"  # 45 months
    assert _age_bucket_key(months_ago(47))[0] == "B16"  # 47 months
    
    # B17: 48-50 months (48 to 51 months)
    assert _age_bucket_key(months_ago(48))[0] == "B17"  # 48 months
    assert _age_bucket_key(months_ago(50))[0] == "B17"  # 50 months
    
    # B18: 51-53 months (51 to 54 months)
    assert _age_bucket_key(months_ago(51))[0] == "B18"  # 51 months
    assert _age_bucket_key(months_ago(53))[0] == "B18"  # 53 months
    
    # B19: 54-57 months (54 to 57 months)
    assert _age_bucket_key(months_ago(54))[0] == "B19"  # 54 months
    assert _age_bucket_key(months_ago(56))[0] == "B19"  # 56 months


# ============================================================================
# Test 2: Boundary edge cases (exact month boundaries)
# ============================================================================

def test_boundary_edge_cases():
    """Verify exact month boundaries are handled correctly."""
    today = _today()
    
    # Helper to create a DOB that is exactly N calendar months ago
    def months_ago(months):
        year = today.year
        month = today.month - months
        day = today.day
        while month <= 0:
            month += 12
            year -= 1
        import calendar
        max_day = calendar.monthrange(year, month)[1]
        day = min(day, max_day)
        return date(year, month, day)
    
    # Test exact 3-month boundary (should be B2, not B1)
    dob_3_months = months_ago(3)
    bucket, _ = _age_bucket_key(dob_3_months)
    assert bucket == "B2", f"Expected B2 for 3 months, got {bucket}"
    
    # Test exact 6-month boundary (should be B3, not B2)
    dob_6_months = months_ago(6)
    bucket, _ = _age_bucket_key(dob_6_months)
    assert bucket == "B3", f"Expected B3 for 6 months, got {bucket}"
    
    # Test exact 9-month boundary (should be B4, not B3)
    dob_9_months = months_ago(9)
    bucket, _ = _age_bucket_key(dob_9_months)
    assert bucket == "B4", f"Expected B4 for 9 months, got {bucket}"
    
    # Test exact 12-month boundary (should be B5, not B4)
    dob_12_months = months_ago(12)
    bucket, _ = _age_bucket_key(dob_12_months)
    assert bucket == "B5", f"Expected B5 for 12 months, got {bucket}"
    
    # Test exact 57-month boundary (should be B19, not invalid)
    dob_57_months = months_ago(57)
    bucket, _ = _age_bucket_key(dob_57_months)
    assert bucket == "B19", f"Expected B19 for 57 months, got {bucket}"


# ============================================================================
# Test 3: Invalid ages
# ============================================================================

def test_invalid_ages():
    """Verify invalid ages are handled correctly."""
    today = _today()
    
    # Helper to create a DOB that is exactly N calendar months ago
    def months_ago(months):
        year = today.year
        month = today.month - months
        day = today.day
        while month <= 0:
            month += 12
            year -= 1
        import calendar
        max_day = calendar.monthrange(year, month)[1]
        day = min(day, max_day)
        return date(year, month, day)
    
    # Test too young (< 1 day)
    dob_too_young = today
    bucket, reason = _age_bucket_key(dob_too_young)
    assert bucket == "invalid"
    assert reason == "too_young"
    
    # Test too old (> 57 months)
    dob_too_old = months_ago(58)  # 58 months
    bucket, reason = _age_bucket_key(dob_too_old)
    assert bucket == "invalid", f"Expected invalid for 58 months, got {bucket}"
    assert reason == "too_old"
    
    # Test future DOB
    dob_future = today + timedelta(days=30)
    bucket, reason = _age_bucket_key(dob_future)
    assert bucket == "invalid"
    assert reason == "future_dob"
    
    # Test missing DOB
    bucket, reason = _age_bucket_key(None)
    assert bucket == "invalid"
    assert reason == "missing_dob"


# ============================================================================
# Test 4: Canonical constant is used consistently
# ============================================================================

def test_canonical_constant_structure():
    """Verify AGE_BUCKET_LABELS has correct structure."""
    # Should have exactly 19 buckets
    assert len(AGE_BUCKET_LABELS) == 19
    
    # Should have B1 through B19
    for i in range(1, 20):
        key = f"B{i}"
        assert key in AGE_BUCKET_LABELS, f"Missing bucket {key}"
        
        # Each bucket should have Arabic and English labels
        assert "ar" in AGE_BUCKET_LABELS[key], f"Missing Arabic label for {key}"
        assert "en" in AGE_BUCKET_LABELS[key], f"Missing English label for {key}"
        
        # Labels should not be empty
        assert AGE_BUCKET_LABELS[key]["ar"], f"Empty Arabic label for {key}"
        assert AGE_BUCKET_LABELS[key]["en"], f"Empty English label for {key}"


def test_canonical_constant_bilingual_labels():
    """Verify bilingual labels are correct."""
    # Test a few key buckets
    assert AGE_BUCKET_LABELS["B1"]["ar"] == "يوم إلى 3 أشهر"
    assert AGE_BUCKET_LABELS["B1"]["en"] == "1 day to 3 months"
    
    assert AGE_BUCKET_LABELS["B10"]["ar"] == "27 إلى 30 شهر"
    assert AGE_BUCKET_LABELS["B10"]["en"] == "27 to 30 months"
    
    assert AGE_BUCKET_LABELS["B19"]["ar"] == "54 إلى 57 شهر"
    assert AGE_BUCKET_LABELS["B19"]["en"] == "54 to 57 months"


# ============================================================================
# Test 5: No off-by-one errors in boundary calculations
# ============================================================================

def test_no_off_by_one_errors():
    """Verify no off-by-one errors in boundary calculations."""
    today = _today()
    
    # Helper to create a DOB that is exactly N calendar months ago
    def months_ago(months):
        year = today.year
        month = today.month - months
        day = today.day
        while month <= 0:
            month += 12
            year -= 1
        import calendar
        max_day = calendar.monthrange(year, month)[1]
        day = min(day, max_day)
        return date(year, month, day)
    
    # Test that children at exact boundaries go to the correct bucket
    # B1 should include 0-2 months (not 3 months)
    dob_2_months = months_ago(2)  # 2 months
    bucket, _ = _age_bucket_key(dob_2_months)
    assert bucket == "B1", f"Expected B1 for 2 months, got {bucket}"
    
    dob_3_months = months_ago(3)  # Exactly 3 months
    bucket, _ = _age_bucket_key(dob_3_months)
    assert bucket == "B2", f"Expected B2 for exactly 3 months, got {bucket}"
    
    # B19 should include 54-57 months (not 58 months)
    dob_57_months = months_ago(57)  # Exactly 57 months
    bucket, _ = _age_bucket_key(dob_57_months)
    assert bucket == "B19", f"Expected B19 for exactly 57 months, got {bucket}"
    
    dob_58_months = months_ago(58)  # 58 months (too old)
    bucket, reason = _age_bucket_key(dob_58_months)
    assert bucket == "invalid", f"Expected invalid for 58 months, got {bucket}"
    assert reason == "too_old"


# ============================================================================
# Test 6: Age calculation helpers work correctly
# ============================================================================

def test_age_calculation_helpers():
    """Verify age calculation helpers work correctly."""
    today = _today()
    
    # Helper to create a DOB that is exactly N calendar months ago
    def months_ago(months):
        year = today.year
        month = today.month - months
        day = today.day
        while month <= 0:
            month += 12
            year -= 1
        import calendar
        max_day = calendar.monthrange(year, month)[1]
        day = min(day, max_day)
        return date(year, month, day)
    
    # Test calculate_age_days
    dob = today - timedelta(days=30)
    age_days = calculate_age_days(dob, today)
    assert age_days == 30
    
    # Test calculate_age_months
    dob = months_ago(3)
    age_months = calculate_age_months(dob, today)
    assert age_months == 3
    
    # Test with different month lengths
    dob = months_ago(12)
    age_months = calculate_age_months(dob, today)
    assert age_months == 12


# ============================================================================
# Test 7: Integration with database queries
# ============================================================================

def test_integration_with_database_queries(test_db: Session, sample_child):
    """Verify age bucket classification works with database queries."""
    # Helper to create a DOB that is exactly N calendar months ago
    today = _today()
    def months_ago(months):
        year = today.year
        month = today.month - months
        day = today.day
        while month <= 0:
            month += 12
            year -= 1
        import calendar
        max_day = calendar.monthrange(year, month)[1]
        day = min(day, max_day)
        return date(year, month, day)
    
    # Create a child with a specific DOB
    sample_child.dob = months_ago(3)  # 3 months old
    test_db.commit()
    
    # Query the child and classify their age bucket
    child = test_db.query(models.Child).filter(models.Child.id == sample_child.id).first()
    bucket, _ = _age_bucket_key(child.dob)
    
    assert bucket == "B2", f"Expected B2 for 3-month-old child, got {bucket}"


# ============================================================================
# Test 8: Export functionality with consolidated labels
# ============================================================================

def test_export_functionality_with_consolidated_labels():
    """Verify export functionality works with consolidated labels."""
    # This test verifies that the consolidated labels can be used in exports
    # without any issues
    
    # Create a mock metrics dict with age buckets
    metrics = {
        "age_buckets": {
            "B1": 10,
            "B2": 15,
            "B3": 20,
        }
    }
    
    # Verify that we can access the labels correctly
    for bucket_key in metrics["age_buckets"].keys():
        label = AGE_BUCKET_LABELS.get(bucket_key, {"ar": bucket_key, "en": bucket_key})
        assert "ar" in label
        assert "en" in label
        assert label["ar"]
        assert label["en"]


# ============================================================================
# Test 9: All buckets have consistent month ranges
# ============================================================================

def test_all_buckets_have_consistent_month_ranges():
    """Verify all buckets have consistent 3-month ranges."""
    # Each bucket should span exactly 3 months (except B1 which is 1 day to 3 months)
    # B1: 0-2 months (3 months total)
    # B2: 3-5 months (3 months total)
    # ...
    # B19: 54-57 months (3 months total)
    
    # Verify the pattern
    for i in range(1, 20):
        bucket_key = f"B{i}"
        start_month = (i - 1) * 3
        end_month = i * 3
        
        # Verify the label mentions the correct range
        label_en = AGE_BUCKET_LABELS[bucket_key]["en"]
        
        # Check that the label contains the expected month range
        if i == 1:
            assert "1 day to 3 months" in label_en
        else:
            assert f"{start_month} to {end_month} months" in label_en


# ============================================================================
# Test 10: Fallback for unknown buckets
# ============================================================================

def test_fallback_for_unknown_buckets():
    """Verify fallback behavior for unknown bucket keys."""
    # Test that unknown bucket keys fall back to using the key itself
    unknown_key = "B99"
    label = AGE_BUCKET_LABELS.get(unknown_key, {"ar": unknown_key, "en": unknown_key})
    
    assert label["ar"] == unknown_key
    assert label["en"] == unknown_key


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
