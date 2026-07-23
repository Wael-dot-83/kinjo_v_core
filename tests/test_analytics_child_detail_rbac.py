"""Tests for the analytics:child_detail capability (ADMIN-only) and its
suppression behavior in the calculator layer."""
import types

import models
from analytics import metric_formatter as fmt
from api.analytics.scope_domain import can_view_child_detail


def _user(role):
    return types.SimpleNamespace(role=role, id=1, email="u@x")


def test_only_admin_can_view_child_detail():
    assert can_view_child_detail(_user(models.UserRole.ADMIN)) is True
    for role in (models.UserRole.MANAGER, models.UserRole.SUPERVISOR):
        assert can_view_child_detail(_user(role)) is False


def test_child_metrics_suppressed_shape():
    """When unauthorized, child metrics keep their shape but expose no values."""
    from schemas.chart_dto import MetricResponse, ChartConfig, ChartDataset
    m = MetricResponse(
        metric="child_engagement_score", value=77.0,
        chart=ChartConfig(type="bar", labels=["x"],
                          datasets=[ChartDataset(label={"en": "x", "ar": "x"}, data=[77.0])]),
        locale="en",
    )
    fmt.annotate_metric(m, suppressed=True)
    assert m.data_state == fmt.SUPPRESSED
    assert m.display["en"] == fmt.placeholder(fmt.SUPPRESSED)


def test_parent_role_is_not_authorized_if_present():
    parent = getattr(models.UserRole, "PARENT", None)
    if parent is not None:
        assert can_view_child_detail(_user(parent)) is False
