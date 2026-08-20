"""ADMIN-SCORING-001/002/003 — the report endpoints actually use the new scoring.

The unit tests in this directory prove the formulas are right. These prove the
formulas are *reached*: a correct scoring module that nothing calls is still a
broken report.
"""

import inspect

import pytest

import admin_reports_api
from conftest import bearer_headers

BASE = "/api/admin/reports"


@pytest.fixture
def seeded(test_db, parent_user, sample_kindergarten, sample_class):
    """A kindergarten with a class holding children and no supervisor.

    That is a CRITICAL violation under ADMIN-SCORING-001, so the compliance
    score must move off 100 by a weighted amount rather than by a fraction
    diluted across every entity in the network.
    """
    from datetime import date, timedelta

    import models

    children = []
    for i in range(3):
        child = models.Child(
            parent_id=parent_user.parent_profile.id,
            first_name=f"Child{i}",
            last_name="Test",
            date_of_birth=date.today() - timedelta(days=365 * 3),
            gender=models.Gender.MALE,
            father_name="Ahmad Al-Rashid",
            mother_first_name="Fatima",
            mother_last_name="Hassan",
            mother_nationality="Jordanian",
            mother_national_id=f"098765432{i}",
        )
        test_db.add(child)
        test_db.flush()
        test_db.add(models.EnrollmentApplication(
            child_id=child.id,
            kindergarten_id=sample_kindergarten.id,
            class_id=sample_class.id,
            status=models.EnrollmentStatus.ACTIVE,
        ))
        children.append(child)
    test_db.commit()
    return {"kindergarten": sample_kindergarten, "class": sample_class, "children": children}


class TestSourceOfTruth:
    """The endpoints must not re-derive what the scoring module owns."""

    def test_the_broken_entity_base_formula_is_gone(self):
        source = inspect.getsource(admin_reports_api)

        assert "entity_base" not in source

    def test_endpoints_do_not_reimplement_the_status_bands(self):
        """Bands live in scoring.py; a copy in the router will drift from it."""
        source = inspect.getsource(admin_reports_api)

        assert 'if score >= 95:' not in source

    def test_core_metrics_calls_the_scoring_module(self):
        source = inspect.getsource(admin_reports_api._collect_core_metrics)

        assert "calculate_compliance_score(" in source
        assert "calculate_data_quality_score(" in source

    def test_risk_rows_uses_percentile_banding(self):
        source = inspect.getsource(admin_reports_api._risk_rows)

        assert "calculate_risk_score(" in source
        assert "rank_kindergartens_by_risk(" in source
        # The old absolute cut-offs must be gone.
        assert "score >= 60" not in source
        assert "score >= 35" not in source


class TestComplianceEndpoint:
    def test_returns_the_weighted_breakdown(self, client, admin_token, seeded):
        response = client.get(f"{BASE}/compliance", headers=bearer_headers(admin_token))

        assert response.status_code == 200, response.text
        body = response.json()
        assert "severity_breakdown" in body
        assert "weighted_violations" in body
        assert "total_deduction" in body

    def test_unsupervised_class_costs_twenty_five_points(self, client, admin_token, seeded):
        """The whole point of ADMIN-SCORING-001, end to end."""
        response = client.get(f"{BASE}/compliance", headers=bearer_headers(admin_token))
        body = response.json()

        breakdown = body["severity_breakdown"]
        assert "class_with_children_no_supervisor" in breakdown
        entry = breakdown["class_with_children_no_supervisor"]
        assert entry["severity"] == "CRITICAL"
        assert entry["severity_weight"] == 25
        assert entry["deduction"] == entry["count"] * 25

    def test_score_reflects_the_deduction_not_a_diluted_ratio(
        self, client, admin_token, seeded
    ):
        response = client.get(f"{BASE}/compliance", headers=bearer_headers(admin_token))
        body = response.json()

        assert body["compliance_score"] == pytest.approx(
            max(0.0, 100.0 - body["total_deduction"])
        )
        # The old formula would have returned something within a hair of 100.
        assert body["compliance_score"] <= 75.0

    def test_breakdown_is_bilingual(self, client, admin_token, seeded):
        response = client.get(f"{BASE}/compliance", headers=bearer_headers(admin_token))

        for entry in response.json()["severity_breakdown"].values():
            assert entry["description_ar"].strip()
            assert entry["description_en"].strip()
            assert entry["description_ar"] != entry["description_en"]


class TestDataQualityEndpoint:
    def test_returns_all_four_dimensions(self, client, admin_token, seeded):
        response = client.get(f"{BASE}/data-quality", headers=bearer_headers(admin_token))

        assert response.status_code == 200, response.text
        dimensions = response.json()["dimensions"]
        assert set(dimensions) == {
            "completeness", "timeliness", "validity", "uniqueness"
        }

    def test_dimension_weights_are_published(self, client, admin_token, seeded):
        response = client.get(f"{BASE}/data-quality", headers=bearer_headers(admin_token))
        dimensions = response.json()["dimensions"]

        assert dimensions["completeness"]["weight"] == 0.30
        assert dimensions["timeliness"]["weight"] == 0.20
        assert dimensions["validity"]["weight"] == 0.30
        assert dimensions["uniqueness"]["weight"] == 0.20

    def test_score_is_the_weighted_average_of_the_dimensions(
        self, client, admin_token, seeded
    ):
        response = client.get(f"{BASE}/data-quality", headers=bearer_headers(admin_token))
        body = response.json()

        expected = sum(
            d["score"] * d["weight"] for d in body["dimensions"].values()
        )
        assert body["data_quality_score"] == pytest.approx(expected, abs=0.01)

    def test_score_is_no_longer_just_the_filing_rate(
        self, client, admin_token, seeded
    ):
        """No daily report was filed, so timeliness is 0 -- but the score is not."""
        response = client.get(f"{BASE}/data-quality", headers=bearer_headers(admin_token))
        body = response.json()

        assert body["dimensions"]["timeliness"]["score"] == 0.0
        assert body["data_quality_score"] > 0.0

    def test_dimension_labels_are_bilingual(self, client, admin_token, seeded):
        response = client.get(f"{BASE}/data-quality", headers=bearer_headers(admin_token))

        for dimension in response.json()["dimensions"].values():
            assert dimension["label_ar"].strip()
            assert dimension["label_en"].strip()
            assert dimension["label_ar"] != dimension["label_en"]


class TestRiskRankingEndpoint:
    def test_rows_carry_percentile_and_population(self, client, admin_token, seeded):
        response = client.get(f"{BASE}/risk-ranking", headers=bearer_headers(admin_token))

        assert response.status_code == 200, response.text
        rows = response.json().get("rows") or response.json().get("ranking") or []
        for row in rows:
            assert "percentile_rank" in row
            assert "population_size" in row
            assert row["risk_status"] in {"critical", "warning", "elevated", "normal"}

    def test_rows_carry_bilingual_band_labels(self, client, admin_token, seeded):
        response = client.get(f"{BASE}/risk-ranking", headers=bearer_headers(admin_token))
        rows = response.json().get("rows") or response.json().get("ranking") or []

        for row in rows:
            assert row["risk_label_ar"].strip()
            assert row["risk_label_en"].strip()
