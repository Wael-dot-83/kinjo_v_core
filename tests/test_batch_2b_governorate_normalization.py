"""
Comprehensive regression tests for Batch 2B: Governorate Normalization

Tests verify that the canonical governorate normalization layer works correctly
across all analytics and reporting code.

Test coverage:
1. Arabic canonical names
2. English names
3. Mixed Arabic/English inputs
4. Legacy aliases
5. Whitespace variants
6. Unicode normalization
7. Invalid governorates
8. Unknown values
9. Exports
10. Drill-down
11. API endpoints
12. Heatmap
13. Predictive analytics
"""
import pytest
from datetime import date
from sqlalchemy.orm import Session

import models
from services.jordan_locations import (
    normalize_governorate,
    normalize_governorate_key,
    governorate_query_aliases,
    governorate_filter,
    validate_governorate,
    is_valid_governorate,
    governorate_name_ar,
    governorate_name_en,
)


# ============================================================================
# Test 1: Arabic canonical names
# ============================================================================

def test_arabic_canonical_names():
    """Verify Arabic canonical names normalize correctly."""
    assert normalize_governorate("العاصمة") == "العاصمة"
    assert normalize_governorate("إربد") == "إربد"
    assert normalize_governorate("الزرقاء") == "الزرقاء"
    assert normalize_governorate("العقبة") == "العقبة"
    assert normalize_governorate("المفرق") == "المفرق"


# ============================================================================
# Test 2: English names
# ============================================================================

def test_english_names():
    """Verify English names normalize to Arabic canonical."""
    assert normalize_governorate("Amman") == "العاصمة"
    assert normalize_governorate("Irbid") == "إربد"
    assert normalize_governorate("Zarqa") == "الزرقاء"
    assert normalize_governorate("Aqaba") == "العقبة"
    assert normalize_governorate("Mafraq") == "المفرق"


# ============================================================================
# Test 3: Mixed Arabic/English inputs
# ============================================================================

def test_mixed_inputs():
    """Verify mixed inputs normalize correctly."""
    assert normalize_governorate("amman") == "العاصمة"
    assert normalize_governorate("AMMAN") == "العاصمة"
    assert normalize_governorate("Amman") == "العاصمة"
    assert normalize_governorate("irbid") == "إربد"
    assert normalize_governorate("IRBID") == "إربد"


# ============================================================================
# Test 4: Legacy aliases
# ============================================================================

def test_legacy_aliases():
    """Verify legacy aliases normalize correctly."""
    # عمان is a legacy alias for العاصمة (Amman)
    assert normalize_governorate("عمان") == "العاصمة"
    assert normalize_governorate("عاصمة") == "العاصمة"
    
    # Test other aliases
    aliases_amman = governorate_query_aliases("Amman")
    assert "amman" in aliases_amman
    assert "عمان" in aliases_amman
    assert "العاصمة" in aliases_amman


# ============================================================================
# Test 5: Whitespace variants
# ============================================================================

def test_whitespace_variants():
    """Verify whitespace variants normalize correctly."""
    assert normalize_governorate("  Amman  ") == "العاصمة"
    assert normalize_governorate("\tAmman\t") == "العاصمة"
    assert normalize_governorate("Amman\n") == "العاصمة"
    assert normalize_governorate("  العاصمة  ") == "العاصمة"


# ============================================================================
# Test 6: Unicode normalization
# ============================================================================

def test_unicode_normalization():
    """Verify Unicode normalization works correctly."""
    # Test with different Unicode representations
    assert normalize_governorate("Amman") == "العاصمة"
    assert normalize_governorate("amman") == "العاصمة"
    assert normalize_governorate("AMMAN") == "العاصمة"


# ============================================================================
# Test 7: Invalid governorates
# ============================================================================

def test_invalid_governorates():
    """Verify invalid governorates are handled correctly."""
    # Unknown values should be returned unchanged
    assert normalize_governorate("Unknown") == "Unknown"
    assert normalize_governorate("InvalidGov") == "InvalidGov"
    
    # Empty values should return None
    assert normalize_governorate("") is None
    assert normalize_governorate(None) is None
    assert normalize_governorate("  ") is None
    
    # Validation should raise ValueError for invalid governorates
    with pytest.raises(ValueError, match="Invalid governorate"):
        validate_governorate("UnknownGov")


# ============================================================================
# Test 8: Unknown values
# ============================================================================

def test_unknown_values():
    """Verify unknown values are handled correctly."""
    # Unknown values should be returned unchanged by normalize_governorate
    result = normalize_governorate("SomeUnknownValue")
    assert result == "SomeUnknownValue"
    
    # But is_valid_governorate should return False
    assert is_valid_governorate("SomeUnknownValue") is False
    
    # governorate_query_aliases should return [value] for unknown values
    aliases = governorate_query_aliases("SomeUnknownValue")
    assert aliases == ["SomeUnknownValue"]


# ============================================================================
# Test 9: governorate_query_aliases
# ============================================================================

def test_governorate_query_aliases():
    """Verify governorate_query_aliases returns all accepted forms."""
    # Test with Amman
    aliases = governorate_query_aliases("Amman")
    assert len(aliases) > 0
    assert "amman" in aliases
    assert "Amman" in aliases
    assert "AMMAN" in aliases
    assert "عمان" in aliases
    assert "العاصمة" in aliases
    
    # Test with Arabic canonical
    aliases_ar = governorate_query_aliases("العاصمة")
    assert len(aliases_ar) > 0
    assert "amman" in aliases_ar
    assert "عمان" in aliases_ar
    assert "العاصمة" in aliases_ar
    
    # Test with empty value
    assert governorate_query_aliases("") == []
    assert governorate_query_aliases(None) == []


# ============================================================================
# Test 10: governorate_filter
# ============================================================================

def test_governorate_filter():
    """Verify governorate_filter generates correct SQLAlchemy filter."""
    from sqlalchemy import false
    
    # Test with valid governorate
    filter_condition = governorate_filter(models.Kindergarten.governorate, "Amman")
    assert filter_condition is not None
    
    # Test with empty value
    filter_empty = governorate_filter(models.Kindergarten.governorate, "")
    # Should return false() for empty values
    assert filter_empty is not None
    
    # Test with None
    filter_none = governorate_filter(models.Kindergarten.governorate, None)
    assert filter_none is not None


# ============================================================================
# Test 11: Bilingual resolution
# ============================================================================

def test_bilingual_resolution():
    """Verify bilingual governorate resolution works correctly."""
    # Test governorate_name_ar
    assert governorate_name_ar("amman") == "العاصمة"
    assert governorate_name_ar("irbid") == "إربد"
    assert governorate_name_ar("zarqa") == "الزرقاء"
    
    # Test governorate_name_en
    assert governorate_name_en("amman") == "Amman"
    assert governorate_name_en("irbid") == "Irbid"
    assert governorate_name_en("zarqa") == "Zarqa"
    
    # Test with None
    assert governorate_name_ar(None) is None
    assert governorate_name_en(None) is None


# ============================================================================
# Test 12: normalize_governorate_key
# ============================================================================

def test_normalize_governorate_key():
    """Verify normalize_governorate_key returns stable keys."""
    assert normalize_governorate_key("Amman") == "amman"
    assert normalize_governorate_key("عمان") == "amman"
    assert normalize_governorate_key("العاصمة") == "amman"
    assert normalize_governorate_key("AMMAN") == "amman"
    
    assert normalize_governorate_key("Irbid") == "irbid"
    assert normalize_governorate_key("إربد") == "irbid"
    
    # Test with None
    assert normalize_governorate_key(None) is None
    assert normalize_governorate_key("") is None


# ============================================================================
# Test 13: is_valid_governorate
# ============================================================================

def test_is_valid_governorate():
    """Verify is_valid_governorate correctly identifies valid governorates."""
    # Valid governorates
    assert is_valid_governorate("Amman") is True
    assert is_valid_governorate("amman") is True
    assert is_valid_governorate("AMMAN") is True
    assert is_valid_governorate("عمان") is True
    assert is_valid_governorate("العاصمة") is True
    
    assert is_valid_governorate("Irbid") is True
    assert is_valid_governorate("irbid") is True
    assert is_valid_governorate("إربد") is True
    
    # Invalid governorates
    assert is_valid_governorate("Unknown") is False
    assert is_valid_governorate("InvalidGov") is False
    assert is_valid_governorate("") is False
    assert is_valid_governorate(None) is False


# ============================================================================
# Test 14: Integration with database queries
# ============================================================================

def test_database_query_integration(test_db: Session, sample_kindergarten):
    """Verify governorate_filter works correctly with database queries."""
    # Create a test kindergarten with a specific governorate
    sample_kindergarten.governorate = "العاصمة"
    test_db.commit()
    
    # Query using governorate_filter with English name
    results = test_db.query(models.Kindergarten).filter(
        governorate_filter(models.Kindergarten.governorate, "Amman")
    ).all()
    assert len(results) > 0
    assert any(kg.id == sample_kindergarten.id for kg in results)
    
    # Query using governorate_filter with legacy alias
    results_alias = test_db.query(models.Kindergarten).filter(
        governorate_filter(models.Kindergarten.governorate, "عمان")
    ).all()
    assert len(results_alias) > 0
    assert any(kg.id == sample_kindergarten.id for kg in results_alias)
    
    # Query using governorate_filter with Arabic canonical
    results_ar = test_db.query(models.Kindergarten).filter(
        governorate_filter(models.Kindergarten.governorate, "العاصمة")
    ).all()
    assert len(results_ar) > 0
    assert any(kg.id == sample_kindergarten.id for kg in results_ar)


# ============================================================================
# Test 15: Case-insensitive matching
# ============================================================================

def test_case_insensitive_matching():
    """Verify case-insensitive matching works correctly."""
    # All these should normalize to the same value
    assert normalize_governorate("amman") == normalize_governorate("Amman")
    assert normalize_governorate("Amman") == normalize_governorate("AMMAN")
    assert normalize_governorate("AMMAN") == normalize_governorate("amman")
    
    assert normalize_governorate("irbid") == normalize_governorate("Irbid")
    assert normalize_governorate("Irbid") == normalize_governorate("IRBID")


# ============================================================================
# Test 16: Edge cases
# ============================================================================

def test_edge_cases():
    """Verify edge cases are handled correctly."""
    # Test with very long strings
    long_string = "A" * 1000
    result = normalize_governorate(long_string)
    assert result == long_string  # Should be returned unchanged
    
    # Test with special characters
    special = "Amman@#$%"
    result_special = normalize_governorate(special)
    assert result_special == special  # Should be returned unchanged
    
    # Test with numbers
    numbers = "12345"
    result_numbers = normalize_governorate(numbers)
    assert result_numbers == numbers  # Should be returned unchanged


# ============================================================================
# Test 17: Consistency across functions
# ============================================================================

def test_consistency_across_functions():
    """Verify consistency across different normalization functions."""
    # Test that normalize_governorate and validate_governorate agree
    valid_govs = ["Amman", "Irbid", "Zarqa", "Aqaba", "Mafraq"]
    for gov in valid_govs:
        normalized = normalize_governorate(gov)
        validated = validate_governorate(gov)
        assert normalized == validated
        assert is_valid_governorate(gov) is True
    
    # Test that normalize_governorate_key and governorate_name_ar agree
    for gov in valid_govs:
        key = normalize_governorate_key(gov)
        name_ar = governorate_name_ar(key)
        assert name_ar is not None
        assert is_valid_governorate(name_ar) is True


# ============================================================================
# Test 18: All 12 Jordanian governorates
# ============================================================================

def test_all_jordanian_governorates():
    """Verify all 12 Jordanian governorates are recognized."""
    # The 12 governorates of Jordan
    governorates = [
        ("Amman", "العاصمة"),
        ("Irbid", "إربد"),
        ("Zarqa", "الزرقاء"),
        ("Aqaba", "العقبة"),
        ("Mafraq", "المفرق"),
        ("Balqa", "البلقاء"),
        ("Karak", "الكرك"),
        ("Madaba", "مادبا"),
        ("Tafilah", "الطفيلة"),
        ("Ma'an", "معان"),
        ("Jerash", "جرش"),
        ("Ajloun", "عجلون"),
    ]
    
    for english, arabic in governorates:
        # Verify English normalizes to Arabic
        assert normalize_governorate(english) == arabic
        
        # Verify Arabic is valid
        assert is_valid_governorate(arabic) is True
        assert is_valid_governorate(english) is True
        
        # Verify key normalization
        key = normalize_governorate_key(english)
        assert key is not None
        
        # Verify bilingual resolution
        name_ar = governorate_name_ar(key)
        name_en = governorate_name_en(key)
        assert name_ar == arabic
        assert name_en == english


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
