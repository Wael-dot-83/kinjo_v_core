from agency_reports_registry import AGENCY_REPORT_REGISTRY, SENSITIVE_FIELD_DENYLIST


def test_official_agency_registry_contains_required_agencies():
    assert set(AGENCY_REPORT_REGISTRY) == {"moe", "moh", "dos", "ncfa", "mol", "mosd", "mopic"}


def test_registry_reports_are_aggregated_only():
    for agency in AGENCY_REPORT_REGISTRY.values():
        for report in agency["reports"].values():
            assert report.get("privacy_level") == "aggregated_only"


def test_sensitive_export_denylist_blocks_personal_fields():
    assert "national_id" in SENSITIVE_FIELD_DENYLIST
    assert "phone_number" in SENSITIVE_FIELD_DENYLIST
    assert "message_body" in SENSITIVE_FIELD_DENYLIST
    assert "description" in SENSITIVE_FIELD_DENYLIST
