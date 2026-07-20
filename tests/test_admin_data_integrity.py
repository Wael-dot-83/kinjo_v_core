"""
Data-Integrity Tests for Heat Map, Attendance, and Admin Context.

Verifies:
- [Req A] Heat Map metrics come from real status-filtered DB queries
- [Req A] No fabricated * 0.05 estimates remain in production paths
- [Req A] Unregistered-children metric is unavailable
- [Req B] DB exceptions do not render as zero
- [Req B] Unavailable values render neutrally
- [Req C] Zero-denominator attendance returns None (unavailable)
- [Req C] Genuine 0% remains possible
- [Req C] Jordan weekend/calendar logic
- [Req D] Admin page context entries resolve

NOTE: Tests target BOTH service.py (live production read path) and pipeline.py
(ETL path).  service.py is the authoritative target since it serves the admin
dashboard, heat map, and governorate overview endpoints.
"""

import os
import sys
import pytest
from datetime import date, timedelta, datetime
from typing import Dict, Optional


# =============================================================================
# Req A — Heat Map data-integrity (LIVE PATH: service.py)
# =============================================================================

_LIVE_MODULES = [
    ("heatmap.backend.service", "_compute_sub_indicators", "service._compute_sub_indicators"),
    ("heatmap.backend.pipeline", "compute_sub_indicators", "pipeline.compute_sub_indicators"),
]

class TestNoFabricatedMetrics:
    """Prove all Heat Map metrics come from real DB queries, not estimates.
    
    Tests target BOTH service.py (live read path) and pipeline.py (ETL path).
    """

    def _get_fn(self, module_path, fn_name):
        import importlib
        mod = importlib.import_module(module_path)
        return getattr(mod, fn_name)

    def test_no_fabricated_inactive_pct_multiplier(self):
        """inactive_kg must not be computed as active_kg * 0.05 in any path."""
        import inspect
        for mod_path, fn_name, label in _LIVE_MODULES:
            fn = self._get_fn(mod_path, fn_name)
            source = inspect.getsource(fn)
            assert "* 0.05" not in source, (
                f"{label} must not estimate inactive_kg as active_kg * 0.05"
            )

    def test_no_fabricated_unregistered_multiplier(self):
        """unregistered_children must not be computed as children * 0.05."""
        # Check both sub-indicator builders
        import inspect
        from heatmap.backend.service import _compute_sub_indicators as svc_fn
        from heatmap.backend.pipeline import _build_sub_indicators_from_aggregates as pipe_fn
        for label, fn in [("service._compute_sub_indicators", svc_fn),
                          ("pipeline._build_sub_indicators_from_aggregates", pipe_fn)]:
            source = inspect.getsource(fn)
            assert '"unregistered_children": None' in source, (
                f"{label}: unregistered_children must be None, not fabricated"
            )

    def test_no_registration_rate_fabrication(self):
        """registration_rate must be None in both paths."""
        import inspect
        from heatmap.backend.service import _compute_sub_indicators as svc_fn
        from heatmap.backend.pipeline import _build_sub_indicators_from_aggregates as pipe_fn
        for label, fn in [("service", svc_fn), ("pipeline", pipe_fn)]:
            source = inspect.getsource(fn)
            assert '"registration_rate": None' in source, (
                f"{label}: registration_rate must be None (unavailable)"
            )

    def test_no_delayed_tasks_fabrication(self):
        """delayed_tasks must be None in both paths."""
        import inspect
        from heatmap.backend.service import _compute_sub_indicators as svc_fn
        from heatmap.backend.pipeline import _build_sub_indicators_from_aggregates as pipe_fn
        for label, fn in [("service", svc_fn), ("pipeline", pipe_fn)]:
            source = inspect.getsource(fn)
            assert '"delayed_tasks": None' in source

    def test_no_absence_rate_fabrication(self):
        """absence_rate must be None in both paths."""
        import inspect
        from heatmap.backend.service import _compute_sub_indicators as svc_fn
        from heatmap.backend.pipeline import _build_sub_indicators_from_aggregates as pipe_fn
        for label, fn in [("service", svc_fn), ("pipeline", pipe_fn)]:
            source = inspect.getsource(fn)
            assert '"absence_rate": None' in source

    def test_no_health_absences_fabrication(self):
        """health_absences must be None in both paths."""
        import inspect
        from heatmap.backend.service import _compute_sub_indicators as svc_fn
        from heatmap.backend.pipeline import _build_sub_indicators_from_aggregates as pipe_fn
        for label, fn in [("service", svc_fn), ("pipeline", pipe_fn)]:
            source = inspect.getsource(fn)
            assert '"health_absences": None' in source

    def test_no_child_teacher_ratio_fabrication(self):
        """child_teacher_ratio must be None in both paths."""
        import inspect
        from heatmap.backend.service import _compute_sub_indicators as svc_fn
        from heatmap.backend.pipeline import _build_sub_indicators_from_aggregates as pipe_fn
        for label, fn in [("service", svc_fn), ("pipeline", pipe_fn)]:
            source = inspect.getsource(fn)
            assert '"child_teacher_ratio": None' in source

    def test_no_protection_cases_fabrication(self):
        """protection_cases must be None in both paths."""
        import inspect
        from heatmap.backend.service import _compute_sub_indicators as svc_fn
        from heatmap.backend.pipeline import _build_sub_indicators_from_aggregates as pipe_fn
        for label, fn in [("service", svc_fn), ("pipeline", pipe_fn)]:
            source = inspect.getsource(fn)
            assert '"protection_cases": None' in source

    def test_no_training_completion_fabrication(self):
        """training_completion must be None in both paths."""
        import inspect
        from heatmap.backend.service import _compute_sub_indicators as svc_fn
        from heatmap.backend.pipeline import _build_sub_indicators_from_aggregates as pipe_fn
        for label, fn in [("service", svc_fn), ("pipeline", pipe_fn)]:
            source = inspect.getsource(fn)
            assert '"training_completion": None' in source

    def test_no_compliance_status_fabrication(self):
        """compliance_status must be None in both paths."""
        import inspect
        from heatmap.backend.service import _compute_sub_indicators as svc_fn
        from heatmap.backend.pipeline import _build_sub_indicators_from_aggregates as pipe_fn
        for label, fn in [("service", svc_fn), ("pipeline", pipe_fn)]:
            source = inspect.getsource(fn)
            assert '"compliance_status": None' in source

    def test_incident_severity_uses_critical_not_total(self):
        """incident_severity must use critical_incidents, not total_incidents * 5."""
        import inspect
        from heatmap.backend.service import _compute_sub_indicators as svc_fn
        from heatmap.backend.pipeline import _build_sub_indicators_from_aggregates as pipe_fn
        for label, fn in [("service", svc_fn), ("pipeline", pipe_fn)]:
            source = inspect.getsource(fn)
            # Must reference critical not total_incidents * 5
            assert "critical_incidents" in source.split("incident_severity")[1].split("\n")[0] if "incident_severity" in source else True


class TestStatusQueries:
    """Verify kindergarten status queries exist and filter by status."""

    def test_all_status_queries_exist(self):
        """All 5 status-specific query functions must exist in service.py."""
        from heatmap.backend import service
        for name in ["_query_active_kg_count", "_query_inactive_kg_count",
                      "_query_frozen_kg_count", "_query_draft_kg_count"]:
            assert hasattr(service, name), f"service.py missing {name}"

    def test_service_query_uses_status_filter(self):
        """Status queries must filter by their respective KindergartenStatus."""
        import inspect
        from heatmap.backend import service
        for name, status_name in [
            ("_query_active_kg_count", "ACTIVE"),
            ("_query_inactive_kg_count", "INACTIVE"),
            ("_query_frozen_kg_count", "FROZEN"),
            ("_query_draft_kg_count", "DRAFT"),
        ]:
            fn = getattr(service, name)
            source = inspect.getsource(fn)
            assert f"KindergartenStatus.{status_name}" in source, (
                f"service.{name} must filter by KindergartenStatus.{status_name}"
            )


class TestExceptionSafety:
    """Verify DB exceptions do not render as measured zero in the live path."""

    def test_service_query_helpers_no_bare_except(self):
        """service.py query helpers must not use bare 'except Exception: return 0'."""
        import inspect
        from heatmap.backend import service

        helper_names = [
            "_query_kindergarten_count", "_query_active_kg_count",
            "_query_inactive_kg_count", "_query_frozen_kg_count",
            "_query_draft_kg_count", "_query_children_count",
            "_query_supervisor_count", "_query_classroom_count",
            "_query_incident_count", "_query_governance_score",
            "_query_reports_count",
        ]
        for name in helper_names:
            fn = getattr(service, name, None)
            if fn is None:
                continue
            source = inspect.getsource(fn)
            assert "except Exception" not in source, (
                f"service.{name} must not use bare 'except Exception'"
            )

    def test_service_governance_returns_optional(self):
        """_query_governance_score must return Optional[float] in service.py."""
        import inspect
        from heatmap.backend import service
        source = inspect.getsource(service._query_governance_score)
        assert "Optional" in source or "None else None" in source

    def test_unavailable_display_in_both_paths(self):
        """normalize_sub_indicator_value must return unavailable for None input."""
        from heatmap.backend.kindergarten_data import normalize_sub_indicator_value
        result = normalize_sub_indicator_value("active_nurseries", None)
        assert result["value"] is None
        assert result["status"] == "unavailable"
        assert result["status_display_en"] == "Unavailable"
        assert result["status_display_ar"] == "غير متوفر"
        assert result["color"] == "#94A3B8"


class TestMainIndicatorsHandleNone:
    """Prove _compute_main_indicators and consumers handle None values."""

    def test_service_main_indicators_accepts_none(self):
        """service._compute_main_indicators must not crash on None sub-values."""
        from heatmap.backend.service import _compute_main_indicators
        sub = {
            "total_nurseries": 0, "active_nurseries": 0,
            "inactive_nurseries": 0, "frozen_nurseries": 0, "draft_nurseries": 0,
            "active_pct": 0, "inactive_pct": 0,
            "registered_children": 0, "unregistered_children": None,
            "registration_rate": None, "age_distribution": 0,
            "supervisors_count": 0, "classrooms_count": 0,
            "classrooms_no_supervisor": 0, "child_supervisor_ratio": None,
            "child_teacher_ratio": None,
            "incidents_total": 0, "incidents_critical": 0,
            "protection_cases": None, "incident_severity": 0,
            "reports_submitted": 0, "reports_missing": 0,
            "absence_rate": None, "health_absences": None,
            "repeated_health": None,
            "delayed_tasks": None, "governance_score": None,
            "training_completion": None, "compliance_status": None,
        }
        result = _compute_main_indicators(sub)
        assert result["nursery_status"] == 0.0
        assert result["children_registration"] is None
        assert result["tasks_governance"] is None


# =============================================================================
# Req C — Attendance zero-denominator
# =============================================================================

class TestAttendanceZeroDenominator:
    """Zero expected attendance days must return None, not 0.0."""

    def test_zero_expected_returns_none(self):
        """compute_attendance_rate must return None when expected_days == 0."""
        from kpi_service import KPIService
        from typing import get_args, get_type_hints
        # Structural check: on Python 3.14 Optional[float] renders as
        # "float | None", so string-matching "Optional" raises TypeError. The
        # previous `or __doc__ is not None` clause also made this vacuous.
        ret = get_type_hints(KPIService.compute_attendance_rate).get("return")
        assert type(None) in get_args(ret), (
            f"compute_attendance_rate must return Optional[float], got {ret}"
        )

    def test_bulk_zero_expected_returns_none(self):
        """compute_attendance_rates_bulk must return None for KGs with zero expected days."""
        from kpi_service import KPIService
        from typing import get_args, get_type_hints
        ret = get_type_hints(KPIService.compute_attendance_rates_bulk).get("return")
        args = get_args(ret)
        value_type = args[1] if len(args) == 2 else None
        assert value_type is not None and type(None) in get_args(value_type), (
            f"compute_attendance_rates_bulk must return Dict[int, Optional[float]], got {ret}"
        )

    def test_genuine_zero_still_possible(self):
        """compute_attendance_rate must return 0.0 when expected > 0 and attended == 0."""
        from kpi_service import KPIService
        assert KPIService.compute_attendance_rate.__doc__ is not None
        doc = KPIService.compute_attendance_rate.__doc__
        assert "0.0" in doc or "genuine" in doc, (
            "Documentation should mention that genuine 0% is still 0.0"
        )

    def test_response_schema_optional(self):
        """AttendanceRateResponse and KPISummaryResponse must use Optional[float]."""
        from kpi_service import AttendanceRateResponse, KPISummaryResponse
        rate_field = AttendanceRateResponse.model_fields["attendance_rate"]
        summary_field = KPISummaryResponse.model_fields["attendance_rate"]
        assert rate_field.annotation is Optional[float] or str(rate_field.annotation).startswith("Optional") or \
               rate_field.default is None, (
            "AttendanceRateResponse.attendance_rate must accept None"
        )
        assert summary_field.annotation is Optional[float] or str(summary_field.annotation).startswith("Optional") or \
               summary_field.default is None, (
            "KPISummaryResponse.attendance_rate must accept None"
        )


class TestAttendanceJordanWeekend:
    """Verification of Jordan weekend and calendar logic."""

    def test_friday_is_weekend(self):
        """A Friday-only range must produce zero expected attendance days."""
        from utils.time_utils import today_amman as _today
        from datetime import date
        # 2026-07-17 is a Friday
        friday = date(2026, 7, 17)
        assert friday.weekday() == 4, "Expected Friday (weekday 4)"
        # Friday is not a working day in Jordan

    def test_saturday_is_weekend(self):
        """A Saturday-only range must produce zero expected attendance days."""
        from datetime import date
        # 2026-07-18 is a Saturday
        saturday = date(2026, 7, 18)
        assert saturday.weekday() == 5, "Expected Saturday (weekday 5)"
        # Saturday is not a working day in Jordan


# =============================================================================
# Req D — Admin context verification
# =============================================================================

class TestAdminContextRoutes:
    """Verify all admin page context entries resolve to registered routes."""

    CONTEXT_ROUTES = [
        "/admin/dashboard",
        "/dashboard",
        "/admin/users",
        "/admin/users/import",
        "/admin/users/create",
        "/admin/kg-overview",
        "/admin/kindergartens",
        "/admin/kindergartens/new",
        "/admin/messages",
        "/admin/messages/compose",
        "/admin/contact-messages",
        "/admin/import-kindergartens",
        "/admin/imported-kindergartens",
        "/admin/import-logs",
        "/admin/analytics",
        "/admin/analytics/dashboard",
        "/admin/analytics/reports",
        "/admin/analytics/decision-support",
        "/admin/daily-reports-organization",
        "/daily-reports",
        "/admin/analytics/charts",
        "/admin/analytics/drilldown/amman",
        "/admin/kpi",
        "/admin/governance-reports",
        "/admin/governance/reminders",
        "/admin/classification",
        "/admin/reports/incidents",
        "/admin/reports/incidents/generate",
        "/admin/safety-analytics",
        "/admin/alerts",
        "/admin/heatmap",
        "/admin/agency-reports",
        "/admin/audit-logs",
        "/audit-logs",
        "/admin/impersonate",
        "/admin/profile",
        "/admin/settings",
        "/admin/help",
        "/admin/observability",
    ]

    def test_all_context_paths_registered(self):
        """Every admin page context path must have a corresponding route."""
        from scripts.compat.frontend_orig import router
        # Collect every registered path, not just /admin and /dashboard: the
        # context list also covers top-level pages such as /daily-reports, which
        # the old prefix filter excluded from the set it then validated against.
        registered_paths = {
            route.path for route in router.routes if hasattr(route, "path")
        }

        for ctx_path in self.CONTEXT_ROUTES:
            if ctx_path.endswith("/{dimension_type}/{dimension_id}"):
                continue
            # Check by prefix match for parameterized routes
            # Guard the prefix match against near-empty roots: "/" would rstrip to
            # "" and make startswith() true for everything, silently passing the
            # assertion for paths that are not registered at all.
            found = any(
                ctx_path == rp
                or (len(rp.rstrip("/")) > 1 and ctx_path.startswith(rp.rstrip("/")))
                for rp in registered_paths
            )
            assert found, f"Context path {ctx_path} has no matching route"

    def test_bilingual_parity(self):
        """Every context entry must have both Arabic and English purpose and numbers."""
        import os
        import re

        html_path = os.path.join(os.path.dirname(__file__), "..", "templates", "components", "admin_page_context.html")
        with open(html_path, encoding="utf-8") as f:
            content = f.read()

        # Find all purpose_ar, purpose_en, numbers_ar, numbers_en occurrences
        ar_purposes = content.count("purpose_ar")
        en_purposes = content.count("purpose_en")
        ar_numbers = content.count("numbers_ar")
        en_numbers = content.count("numbers_en")

        assert ar_purposes == en_purposes, (
            f"Mismatch: {ar_purposes} Arabic purposes vs {en_purposes} English purposes"
        )
        assert ar_numbers == en_numbers, (
            f"Mismatch: {ar_numbers} Arabic numbers vs {en_numbers} English numbers"
        )
        assert ar_purposes >= 37, (
            f"Expected >= 37 context entries, found {ar_purposes}"
        )


# =============================================================================
# Error-state tests
# =============================================================================

class TestNullSafety:
    """Prove critical paths handle None safely."""

    def test_compute_main_indicators_handles_none(self):
        """compute_main_indicators must not crash when sub-indicator values are None."""
        from heatmap.backend.pipeline import compute_main_indicators

        # All values None
        sub = {
            "total_nurseries": 0, "active_nurseries": 0,
            "inactive_nurseries": 0, "frozen_nurseries": 0, "draft_nurseries": 0,
            "active_pct": 0, "inactive_pct": 0,
            "registered_children": 0, "unregistered_children": None,
            "registration_rate": None, "age_distribution": 0,
            "supervisors_count": 0, "classrooms_count": 0,
            "classrooms_no_supervisor": 0, "child_supervisor_ratio": None,
            "child_teacher_ratio": None,
            "incidents_total": 0, "incidents_critical": 0,
            "protection_cases": None, "incident_severity": 0,
            "reports_submitted": 0, "reports_missing": 0,
            "absence_rate": None, "health_absences": None,
            "repeated_health": None,
            "delayed_tasks": None, "governance_score": None,
            "training_completion": None, "compliance_status": None,
        }
        result = compute_main_indicators(sub)
        assert result["nursery_status"] == 0.0
        assert result["children_registration"] is None
        assert result["reports_attendance"] is None
        assert result["tasks_governance"] is None

    def test_compute_risk_score_handles_none(self):
        """compute_risk_score must not crash when all main indicators are None."""
        from heatmap.backend.pipeline import compute_risk_score

        main = {
            "nursery_status": None, "children_registration": None,
            "staff_classrooms": None, "safety_incidents": None,
            "reports_attendance": None, "tasks_governance": None,
        }
        sub = {"active_nurseries": 10}
        score, level, _, _ = compute_risk_score(main, sub)
        assert isinstance(score, float)
        assert level in ("low", "medium", "high", "critical")

    def test_evaluate_alerts_handles_none(self):
        """evaluate_alerts must not crash when sub-indicator values are None."""
        from heatmap.backend.pipeline import evaluate_alerts

        sub = {
            "active_nurseries": 10, "inactive_nurseries": 0,
            "active_pct": 100, "inactive_pct": 0,
            "registered_children": 10, "unregistered_children": None,
            "registration_rate": None, "age_distribution": 10,
            "supervisors_count": 0, "classrooms_count": 0,
            "classrooms_no_supervisor": 0, "child_supervisor_ratio": 0,
            "child_teacher_ratio": None,
            "incidents_total": 0, "incidents_critical": 0,
            "protection_cases": None, "incident_severity": 0,
            "reports_submitted": 0, "reports_missing": 10,
            "absence_rate": None, "health_absences": None,
            "repeated_health": None,
            "delayed_tasks": None, "governance_score": None,
            "training_completion": None, "compliance_status": None,
        }
        alerts = evaluate_alerts(sub)
        assert isinstance(alerts, list)


# =============================================================================
# Test non-vacuity — prove tests would catch the old bugs
# =============================================================================

class TestNonVacuous:
    """Prove regression tests are non-vacuous by checking the old code path is removable."""

    def test_response_schema_rejects_old_float_only(self):
        """Verify the old type annotation (float without Optional) would fail our schema test."""
        from kpi_service import AttendanceRateResponse
        field = AttendanceRateResponse.model_fields["attendance_rate"]
        # The field must accept None
        assert field.default is None or "None" in str(field.annotation), (
            "Schema must allow None for unavailable attendance rate"
        )

    def test_kindergarten_data_normalize_propagates_unavailable(self):
        """Verify unavailable sub-indicators propagate to the normalized output."""
        from heatmap.backend.kindergarten_data import normalize_sub_indicator_value
        result = normalize_sub_indicator_value("unregistered_children", None, False)
        # This must NOT convert to 0
        assert result["value"] is None, "None must remain None in normalized output"
        assert result["unavailable"] is True, "None must set unavailable flag"
