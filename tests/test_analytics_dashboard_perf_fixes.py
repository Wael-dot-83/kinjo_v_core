# -*- coding: utf-8 -*-
"""Regression tests for two confirmed analytics-dashboard bugs found during a
live investigation of /admin/analytics:

1. get_consolidated_dashboard_data computed a kindergarten's governance score
   via TWO different formulas (a duplicate "simplified GCEI" in
   analytics_service.py vs the canonical KPIService.compute_governance_score)
   across up to four call sites in a single request, causing ~35s cold-cache
   loads and letting different dashboard sections show materially different
   governance scores for the same kindergarten/period. Fixed by memoizing the
   canonical score per (kg, period) on the request's db session and removing
   the duplicate formula.

2. get_high_risk_children()'s dict shape ({child_name, kindergarten_name,
   risk_type, risk_value, description}) didn't match what the Risk
   Intelligence renderers expected ({name, kindergarten, reason, risk_score,
   kindergarten_id}), so every real risk entry was silently discarded and the
   UI always showed "no risk alerts" regardless of actual data. Fixed by
   aligning the renderers to the real schema and adding the missing
   kindergarten_id field to the backend response.
"""
from datetime import date, timedelta

import pytest

import models
from analytics_service import AnalyticsService
from auth import get_password_hash
from database import get_db
from fastapi.testclient import TestClient
from main import app


@pytest.fixture
def client(test_db):
    def override_get_db():
        try:
            yield test_db
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def admin_user(test_db):
    user = models.User(
        username="perfadmin",
        email="perfadmin@test.com",
        hashed_password=get_password_hash("Admin123!"),
        role=models.UserRole.ADMIN,
        status=models.UserStatus.ACTIVE,
    )
    test_db.add(user)
    test_db.commit()
    test_db.refresh(user)
    return user


@pytest.fixture
def kg_with_risk_data(test_db):
    """One kindergarten with a child whose attendance is low enough to be
    flagged by get_high_risk_children's low-attendance detector."""
    kg = models.Kindergarten(
        name_ar="حضانة الفحص",
        name_en="Inspection KG",
        governorate="عمان",
        district="عمان",
        area="القويسمة",
        address_line="شارع الفحص",
        contact_phone="0791234567",
        status=models.KindergartenStatus.ACTIVE,
    )
    test_db.add(kg)
    test_db.commit()

    cls = models.Class(
        kindergarten_id=kg.id,
        name_ar="الصف الأول",
        name_en="Class 1",
        class_code="C1",
        age_group="AGE_2_4",
        capacity_total=20,
        min_age_months=24,
        max_age_months=36,
    )
    test_db.add(cls)
    test_db.commit()

    parent = models.User(
        username="riskparent",
        email="riskparent@test.com",
        hashed_password=get_password_hash("Parent123!"),
        role=models.UserRole.PARENT,
        status=models.UserStatus.ACTIVE,
    )
    test_db.add(parent)
    test_db.commit()

    parent_profile = models.ParentProfile(
        user_id=parent.id,
        first_name="أحمد",
        last_name="محمد",
        phone_number="0791234567",
        gender=models.Gender.MALE,
        nationality="أردني",
        home_governorate="عمان",
        home_district="عمان",
        home_area="وسط البلد",
        home_address_line="شارع الملك فيصل",
    )
    test_db.add(parent_profile)
    test_db.commit()

    child = models.Child(
        parent_id=parent_profile.id,
        first_name="سارة",
        last_name="أحمد",
        date_of_birth=date.today() - timedelta(days=365 * 3),
        gender=models.Gender.FEMALE,
        father_name="أحمد محمد",
        mother_first_name="فاطمة",
        mother_last_name="علي",
        mother_nationality="أردني",
    )
    test_db.add(child)
    test_db.commit()

    enrollment = models.EnrollmentApplication(
        child_id=child.id,
        kindergarten_id=kg.id,
        class_id=cls.id,
        status=models.EnrollmentStatus.ACTIVE,
    )
    test_db.add(enrollment)
    test_db.commit()
    # No AttendanceLog rows at all -> 0% attendance over the trailing 30 days,
    # well under the < 80% threshold get_high_risk_children filters on.

    return {"kindergarten": kg, "child": child}


class TestGovernanceScoreConsistency:
    """Bug 1: governance score must be a single canonical value per (kg, period)."""

    def test_kindergarten_governance_helpers_agree(self, test_db, kg_with_risk_data):
        kg = kg_with_risk_data["kindergarten"]
        period_start = date.today() - timedelta(days=6)
        period_end = date.today()

        # The two internal call paths that used to diverge must now return
        # the exact same (score, band) — both delegate to the canonical
        # KPIService.compute_governance_score via _kg_governance_score_and_band.
        score_and_band = AnalyticsService._kg_governance_score_and_band(
            test_db, kg.id, period_start, period_end
        )
        score_only = AnalyticsService._compute_kindergarten_governance_score(
            test_db, kg.id, period_start, period_end
        )
        assert score_only == score_and_band[0]

    def test_governance_score_memoized_per_request_session(self, test_db, kg_with_risk_data):
        """Calling the helper twice for the same (kg, period) on the same db
        session must not recompute — this is what collapses the former
        3-4x-per-kindergarten redundant computation down to once."""
        kg = kg_with_risk_data["kindergarten"]
        period_start = date.today() - timedelta(days=6)
        period_end = date.today()

        first = AnalyticsService._kg_governance_score_and_band(
            test_db, kg.id, period_start, period_end
        )
        memo = test_db.info.get("_governance_score_memo", {})
        assert (kg.id, period_start, period_end) in memo

        second = AnalyticsService._kg_governance_score_and_band(
            test_db, kg.id, period_start, period_end
        )
        assert first == second

    def test_network_and_governorate_governance_use_canonical_scores(
        self, test_db, kg_with_risk_data
    ):
        """Regression guard: network-wide and governorate-level governance
        averages must be built from the same canonical per-KG score, not a
        second, disagreeing formula."""
        from kpi_service import KPIService

        kg = kg_with_risk_data["kindergarten"]
        period_start = date.today() - timedelta(days=6)
        period_end = date.today()

        canonical_score, _band = KPIService.compute_governance_score(
            test_db, kg.id, period_start, period_end
        )
        network_avg = AnalyticsService._compute_network_governance_score(
            test_db, period_start, period_end
        )
        # Single-kindergarten network -> network average equals that KG's score
        assert network_avg == pytest.approx(canonical_score, abs=0.01)

    def test_dashboard_data_endpoint_responds_with_consistent_governance(
        self, client, admin_user, kg_with_risk_data
    ):
        response = client.post(
            "/token", data={"username": "perfadmin", "password": "Admin123!"}
        )
        assert response.status_code == 200
        token = response.json()["access_token"]

        period_start = date.today() - timedelta(days=6)
        period_end = date.today()
        response = client.get(
            "/api/analytics/dashboard-data"
            f"?period_start={period_start.isoformat()}&period_end={period_end.isoformat()}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "governance_avg_score" in data["network_summary"]
        assert "governance_distribution" in data


class TestHighRiskChildrenSchema:
    """Bug 2: get_high_risk_children's dict shape must match what the
    frontend actually consumes."""

    def test_returns_expected_field_names(self, test_db, kg_with_risk_data):
        results = AnalyticsService.get_high_risk_children(test_db, None)
        assert len(results) >= 1
        entry = results[0]
        # These are the exact keys the Risk Intelligence card renderers
        # (window._renderRiskCards / updateRiskRadar) read.
        for key in ("child_id", "kindergarten_id", "child_name", "kindergarten_name",
                    "risk_type", "risk_value", "description"):
            assert key in entry, f"missing field: {key}"
        assert entry["kindergarten_id"] == kg_with_risk_data["kindergarten"].id

    def test_no_stale_fields_present(self, test_db, kg_with_risk_data):
        """The old (never-actually-returned) field names the frontend used
        to read must not silently reappear — this test fails loudly if
        someone reintroduces the mismatch from the other direction."""
        results = AnalyticsService.get_high_risk_children(test_db, None)
        assert len(results) >= 1
        entry = results[0]
        for stale_key in ("name", "kindergarten", "reason", "risk_score"):
            assert stale_key not in entry


class TestRiskRadarIsolation:
    """A failing risk-radar computation must degrade to an empty list, not
    take down the whole dashboard-data payload. network_summary,
    governorate_breakdown, trends, and governance_distribution have nothing
    to do with Risk Intelligence and should still be served."""

    def test_risk_radar_failure_does_not_500_the_dashboard(
        self, client, admin_user, kg_with_risk_data, monkeypatch
    ):
        from sqlalchemy.exc import SQLAlchemyError

        def _boom(*args, **kwargs):
            raise SQLAlchemyError("simulated risk-radar failure")

        monkeypatch.setattr(AnalyticsService, "get_high_risk_children", staticmethod(_boom))

        response = client.post(
            "/token", data={"username": "perfadmin", "password": "Admin123!"}
        )
        assert response.status_code == 200
        token = response.json()["access_token"]

        period_start = date.today() - timedelta(days=6)
        period_end = date.today()
        response = client.get(
            "/api/analytics/dashboard-data"
            f"?period_start={period_start.isoformat()}&period_end={period_end.isoformat()}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["risk_radar"] == []
        assert "governance_avg_score" in data["network_summary"]
        assert "governance_distribution" in data


class TestDataQualitySubIndicatorsAreReal:
    """accuracy_score and timeliness_score used to be arbitrary offsets of
    completeness_percent (completeness + 5%, and a hardcoded 90.0) rather
    than independently measured. Now they come from
    EnhancedDataQualityService's real validity/freshness checks. These tests
    fail loudly if that regresses back to a derived-from-completeness
    formula."""

    def test_accuracy_reflects_real_validity_not_completeness_offset(self, test_db, kg_with_risk_data):
        # kg_with_risk_data's fields are all filled in -> completeness_percent
        # will be 100.0. A negative-capacity class is a real validity defect
        # that must lower accuracy_score below completeness, and specifically
        # NOT equal completeness + 5% (the old fake formula, which would have
        # been 100.0 since it's capped there).
        cls = test_db.query(models.Class).filter_by(kindergarten_id=kg_with_risk_data["kindergarten"].id).first()
        cls.capacity_total = -1
        test_db.commit()

        AnalyticsService.evaluate_data_quality(test_db, user_id=1)
        latest = test_db.query(models.DataQualityMetric).order_by(
            models.DataQualityMetric.evaluated_at.desc()
        ).first()

        assert latest.completeness_percent == pytest.approx(100.0)
        assert latest.accuracy_score < latest.completeness_percent
        assert latest.details["accuracy_issues"], "negative capacity should be a reported validity issue"

    def test_timeliness_reflects_real_report_freshness_not_hardcoded_90(self, test_db, kg_with_risk_data):
        # No DailyReport rows exist anywhere in this fixture -> freshness_latency
        # returns the "no_data" case (score 50.0), not the old hardcoded 90.0.
        AnalyticsService.evaluate_data_quality(test_db, user_id=1)
        latest = test_db.query(models.DataQualityMetric).order_by(
            models.DataQualityMetric.evaluated_at.desc()
        ).first()

        assert latest.timeliness_score == pytest.approx(50.0)
        assert latest.details["timeliness_hours_since_last_report"] is None
