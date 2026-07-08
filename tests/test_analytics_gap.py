"""
Tests for analytics_gap_service.py — All 33 metrics across 6 layers.

Strategy: use the shared conftest in-memory SQLite test DB with minimal seed data
so each layer returns a structurally valid LayerMetricsResponse even when counts
are all zero.  Structural assertions check:
  - correct layer name
  - all expected metric slugs are present
  - every metric has a numeric value and a well-formed chart
  - chart datasets are non-empty lists with matching backgroundColor length
  - chart thresholds / colours are dicts when provided
Data-driven assertions (non-zero values) are only applied where we seed data.
"""
from __future__ import annotations

import os
os.environ.setdefault("TESTING", "true")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("SECRET_KEY", "analytics-gap-test-secret-key-xxx")

import pytest
from datetime import date, datetime, timedelta, timezone

import models
from analytics_gap_service import (
    AnalyticsGapService,
    _gini,
    _cv,
    _slope,
    _nps,
    _linear_forecast,
)


# ─── Seed helpers ─────────────────────────────────────────────────────────────

def _make_kg(db, name_ar="حضانة تجريبية", name_en="Test KG", gov="عمّان"):
    kg = models.Kindergarten(
        name_ar=name_ar,
        name_en=name_en,
        governorate=gov,
        district="عمّان",
        area="المدينة",
        address_line="شارع الاختبار",
        contact_phone="0791234567",
        status=models.KindergartenStatus.ACTIVE,
        license_valid_until=date.today() + timedelta(days=180),
    )
    db.add(kg)
    db.flush()
    return kg


def _make_class(db, kg_id, capadistrict=20):
    cls = models.Class(
        kindergarten_id=kg_id,
        name_ar="فصل الاختبار",
        name_en="Test Class",
        class_code=f"TC-{kg_id}-{id(db)}",
        age_group="AGE_2_4",
        enrolled_children_count=5,
        capacity_total=capadistrict,
        min_age_months=24,
        max_age_months=48,
        is_active=True,
    )
    db.add(cls)
    db.flush()
    return cls


def _make_parent(db, suffix=""):
    user = models.User(
        username=f"parent_{id(db)}_{suffix}",
        email=f"parent_{id(db)}_{suffix}@test.com",
        hashed_password="hashed",
        role=models.UserRole.PARENT,
        status=models.UserStatus.ACTIVE,
    )
    db.add(user)
    db.flush()
    profile = models.ParentProfile(
        user_id=user.id,
        first_name="أحمد",
        last_name="محمد",
        phone_number="0791234567",
        gender=models.Gender.MALE,
        nationality="أردني",
        home_governorate="عمّان",
        home_district="عمّان",
        home_area="المدينة",
        home_address_line="شارع الاختبار 1",
    )
    db.add(profile)
    db.flush()
    return user, profile


def _make_child(db, parent_id, dob=None):
    if dob is None:
        dob = date.today() - timedelta(days=900)  # ~30 months
    child = models.Child(
        parent_id=parent_id,
        first_name="سارة",
        last_name="محمد",
        gender=models.Gender.FEMALE,
        date_of_birth=dob,
        father_name="محمد",
        mother_first_name="فاطمة",
        mother_last_name="علي",
        mother_nationality="أردنية",
    )
    db.add(child)
    db.flush()
    return child


def _make_enrollment(db, child_id, kg_id, class_id=None):
    ea = models.EnrollmentApplication(
        child_id=child_id,
        kindergarten_id=kg_id,
        class_id=class_id,
        status=models.EnrollmentStatus.ACTIVE,
        is_active=True,
        enrollment_start_date=date.today() - timedelta(days=60),
    )
    db.add(ea)
    db.flush()
    return ea


def _make_manager(db, kg_id, suffix=""):
    user = models.User(
        username=f"mgr_{kg_id}_{suffix}",
        email=f"mgr_{kg_id}_{suffix}@test.com",
        hashed_password="hashed",
        role=models.UserRole.MANAGER,
        status=models.UserStatus.ACTIVE,
        kindergarten_id=kg_id,
    )
    db.add(user)
    db.flush()
    return user


# ─── Stat helper unit tests ───────────────────────────────────────────────────

class TestStatHelpers:
    def test_gini_equal_values(self):
        assert _gini([10.0, 10.0, 10.0]) == 0.0

    def test_gini_empty(self):
        assert _gini([]) == 0.0

    def test_gini_bounded(self):
        import random
        vals = [random.uniform(0, 100) for _ in range(50)]
        g = _gini(vals)
        assert 0.0 <= g <= 1.0

    def test_cv_uniform(self):
        assert _cv([5.0, 5.0, 5.0]) == 0.0

    def test_cv_empty(self):
        assert _cv([]) == 0.0

    def test_slope_increasing(self):
        assert _slope([1.0, 2.0, 3.0, 4.0]) > 0

    def test_slope_decreasing(self):
        assert _slope([4.0, 3.0, 2.0, 1.0]) < 0

    def test_slope_constant(self):
        assert _slope([5.0, 5.0, 5.0]) == 0.0

    def test_nps_all_promoters(self):
        assert _nps([10, 10, 9, 10]) == 100.0

    def test_nps_all_detractors(self):
        assert _nps([0, 1, 2, 6]) == -100.0

    def test_nps_empty(self):
        assert _nps([]) == 0.0

    def test_nps_mixed(self):
        # 2 promoters, 1 passive, 1 detractor → (2-1)/4 * 100 = 25
        assert _nps([9, 10, 8, 3]) == 25.0

    def test_linear_forecast_length(self):
        fc = _linear_forecast([1.0, 2.0, 3.0, 4.0, 5.0], 3)
        assert len(fc) == 3

    def test_linear_forecast_direction(self):
        fc = _linear_forecast([1.0, 2.0, 3.0], 2)
        assert fc[1] > fc[0]


# ─── Chart DTO structural tests ───────────────────────────────────────────────

class TestChartStructure:
    def test_all_network_metrics_have_chart(self, test_db):
        svc = AnalyticsGapService(test_db)
        result = svc.get_network_metrics("en")
        for m in result.metrics:
            assert m.chart.type, f"Missing chart.type on {m.metric}"
            assert isinstance(m.chart.datasets, list)
            assert m.chart.datasets, f"Empty datasets on {m.metric}"
            assert "en" in m.chart.datasets[0].label
            assert "ar" in m.chart.datasets[0].label

    def test_background_color_length_matches_data(self, test_db):
        svc = AnalyticsGapService(test_db)
        for layer_fn in [
            svc.get_network_metrics,
            svc.get_predictive_metrics,
            svc.get_governance_metrics,
        ]:
            result = layer_fn("en")
            for m in result.metrics:
                for ds in m.chart.datasets:
                    if ds.backgroundColor:
                        assert len(ds.backgroundColor) == len(ds.data), \
                            f"Color/data length mismatch on {m.metric}"


# ─── Network layer (Metrics 1-7) ─────────────────────────────────────────────

NETWORK_SLUGS = {
    "equity_index",
    "capacity_pressure",
    "digital_engagement",
    "license_expiry_distribution",
    "network_attendance_rate",
    "staff_turnover_proxy",
    "network_improvement_velocity",
}


class TestNetworkLayer:
    def test_returns_all_7_metrics_empty_db(self, test_db):
        result = AnalyticsGapService(test_db).get_network_metrics("en")
        assert result.layer == "network"
        assert {m.metric for m in result.metrics} == NETWORK_SLUGS

    def test_locale_propagated(self, test_db):
        for locale in ("en", "ar"):
            result = AnalyticsGapService(test_db).get_network_metrics(locale)
            assert result.locale == locale
            for m in result.metrics:
                assert m.locale == locale

    def test_equity_zero_no_data(self, test_db):
        result = AnalyticsGapService(test_db).get_network_metrics("en")
        eq = next(m for m in result.metrics if m.metric == "equity_index")
        assert eq.value == 0.0

    def test_license_expiry_pie_has_5_slices(self, test_db):
        result = AnalyticsGapService(test_db).get_network_metrics("en")
        lic = next(m for m in result.metrics if m.metric == "license_expiry_distribution")
        assert lic.chart.type == "pie"
        assert len(lic.chart.datasets[0].data) == 5

    def test_velocity_chart_line_12_weeks(self, test_db):
        result = AnalyticsGapService(test_db).get_network_metrics("en")
        vel = next(m for m in result.metrics if m.metric == "network_improvement_velocity")
        assert vel.chart.type == "line"
        assert len(vel.chart.datasets[0].data) == 12

    def test_capacity_pressure_with_data(self, test_db):
        kg = _make_kg(test_db)
        _make_class(test_db, kg.id, capadistrict=10)  # enrolled=5, cap=10 → 50%
        test_db.commit()
        result = AnalyticsGapService(test_db).get_network_metrics("en")
        cap = next(m for m in result.metrics if m.metric == "capacity_pressure")
        assert cap.value == 50.0

    def test_staff_turnover_inactive_staff(self, test_db):
        kg = _make_kg(test_db)
        test_db.add(models.User(
            username="mgr_act", email="ma@t.com", hashed_password="h",
            role=models.UserRole.MANAGER, status=models.UserStatus.ACTIVE,
            kindergarten_id=kg.id,
        ))
        test_db.add(models.User(
            username="mgr_inact", email="mi@t.com", hashed_password="h",
            role=models.UserRole.MANAGER, status=models.UserStatus.INACTIVE,
            kindergarten_id=kg.id,
        ))
        test_db.commit()
        result = AnalyticsGapService(test_db).get_network_metrics("en")
        turnover = next(m for m in result.metrics if m.metric == "staff_turnover_proxy")
        assert turnover.value == 50.0


# ─── Governorate layer (Metrics 8-14) ─────────────────────────────────────────

GOV_SLUGS = {
    "interkg_variance",
    "chronic_absenteeism_rate",
    "parent_nps",
    "incident_density",
    "report_submission_rate",
    "enrollment_growth_rate",
    "avg_gqi",
}


class TestGovernorateLayer:
    def test_unknown_gov_returns_no_data(self, test_db):
        result = AnalyticsGapService(test_db).get_governorate_metrics("UNKNOWN_XYZ", "en")
        assert result.layer == "governorate"
        assert result.metrics[0].metric == "no_data"

    def test_known_gov_returns_all_7_metrics(self, test_db):
        _make_kg(test_db, gov="TestGov")
        test_db.commit()
        result = AnalyticsGapService(test_db).get_governorate_metrics("TestGov", "en")
        assert {m.metric for m in result.metrics} == GOV_SLUGS

    def test_nps_chart_type_bar(self, test_db):
        _make_kg(test_db, gov="NPSGov")
        test_db.commit()
        result = AnalyticsGapService(test_db).get_governorate_metrics("NPSGov", "en")
        nps_m = next(m for m in result.metrics if m.metric == "parent_nps")
        assert nps_m.chart.type == "bar"
        assert len(nps_m.chart.datasets[0].data) == 3  # promoters, passives, detractors

    def test_nps_computed_correctly(self, test_db):
        kg = _make_kg(test_db, gov="NpsComputeGov")
        survey = models.Survey(
            kindergarten_id=kg.id, title="Test Survey",
            nps_question_enabled=True,
            start_date=date.today() - timedelta(days=60),
            end_date=date.today(),
        )
        test_db.add(survey)
        test_db.flush()
        parent_user, _ = _make_parent(test_db, "nps")
        test_db.add(models.SurveyResponse(
            survey_id=survey.id, parent_id=parent_user.id, nps_score=10
        ))
        test_db.commit()
        result = AnalyticsGapService(test_db).get_governorate_metrics("NpsComputeGov", "en")
        nps_m = next(m for m in result.metrics if m.metric == "parent_nps")
        assert nps_m.value == 100.0

    def test_incident_density_bar_chart(self, test_db):
        _make_kg(test_db, gov="IncGov")
        test_db.commit()
        result = AnalyticsGapService(test_db).get_governorate_metrics("IncGov", "en")
        inc_m = next(m for m in result.metrics if m.metric == "incident_density")
        assert inc_m.chart.type == "bar"


# ─── Kindergarten layer (Metrics 15-22) ───────────────────────────────────────

KG_SLUGS = {
    "child_risk_composite",
    "parent_engagement_rate",
    "teacher_timeliness_score",
    "meal_compliance_rate",
    "health_alert_density",
    "data_quality_score",
    "age_appropriateness_index",
    "safeguarding_resolution_rate",
}


class TestKGLayer:
    def test_returns_all_8_metrics(self, test_db):
        kg = _make_kg(test_db)
        test_db.commit()
        result = AnalyticsGapService(test_db).get_kg_metrics(kg.id, "en")
        assert {m.metric for m in result.metrics} == KG_SLUGS

    def test_chart_types(self, test_db):
        kg = _make_kg(test_db)
        test_db.commit()
        result = AnalyticsGapService(test_db).get_kg_metrics(kg.id, "en")
        ct = {m.metric: m.chart.type for m in result.metrics}
        assert ct["child_risk_composite"] == "bar"
        assert ct["parent_engagement_rate"] == "gauge"
        assert ct["meal_compliance_rate"] == "bar"
        assert ct["age_appropriateness_index"] == "pie"

    def test_meal_compliance_4_bars(self, test_db):
        kg = _make_kg(test_db)
        test_db.commit()
        result = AnalyticsGapService(test_db).get_kg_metrics(kg.id, "en")
        meal = next(m for m in result.metrics if m.metric == "meal_compliance_rate")
        assert len(meal.chart.datasets[0].data) == 4

    def test_risk_histogram_4_buckets(self, test_db):
        kg = _make_kg(test_db)
        test_db.commit()
        result = AnalyticsGapService(test_db).get_kg_metrics(kg.id, "en")
        risk = next(m for m in result.metrics if m.metric == "child_risk_composite")
        assert len(risk.chart.datasets[0].data) == 4

    def test_data_quality_100_with_complete_profiles(self, test_db):
        kg = _make_kg(test_db)
        _, parent = _make_parent(test_db, "dq")
        child = _make_child(test_db, parent.id)
        _make_enrollment(test_db, child.id, kg.id)
        test_db.commit()
        result = AnalyticsGapService(test_db).get_kg_metrics(kg.id, "en")
        dq = next(m for m in result.metrics if m.metric == "data_quality_score")
        assert dq.value == 100.0

    def test_safeguarding_rate_100_no_cases(self, test_db):
        kg = _make_kg(test_db)
        test_db.commit()
        result = AnalyticsGapService(test_db).get_kg_metrics(kg.id, "en")
        sg = next(m for m in result.metrics if m.metric == "safeguarding_resolution_rate")
        assert sg.value == 100.0

    def test_age_appropriateness_100_correct_age(self, test_db):
        kg = _make_kg(test_db)
        cls = _make_class(test_db, kg.id)  # 24-48 months
        _, parent = _make_parent(test_db, "age")
        child = _make_child(test_db, parent.id, dob=date.today() - timedelta(days=900))
        _make_enrollment(test_db, child.id, kg.id, class_id=cls.id)
        test_db.commit()
        result = AnalyticsGapService(test_db).get_kg_metrics(kg.id, "en")
        ai = next(m for m in result.metrics if m.metric == "age_appropriateness_index")
        assert ai.value == 100.0

    def test_health_alert_density_nonzero_with_sick_reports(self, test_db):
        kg = _make_kg(test_db)
        mgr = _make_manager(test_db, kg.id, "hd")
        _, parent = _make_parent(test_db, "hd")
        child = _make_child(test_db, parent.id)
        test_db.flush()
        dr = models.DailyReport(
            child_id=child.id, kindergarten_id=kg.id,
            date=date.today() - timedelta(days=1),
            status=models.DailyReportStatus.APPROVED,
            submitted_by=mgr.id, arrival_time="08:00",
            mood="sick",
        )
        test_db.add(dr)
        test_db.commit()
        result = AnalyticsGapService(test_db).get_kg_metrics(kg.id, "en")
        hd = next(m for m in result.metrics if m.metric == "health_alert_density")
        assert hd.value == 100.0  # 1/1 sick report = 100%


# ─── Child layer (Metrics 23-27) ──────────────────────────────────────────────

CHILD_SLUGS = {
    "child_attendance_pattern",
    "child_development_profile",
    "child_engagement_score",
    "child_incident_history",
    "child_health_alerts",
}


class TestChildLayer:
    def test_returns_all_5_metrics(self, test_db):
        _, parent = _make_parent(test_db, "ch")
        child = _make_child(test_db, parent.id)
        test_db.commit()
        result = AnalyticsGapService(test_db).get_child_metrics(child.id, "en")
        assert {m.metric for m in result.metrics} == CHILD_SLUGS

    def test_chart_types(self, test_db):
        _, parent = _make_parent(test_db, "chtype")
        child = _make_child(test_db, parent.id)
        test_db.commit()
        result = AnalyticsGapService(test_db).get_child_metrics(child.id, "en")
        ct = {m.metric: m.chart.type for m in result.metrics}
        assert ct["child_attendance_pattern"] == "bar"
        assert ct["child_development_profile"] == "radar"
        assert ct["child_engagement_score"] == "bar"
        assert ct["child_incident_history"] == "bar"
        assert ct["child_health_alerts"] == "bar"

    def test_attendance_4_bars(self, test_db):
        _, parent = _make_parent(test_db, "att4")
        child = _make_child(test_db, parent.id)
        test_db.commit()
        result = AnalyticsGapService(test_db).get_child_metrics(child.id, "en")
        att = next(m for m in result.metrics if m.metric == "child_attendance_pattern")
        assert len(att.chart.datasets[0].data) == 4

    def test_development_radar_4_domains(self, test_db):
        _, parent = _make_parent(test_db, "dev4")
        child = _make_child(test_db, parent.id)
        test_db.commit()
        result = AnalyticsGapService(test_db).get_child_metrics(child.id, "en")
        dev = next(m for m in result.metrics if m.metric == "child_development_profile")
        assert len(dev.chart.labels) == 4

    def test_incident_history_seeded(self, test_db):
        kg = _make_kg(test_db)
        mgr = _make_manager(test_db, kg.id, "inc")
        _, parent = _make_parent(test_db, "inc")
        child = _make_child(test_db, parent.id)
        test_db.flush()
        test_db.add(models.Incident(
            child_id=child.id, kindergarten_id=kg.id,
            type=models.IncidentType.INJURY,
            severity_level=models.SeverityLevel.HIGH,
            description="Test incident",
            occurred_at=datetime.now(timezone.utc) - timedelta(days=5),
            reported_by=mgr.id,
        ))
        test_db.commit()
        result = AnalyticsGapService(test_db).get_child_metrics(child.id, "en")
        inc_m = next(m for m in result.metrics if m.metric == "child_incident_history")
        assert inc_m.value == 1.0
        assert inc_m.chart.datasets[0].data[2] == 1.0  # HIGH index = 2

    def test_engagement_score_with_reports(self, test_db):
        kg = _make_kg(test_db)
        mgr = _make_manager(test_db, kg.id, "eng")
        _, parent = _make_parent(test_db, "eng")
        child = _make_child(test_db, parent.id)
        test_db.flush()
        test_db.add(models.DailyReport(
            child_id=child.id, kindergarten_id=kg.id,
            date=date.today() - timedelta(days=1),
            status=models.DailyReportStatus.APPROVED,
            submitted_by=mgr.id, arrival_time="08:00",
            breakfast=True, snack=True, milk=True, lunch=True,
            mood="happy", nap_duration_minutes=60,
        ))
        test_db.commit()
        result = AnalyticsGapService(test_db).get_child_metrics(child.id, "en")
        eng = next(m for m in result.metrics if m.metric == "child_engagement_score")
        assert eng.value > 0


# ─── Predictive layer (Metrics 28-31) ─────────────────────────────────────────

PRED_SLUGS = {
    "dropout_risk",
    "performance_trajectory",
    "enrollment_forecast",
    "anomaly_cross_correlation",
}


class TestPredictiveLayer:
    def test_returns_all_4_metrics(self, test_db):
        result = AnalyticsGapService(test_db).get_predictive_metrics("en")
        assert result.layer == "predictive"
        assert {m.metric for m in result.metrics} == PRED_SLUGS

    def test_chart_types(self, test_db):
        result = AnalyticsGapService(test_db).get_predictive_metrics("en")
        ct = {m.metric: m.chart.type for m in result.metrics}
        assert ct["dropout_risk"] == "bar"
        assert ct["performance_trajectory"] == "pie"
        assert ct["enrollment_forecast"] == "line"
        assert ct["anomaly_cross_correlation"] == "line"

    def test_trajectory_pie_3_slices(self, test_db):
        result = AnalyticsGapService(test_db).get_predictive_metrics("en")
        pt = next(m for m in result.metrics if m.metric == "performance_trajectory")
        assert len(pt.chart.datasets[0].data) == 3

    def test_forecast_two_datasets(self, test_db):
        result = AnalyticsGapService(test_db).get_predictive_metrics("en")
        ef = next(m for m in result.metrics if m.metric == "enrollment_forecast")
        assert len(ef.chart.datasets) == 2

    def test_cross_correlation_two_series_12_weeks(self, test_db):
        result = AnalyticsGapService(test_db).get_predictive_metrics("en")
        cc = next(m for m in result.metrics if m.metric == "anomaly_cross_correlation")
        assert len(cc.chart.datasets) == 2
        assert len(cc.chart.datasets[0].data) == 12


# ─── Governance layer (Metrics 32-33) ─────────────────────────────────────────

GOV_LAYER_SLUGS = {"enhanced_gqi", "network_health_composite"}


class TestGovernanceLayer:
    def test_returns_both_metrics(self, test_db):
        result = AnalyticsGapService(test_db).get_governance_metrics("en")
        assert result.layer == "governance"
        assert {m.metric for m in result.metrics} == GOV_LAYER_SLUGS

    def test_gqi_radar_7_sub_indicators(self, test_db):
        result = AnalyticsGapService(test_db).get_governance_metrics("en")
        gqi = next(m for m in result.metrics if m.metric == "enhanced_gqi")
        assert gqi.chart.type == "radar"
        assert len(gqi.chart.labels) == 7
        assert len(gqi.chart.datasets[0].data) == 7

    def test_health_composite_bar_6_bars(self, test_db):
        result = AnalyticsGapService(test_db).get_governance_metrics("en")
        hc = next(m for m in result.metrics if m.metric == "network_health_composite")
        assert hc.chart.type == "bar"
        assert len(hc.chart.datasets[0].data) == 6

    def test_gqi_in_0_100_range(self, test_db):
        result = AnalyticsGapService(test_db).get_governance_metrics("en")
        gqi = next(m for m in result.metrics if m.metric == "enhanced_gqi")
        assert 0.0 <= gqi.value <= 100.0

    def test_ar_and_en_labels_differ(self, test_db):
        svc = AnalyticsGapService(test_db)
        en_res = svc.get_governance_metrics("en")
        ar_res = svc.get_governance_metrics("ar")
        en_labels = en_res.metrics[0].chart.labels
        ar_labels = ar_res.metrics[0].chart.labels
        assert en_labels != ar_labels


# ─── API endpoint smoke tests ─────────────────────────────────────────────────

class TestAPIEndpoints:
    """Smoke-test all 6+1 endpoints via TestClient with DB and auth overrides."""

    @pytest.fixture
    def auth_client(self, test_db):
        from fastapi.testclient import TestClient
        from main import app
        from database import get_db
        from dependencies import require_admin
        from auth import get_password_hash

        admin = models.User(
            username="api_admin_gap",
            email="apiadmin@gap.com",
            hashed_password=get_password_hash("Admin@1234"),
            role=models.UserRole.ADMIN,
            status=models.UserStatus.ACTIVE,
        )
        test_db.add(admin)
        test_db.commit()

        def override_db():
            yield test_db

        def override_admin():
            return {"id": admin.id, "role": "ADMIN", "username": admin.username}

        app.dependency_overrides[get_db] = override_db
        app.dependency_overrides[require_admin] = override_admin

        with TestClient(app) as c:
            yield c

        app.dependency_overrides.clear()

    def test_network_200_with_7_metrics(self, auth_client):
        r = auth_client.get("/api/admin/analytics/network?locale=en")
        assert r.status_code == 200
        body = r.json()
        assert body["layer"] == "network"
        assert len(body["metrics"]) == 7

    def test_governorates_list_endpoint(self, auth_client):
        r = auth_client.get("/api/admin/analytics/governorates")
        assert r.status_code == 200
        assert "governorates" in r.json()

    def test_unknown_governorate_returns_no_data(self, auth_client):
        r = auth_client.get("/api/admin/analytics/governorate/NOWHERE?locale=en")
        assert r.status_code == 200
        body = r.json()
        assert body["metrics"][0]["metric"] == "no_data"

    def test_predictive_200_with_4_metrics(self, auth_client):
        r = auth_client.get("/api/admin/analytics/predictive?locale=en")
        assert r.status_code == 200
        body = r.json()
        assert body["layer"] == "predictive"
        assert len(body["metrics"]) == 4

    def test_governance_200_with_2_metrics(self, auth_client):
        r = auth_client.get("/api/admin/analytics/governance?locale=en")
        assert r.status_code == 200
        body = r.json()
        assert body["layer"] == "governance"
        assert len(body["metrics"]) == 2

    def test_unauthenticated_returns_401_or_403(self, test_db):
        from fastapi.testclient import TestClient
        from main import app

        with TestClient(app) as c:
            r = c.get("/api/admin/analytics/network")
        assert r.status_code in (401, 403)
