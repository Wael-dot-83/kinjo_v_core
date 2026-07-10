from agency_reports_registry import (
    AGENCY_REPORT_REGISTRY,
    AGENCY_LOGOS,
    OFFICIAL_AGENCY_CODES,
    SENSITIVE_FIELD_DENYLIST,
)

REQUIRED_OFFICIAL = {"mosd", "moe", "moh", "mol", "ssc", "dos", "ncfa"}


def test_official_agency_registry_contains_required_codes():
    # The seven official reporting agencies must all be present.
    assert REQUIRED_OFFICIAL.issubset(set(AGENCY_REPORT_REGISTRY)), (
        "Missing official agency codes: " + str(REQUIRED_OFFICIAL - set(AGENCY_REPORT_REGISTRY))
    )


def test_mopic_retained_but_not_official():
    # mopic (Ministry of Planning) is kept for an existing ready report but is
    # intentionally NOT part of the official public scope.
    assert "mopic" in AGENCY_REPORT_REGISTRY
    assert AGENCY_REPORT_REGISTRY["mopic"].get("is_official") is False


def test_all_official_agencies_flagged_is_official():
    for code in REQUIRED_OFFICIAL:
        assert AGENCY_REPORT_REGISTRY[code].get("is_official") is True


def test_moe_arabic_name_is_canonical():
    assert AGENCY_REPORT_REGISTRY["moe"]["name_ar"] == "وزارة التربية والتعليم"


def test_ssc_arabic_name_is_canonical():
    assert AGENCY_REPORT_REGISTRY["ssc"]["name_ar"] == "المؤسسة العامة للضمان الاجتماعي"


def test_registry_reports_are_aggregated_only():
    for agency in AGENCY_REPORT_REGISTRY.values():
        for report in agency["reports"].values():
            assert report.get("privacy_level") == "aggregated_only"


def test_sensitive_export_denylist_blocks_personal_fields():
    for field in ("national_id", "phone_number", "message_body", "description"):
        assert field in SENSITIVE_FIELD_DENYLIST