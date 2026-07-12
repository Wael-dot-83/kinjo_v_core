"""Tests for the canonical metric registry (analytics/metric_registry.py)."""
import pytest

from analytics import metric_registry as mr


@pytest.fixture(autouse=True)
def _loaded():
    mr.load_registry(force=True)


def test_registry_has_all_33_metrics():
    assert len(mr.list_metrics()) == 33


def test_layer_counts_match_six_layer_design():
    counts = {
        layer: len(mr.list_metrics(layer=layer))
        for layer in ("network", "geographic", "kindergarten", "child", "predictive", "governance")
    }
    assert counts == {
        "network": 7, "geographic": 7, "kindergarten": 8,
        "child": 5, "predictive": 4, "governance": 2,
    }


def test_validate_registry_is_clean():
    problems = mr.validate_registry()
    assert problems == [], f"registry validation problems: {problems}"


def test_every_metric_has_required_fields_and_bilingual_titles():
    for key in mr.list_metrics():
        d = mr.get_metric(key)
        for field in mr.REQUIRED_FIELDS:
            assert d.get(field), f"{key} missing {field}"
        assert d["title_en"] and d["title_ar"], f"{key} missing bilingual title"


def test_kpi_standard_links_resolve_when_present():
    import kpi_standards
    for key in mr.list_metrics():
        d = mr.get_metric(key)
        kpi_key = d.get("kpi_standard_key")
        if kpi_key:
            assert kpi_key in kpi_standards.STANDARDS, f"{key} -> unknown kpi '{kpi_key}'"
            # enrichment is attached on get_metric
            assert "kpi_standard" in d


def test_area_is_surfaced_as_city():
    assert mr.dimension_label("AREA", "en") == "City"
    assert mr.dimension_label("AREA", "ar") == "المدينة"
    # the 7 geographic metrics are queryable at the AREA(City) dimension
    assert len(mr.list_metrics(dimension="AREA")) == 7


def test_exactly_five_restricted_child_metrics():
    restricted = mr.list_metrics(privacy_level="restricted")
    assert len(restricted) == 5
    assert all(mr.get_metric(k)["layer"] == "child" for k in restricted)


def test_drilldown_path_is_country_to_child_via_city():
    assert mr.DRILLDOWN_PATH == [
        "NETWORK", "GOVERNORATE", "AREA", "KINDERGARTEN", "CLASS", "CHILD"
    ]


def test_unknown_metric_raises_keyerror():
    with pytest.raises(KeyError):
        mr.get_metric("does_not_exist")
