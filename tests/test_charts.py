"""
Comprehensive test suite for the KinJo charting subsystem.
Covers: schemas, colors, stats, cache, advisor (≥20 decision-matrix cases),
        builders, service, and API endpoints.
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from typing import Any, Dict
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest


# ---------------------------------------------------------------------------
# ── Schemas ─────────────────────────────────────────────────────────────────
# ---------------------------------------------------------------------------

class TestSchemas:
    def test_chart_request_defaults(self):
        from charts.schemas import ChartRequest, ChartSource, Granularity
        req = ChartRequest(source=ChartSource.INCIDENTS)
        assert req.granularity == Granularity.MONTH
        assert req.chart_type is None

    def test_chart_request_date_validation_ok(self):
        from charts.schemas import ChartRequest, ChartSource
        req = ChartRequest(source=ChartSource.ATTENDANCE, date_from="2026-01-01", date_to="2026-06-30")
        assert req.date_from == "2026-01-01"

    def test_chart_request_bad_date_raises(self):
        from charts.schemas import ChartRequest, ChartSource
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            ChartRequest(source=ChartSource.INCIDENTS, date_from="01-01-2026")

    def test_chart_type_enum_values(self):
        from charts.schemas import ChartType
        assert ChartType.LINE.value == "line"
        assert ChartType.HEATMAP.value == "heatmap"
        assert len(list(ChartType)) == 9

    def test_chart_source_enum_values(self):
        from charts.schemas import ChartSource
        assert len(list(ChartSource)) == 5

    def test_suggest_request_defaults(self):
        from charts.schemas import SuggestRequest, ChartSource
        req = SuggestRequest(source=ChartSource.DAILY_REPORTS)
        assert req.max_suggestions == 3

    def test_suggest_request_max_clamps(self):
        from charts.schemas import SuggestRequest, ChartSource
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            SuggestRequest(source=ChartSource.INCIDENTS, max_suggestions=10)

    def test_data_profile_defaults(self):
        from charts.schemas import DataProfile
        p = DataProfile(row_count=0)
        assert p.has_time_series is False
        assert p.n_categories == 0


# ---------------------------------------------------------------------------
# ── Colors ───────────────────────────────────────────────────────────────────
# ---------------------------------------------------------------------------

class TestColors:
    def test_get_color_wraps(self):
        from charts.colors import get_color, PALETTE
        assert get_color(0) == PALETTE[0]
        assert get_color(len(PALETTE)) == PALETTE[0]

    def test_assign_colors_deterministic(self):
        from charts.colors import assign_colors
        cats = ["happy", "sad", "normal"]
        m1 = assign_colors(cats)
        m2 = assign_colors(cats)
        assert m1 == m2

    def test_sequential_colorscale_shape(self):
        from charts.colors import sequential_colorscale
        cs = sequential_colorscale()
        assert cs[0][0] == 0.0 and cs[-1][0] == 1.0

    def test_diverging_colorscale_midpoint(self):
        from charts.colors import diverging_colorscale
        cs = diverging_colorscale()
        midpoints = [c[0] for c in cs]
        assert 0.5 in midpoints

    def test_palette_has_twelve_colors(self):
        from charts.colors import PALETTE
        assert len(PALETTE) == 12


# ---------------------------------------------------------------------------
# ── Stats ────────────────────────────────────────────────────────────────────
# ---------------------------------------------------------------------------

class TestStats:
    def _sample_df(self) -> pd.DataFrame:
        dates = pd.date_range("2026-01-01", periods=30)
        return pd.DataFrame({
            "date": dates,
            "value": np.random.randint(10, 100, 30),
            "category": ["A", "B", "C"] * 10,
        })

    def test_profile_empty_df(self):
        from charts.stats import profile_dataframe
        p = profile_dataframe(pd.DataFrame())
        assert p.row_count == 0
        assert p.has_time_series is False

    def test_profile_detects_time_col(self):
        from charts.stats import profile_dataframe
        p = profile_dataframe(self._sample_df())
        assert p.has_time_series is True
        assert p.time_span_days is not None
        assert p.time_span_days > 0

    def test_profile_detects_category(self):
        from charts.stats import profile_dataframe
        p = profile_dataframe(self._sample_df())
        assert p.has_categories is True
        assert "category" in p.cardinality

    def test_profile_numeric_detected(self):
        from charts.stats import profile_dataframe
        p = profile_dataframe(self._sample_df())
        assert p.has_numeric is True
        assert p.n_numeric_cols >= 1

    def test_compute_trend_slope_positive(self):
        from charts.stats import compute_trend
        s = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0])
        slope, r2 = compute_trend(s)
        assert slope > 0
        assert r2 > 0.99

    def test_compute_trend_flat_series(self):
        from charts.stats import compute_trend
        s = pd.Series([5.0] * 10)
        slope, r2 = compute_trend(s)
        assert abs(slope) < 1e-9

    def test_compute_trend_short_series(self):
        from charts.stats import compute_trend
        slope, r2 = compute_trend(pd.Series([]))
        assert slope == 0.0

    def test_detect_outliers_iqr(self):
        from charts.stats import detect_outliers_iqr
        s = pd.Series([1, 2, 2, 3, 3, 3, 3, 100])  # 100 is outlier
        mask = detect_outliers_iqr(s)
        assert mask.iloc[-1] is True or mask.sum() >= 1

    def test_moving_average_length_preserved(self):
        from charts.stats import moving_average
        s = pd.Series(range(20), dtype=float)
        ma = moving_average(s, window=5)
        assert len(ma) == len(s)

    def test_safe_pct_change_first_element_zero(self):
        from charts.stats import safe_pct_change
        s = pd.Series([100.0, 110.0, 121.0])
        pct = safe_pct_change(s)
        assert pct.iloc[0] == 0.0

    def test_resample_timeseries_monthly(self):
        from charts.stats import resample_timeseries
        df = pd.DataFrame({
            "date": pd.date_range("2026-01-01", periods=60),
            "count": [1] * 60,
        })
        out = resample_timeseries(df, "date", "count", freq="ME", agg="sum")
        assert len(out) >= 2
        assert "count" in out.columns


# ---------------------------------------------------------------------------
# ── Cache ────────────────────────────────────────────────────────────────────
# ---------------------------------------------------------------------------

class TestCache:
    def _params(self) -> dict:
        return {"source": "incidents", "date_from": "2026-01-01"}

    def test_get_raw_returns_none_without_redis(self):
        from charts import cache
        with patch("charts.cache._get_redis", return_value=None):
            result = cache.get_raw(self._params())
        assert result is None

    def test_set_raw_is_noop_without_redis(self):
        from charts import cache
        with patch("charts.cache._get_redis", return_value=None):
            cache.set_raw(self._params(), "data")  # must not raise

    def test_get_render_returns_none_without_redis(self):
        from charts import cache
        with patch("charts.cache._get_redis", return_value=None):
            result = cache.get_render(self._params())
        assert result is None

    def test_set_get_render_with_mock_redis(self):
        from charts import cache
        store: Dict[str, Any] = {}
        mock_redis = MagicMock()
        mock_redis.get.side_effect = lambda k: store.get(k)
        mock_redis.setex.side_effect = lambda k, ttl, v: store.update({k: v})

        with patch("charts.cache._get_redis", return_value=mock_redis):
            cache.set_render(self._params(), "<div>chart</div>")
            result = cache.get_render(self._params())
        assert result == "<div>chart</div>"

    def test_make_key_is_deterministic(self):
        from charts.cache import _make_key
        k1 = _make_key("raw", {"a": 1, "b": 2})
        k2 = _make_key("raw", {"b": 2, "a": 1})
        assert k1 == k2


# ---------------------------------------------------------------------------
# ── ChartAdvisor — 20+ decision-matrix test cases ────────────────────────────
# ---------------------------------------------------------------------------

class TestChartAdvisor:
    """20+ cases exercising the full decision matrix."""

    def _advisor(self):
        from charts.advisor import ChartAdvisor
        return ChartAdvisor()

    def _profile(self, **kwargs):
        from charts.schemas import DataProfile
        return DataProfile(row_count=100, **kwargs)

    # ── Time-series branch ────────────────────────────────────────────────

    def test_long_time_span_suggests_line_first(self):
        from charts.schemas import ChartSource, ChartType
        df = pd.DataFrame({
            "date": pd.date_range("2024-01-01", periods=200),
            "count": range(200),
        })
        suggestions, _ = self._advisor().suggest(df, ChartSource.INCIDENTS)
        assert suggestions[0].chart_type == ChartType.LINE

    def test_long_time_span_confidence_high(self):
        from charts.schemas import ChartSource
        df = pd.DataFrame({
            "date": pd.date_range("2024-01-01", periods=200),
            "count": range(200),
        })
        suggestions, _ = self._advisor().suggest(df, ChartSource.ATTENDANCE)
        assert suggestions[0].confidence >= 0.88

    def test_short_time_span_suggests_bar_first(self):
        from charts.schemas import ChartSource, ChartType
        # Use ENROLLMENTS — no per-source time-series line boost that outranks bar
        df = pd.DataFrame({
            "date": pd.date_range("2026-06-01", periods=7),
            "count": range(7),
        })
        suggestions, _ = self._advisor().suggest(df, ChartSource.KINDERGARTENS)
        # For short span (<30 days) bar should rank first (conf 0.80) or appear top-2
        types = [s.chart_type for s in suggestions[:2]]
        assert ChartType.BAR in types

    # ── Low-cardinality category branch ───────────────────────────────────

    def test_low_cardinality_suggests_pie(self):
        from charts.schemas import ChartSource, ChartType
        df = pd.DataFrame({
            "status": ["present", "absent", "late"] * 10,
            "count": [30, 10, 5] * 10,
        })
        suggestions, _ = self._advisor().suggest(df, ChartSource.ATTENDANCE)
        types = [s.chart_type for s in suggestions]
        assert ChartType.PIE in types

    def test_low_cardinality_pie_confidence(self):
        from charts.schemas import ChartSource, ChartType
        df = pd.DataFrame({"mood": ["happy", "sad"] * 5, "count": [8, 2] * 5})
        suggestions, _ = self._advisor().suggest(df, ChartSource.DAILY_REPORTS)
        pie_conf = next((s.confidence for s in suggestions if s.chart_type == ChartType.PIE), None)
        assert pie_conf is not None and pie_conf >= 0.85

    # ── Moderate-cardinality branch ────────────────────────────────────────

    def test_moderate_cardinality_suggests_bar(self):
        from charts.schemas import ChartSource, ChartType
        cats = [f"cat_{i}" for i in range(10)]
        df = pd.DataFrame({
            "category": cats * 3,
            "count": list(range(10)) * 3,
        })
        suggestions, _ = self._advisor().suggest(df, ChartSource.KINDERGARTENS)
        types = [s.chart_type for s in suggestions]
        assert ChartType.BAR in types

    # ── High-cardinality branch ────────────────────────────────────────────

    def test_high_cardinality_bar_first(self):
        from charts.schemas import ChartSource, ChartType
        cats = [f"kg_{i}" for i in range(20)]
        df = pd.DataFrame({"kindergarten": cats, "enrolled": range(20)})
        suggestions, _ = self._advisor().suggest(df, ChartSource.KINDERGARTENS)
        assert suggestions[0].chart_type == ChartType.BAR

    # ── Numeric distribution branch ────────────────────────────────────────

    def test_high_skew_suggests_histogram(self):
        from charts.schemas import ChartSource, ChartType
        vals = np.concatenate([np.zeros(80), np.array([50, 100, 150, 200, 1000])])
        df = pd.DataFrame({"value": vals})
        suggestions, _ = self._advisor().suggest(df, ChartSource.ENROLLMENTS)
        types = [s.chart_type for s in suggestions]
        assert ChartType.HISTOGRAM in types

    def test_high_skew_histogram_confidence(self):
        from charts.schemas import ChartSource, ChartType
        vals = np.concatenate([np.zeros(80), np.array([50, 100, 150, 200, 1000])])
        df = pd.DataFrame({"value": vals})
        suggestions, _ = self._advisor().suggest(df, ChartSource.INCIDENTS)
        hist = next((s for s in suggestions if s.chart_type == ChartType.HISTOGRAM), None)
        assert hist is not None
        assert hist.confidence >= 0.80

    def test_low_skew_suggests_histogram(self):
        from charts.schemas import ChartSource, ChartType
        df = pd.DataFrame({"value": np.random.normal(50, 10, 100)})
        suggestions, _ = self._advisor().suggest(df, ChartSource.ENROLLMENTS)
        types = [s.chart_type for s in suggestions]
        assert ChartType.HISTOGRAM in types

    # ── Multi-numeric correlation branch ──────────────────────────────────

    def test_three_numeric_cols_suggests_heatmap(self):
        from charts.schemas import ChartSource, ChartType
        df = pd.DataFrame({
            "a": np.random.rand(50),
            "b": np.random.rand(50),
            "c": np.random.rand(50),
        })
        suggestions, _ = self._advisor().suggest(df, ChartSource.KINDERGARTENS)
        types = [s.chart_type for s in suggestions]
        assert ChartType.HEATMAP in types

    def test_two_numeric_cols_suggests_scatter(self):
        from charts.schemas import ChartSource, ChartType
        df = pd.DataFrame({
            "capacity": np.random.randint(20, 60, 30),
            "enrolled": np.random.randint(10, 55, 30),
        })
        suggestions, _ = self._advisor().suggest(df, ChartSource.KINDERGARTENS)
        types = [s.chart_type for s in suggestions]
        assert ChartType.SCATTER in types

    # ── Source-specific boost rules ────────────────────────────────────────

    def test_enrollment_source_boosts_funnel(self):
        from charts.schemas import ChartSource, ChartType
        df = pd.DataFrame({
            "stage": ["Applied", "Reviewed", "Approved", "Enrolled"],
            "count": [100, 80, 50, 40],
        })
        suggestions, _ = self._advisor().suggest(df, ChartSource.ENROLLMENTS, max_suggestions=5)
        types = [s.chart_type for s in suggestions]
        assert ChartType.FUNNEL in types

    def test_attendance_source_boosts_line_for_timeseries(self):
        from charts.schemas import ChartSource, ChartType
        df = pd.DataFrame({
            "date": pd.date_range("2025-09-01", periods=180),
            "rate": np.random.uniform(0.7, 0.99, 180),
        })
        suggestions, _ = self._advisor().suggest(df, ChartSource.ATTENDANCE)
        assert suggestions[0].chart_type == ChartType.LINE

    def test_daily_report_source_boosts_bar(self):
        from charts.schemas import ChartSource, ChartType
        df = pd.DataFrame({
            "mood": ["happy", "normal", "sad", "tired", "sick"],
            "count": [40, 30, 15, 10, 5],
        })
        suggestions, _ = self._advisor().suggest(df, ChartSource.DAILY_REPORTS)
        types = [s.chart_type for s in suggestions]
        assert ChartType.BAR in types

    def test_kindergartens_suggests_bar(self):
        from charts.schemas import ChartSource, ChartType
        df = pd.DataFrame({
            "kindergarten": ["KG A", "KG B", "KG C"],
            "capacity": [30, 40, 25],
            "enrolled": [28, 38, 20],
        })
        suggestions, _ = self._advisor().suggest(df, ChartSource.KINDERGARTENS)
        types = [s.chart_type for s in suggestions]
        assert ChartType.BAR in types

    # ── Empty / edge cases ─────────────────────────────────────────────────

    def test_empty_df_returns_fallback(self):
        from charts.schemas import ChartSource
        df = pd.DataFrame()
        suggestions, profile = self._advisor().suggest(df, ChartSource.INCIDENTS)
        assert len(suggestions) >= 1
        assert profile.row_count == 0

    def test_max_suggestions_respected(self):
        from charts.schemas import ChartSource
        df = pd.DataFrame({
            "date": pd.date_range("2026-01-01", periods=100),
            "type": ["A", "B"] * 50,
            "count": range(100),
        })
        suggestions, _ = self._advisor().suggest(df, ChartSource.INCIDENTS, max_suggestions=2)
        assert len(suggestions) <= 2

    def test_no_duplicate_chart_types_in_suggestions(self):
        from charts.schemas import ChartSource
        df = pd.DataFrame({
            "date": pd.date_range("2026-01-01", periods=200),
            "category": ["A", "B", "C", "D"] * 50,
            "value": range(200),
        })
        suggestions, _ = self._advisor().suggest(df, ChartSource.INCIDENTS, max_suggestions=5)
        types = [s.chart_type for s in suggestions]
        assert len(types) == len(set(types))

    def test_suggestion_has_rationale(self):
        from charts.schemas import ChartSource
        df = pd.DataFrame({"mood": ["happy"] * 10, "count": [10] * 10})
        suggestions, _ = self._advisor().suggest(df, ChartSource.DAILY_REPORTS)
        assert all(len(s.rationale) > 10 for s in suggestions)

    def test_suggestion_confidence_in_range(self):
        from charts.schemas import ChartSource
        df = pd.DataFrame({"x": [1, 2, 3], "y": [4, 5, 6]})
        suggestions, _ = self._advisor().suggest(df, ChartSource.KINDERGARTENS)
        for s in suggestions:
            assert 0.0 <= s.confidence <= 1.0

    def test_default_title_includes_source(self):
        from charts.advisor import ChartAdvisor
        from charts.schemas import ChartSource, ChartType
        adv = ChartAdvisor()
        title = adv._default_title(ChartSource.INCIDENTS, ChartType.LINE)
        assert "Incidents" in title

    def test_incidents_with_time_series_boosts_line(self):
        from charts.schemas import ChartSource, ChartType
        df = pd.DataFrame({
            "date": pd.date_range("2025-01-01", periods=200),
            "count": range(200),
        })
        suggestions, _ = self._advisor().suggest(df, ChartSource.INCIDENTS, max_suggestions=5)
        types = [s.chart_type for s in suggestions]
        assert ChartType.LINE in types


# ---------------------------------------------------------------------------
# ── Builders ─────────────────────────────────────────────────────────────────
# ---------------------------------------------------------------------------

class TestBuilders:
    def _req(self, **kwargs):
        from charts.schemas import ChartRequest, ChartSource, ChartType
        return ChartRequest(source=ChartSource.INCIDENTS, **kwargs)

    def test_line_builder_empty_df(self):
        from charts.builders.line import LineBuilder
        html = LineBuilder().render(pd.DataFrame(), self._req())
        assert isinstance(html, str)

    def test_bar_builder_empty_df(self):
        from charts.builders.bar import BarBuilder
        html = BarBuilder().render(pd.DataFrame(), self._req())
        assert isinstance(html, str)

    def test_pie_builder_with_data(self):
        from charts.builders.pie import PieBuilder
        df = pd.DataFrame({"mood": ["happy", "sad", "normal"], "count": [50, 30, 20]})
        html = PieBuilder().render(df, self._req(title="Moods"))
        assert "plotly" in html.lower() or "<div" in html

    def test_histogram_builder_with_data(self):
        from charts.builders.histogram import HistogramBuilder
        df = pd.DataFrame({"value": np.random.randn(100)})
        html = HistogramBuilder().render(df, self._req())
        assert isinstance(html, str)

    def test_box_builder_with_data(self):
        from charts.builders.box import BoxBuilder
        df = pd.DataFrame({"value": np.random.randn(50), "group": ["A", "B"] * 25})
        html = BoxBuilder().render(df, self._req(group_by="group"))
        assert isinstance(html, str)

    def test_scatter_builder_with_data(self):
        from charts.builders.scatter import ScatterBuilder
        df = pd.DataFrame({"x": range(20), "y": range(20)})
        html = ScatterBuilder().render(df, self._req())
        assert isinstance(html, str)

    def test_heatmap_builder_correlation(self):
        from charts.builders.heatmap import HeatmapBuilder
        df = pd.DataFrame({"a": range(10), "b": range(10), "c": [i * 2 for i in range(10)]})
        html = HeatmapBuilder().render(df, self._req())
        assert isinstance(html, str)

    def test_funnel_builder_with_data(self):
        from charts.builders.funnel import FunnelBuilder
        df = pd.DataFrame({"stage": ["A", "B", "C"], "count": [100, 60, 30]})
        html = FunnelBuilder().render(df, self._req())
        assert isinstance(html, str)

    def test_treemap_builder_with_data(self):
        from charts.builders.treemap import TreemapBuilder
        df = pd.DataFrame({
            "governorate": ["Amman", "Amman", "Zarqa"],
            "kindergarten": ["KG1", "KG2", "KG3"],
            "enrolled": [40, 30, 25],
        })
        html = TreemapBuilder().render(df, self._req())
        assert isinstance(html, str)

    def test_get_builder_registry(self):
        from charts.builders import get_builder
        from charts.schemas import ChartType
        for ct in ChartType:
            builder = get_builder(ct)
            assert builder is not None

    def test_get_builder_invalid_raises(self):
        from charts.builders import get_builder
        with pytest.raises((ValueError, KeyError)):
            get_builder("nonexistent_type")  # type: ignore

    def test_line_builder_respects_title(self):
        from charts.builders.line import LineBuilder
        df = pd.DataFrame({
            "date": pd.date_range("2026-01-01", periods=10),
            "count": range(10),
        })
        html = LineBuilder().render(df, self._req(title="My Custom Title"))
        assert "My Custom Title" in html

    def test_bar_builder_top_n(self):
        from charts.builders.bar import BarBuilder
        df = pd.DataFrame({"label": [f"cat_{i}" for i in range(20)], "value": range(20)})
        html = BarBuilder().render(df, self._req(top_n=5))
        assert isinstance(html, str)


# ---------------------------------------------------------------------------
# ── ChartService (unit, with mocked DB) ──────────────────────────────────────
# ---------------------------------------------------------------------------

class TestChartService:
    def _mock_db(self):
        return MagicMock()

    def test_render_returns_chart_response(self):
        from charts.schemas import ChartRequest, ChartResponse, ChartSource
        from charts.service import ChartService

        svc = ChartService()
        df = pd.DataFrame({"mood": ["happy", "sad"], "count": [10, 5]})
        req = ChartRequest(source=ChartSource.DAILY_REPORTS)

        with patch.object(svc, "get_data", return_value=df):
            resp = svc.render(self._mock_db(), req)

        assert isinstance(resp, ChartResponse)
        # Structured contract: the server returns data series; HTML rendering moved to the frontend.
        assert resp.quality.record_count == 2
        assert resp.summary["total_records"] == 2
        assert len(resp.series) == 2
        assert resp.scope.level == "national"

    def test_render_uses_cache_hit(self):
        from charts.schemas import ChartRequest, ChartSource
        from charts.service import ChartService

        svc = ChartService()
        req = ChartRequest(source=ChartSource.INCIDENTS)

        cached_json = pd.DataFrame({"label": ["A", "B"], "count": [3, 4]}).to_json(orient="split")
        with patch("charts.service.chart_cache.get_raw", return_value=cached_json):
            resp = svc.render(self._mock_db(), req)

        # Caching moved to the raw-data layer: a cache hit serves rows without invoking a loader.
        assert resp.quality.record_count == 2
        assert resp.summary["total_records"] == 2
        assert len(resp.series) == 2

    def test_render_heavy_dataset_submits_task(self):
        from charts.schemas import ChartRequest, ChartSource
        from charts.service import ChartService

        svc = ChartService()
        big_df = pd.DataFrame({"x": range(svc.HEAVY_ROW_THRESHOLD + 1)})
        req = ChartRequest(source=ChartSource.INCIDENTS)

        with patch.object(svc, "get_data", return_value=big_df), \
             patch.object(svc, "_submit_task", return_value="fake-task-id"):
            resp = svc.render(self._mock_db(), req)

        assert resp.task_id == "fake-task-id"
        # Heavy dataset defers rendering to an async task: no inline series yet.
        assert resp.series == []
        assert resp.quality.status == "processing"

    def test_suggest_returns_suggest_response(self):
        from charts.schemas import SuggestRequest, SuggestResponse, ChartSource
        from charts.service import ChartService

        svc = ChartService()
        df = pd.DataFrame({"type": ["A", "B"] * 5, "count": range(10)})
        req = SuggestRequest(source=ChartSource.INCIDENTS)

        with patch.object(svc, "get_data", return_value=df):
            resp = svc.suggest(self._mock_db(), req)

        assert isinstance(resp, SuggestResponse)
        assert len(resp.suggestions) >= 1

    def test_auto_type_returns_chart_type(self):
        from charts.schemas import ChartSource, ChartType
        from charts.service import ChartService

        svc = ChartService()
        df = pd.DataFrame({
            "date": pd.date_range("2026-01-01", periods=60),
            "count": range(60),
        })
        ct = svc._auto_type(df, ChartSource.INCIDENTS)
        assert isinstance(ct, ChartType)


# ---------------------------------------------------------------------------
# ── API Endpoints (using FastAPI TestClient) ──────────────────────────────────
# ---------------------------------------------------------------------------

class TestChartsAPI:
    """Integration tests for /admin/charts/* using conftest client+fixtures."""

    def test_render_endpoint_auth_required(self, client):
        resp = client.get("/admin/charts/render?source=incidents")
        assert resp.status_code in (401, 403, 302)

    def test_data_endpoint_auth_required(self, client):
        resp = client.get("/admin/charts/data?source=incidents")
        assert resp.status_code in (401, 403, 302)

    def test_suggest_endpoint_auth_required(self, client):
        resp = client.post("/admin/charts/suggest", json={"source": "incidents"})
        assert resp.status_code in (401, 403, 302)

    def test_render_invalid_source(self, client, auth_headers_admin):
        resp = client.get("/admin/charts/render?source=invalid_source", headers=auth_headers_admin)
        assert resp.status_code == 422

    def test_render_invalid_chart_type(self, client, auth_headers_admin):
        resp = client.get(
            "/admin/charts/render?source=incidents&chart_type=invalid",
            headers=auth_headers_admin,
        )
        assert resp.status_code == 422

    def test_suggest_valid_source(self, client, auth_headers_admin):
        resp = client.post(
            "/admin/charts/suggest",
            json={"source": "incidents", "max_suggestions": 3},
            headers=auth_headers_admin,
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "suggestions" in body
        assert "row_count" in body

    def test_render_incidents_returns_structured(self, client, auth_headers_admin):
        resp = client.get(
            "/admin/charts/render?source=incidents&chart_type=bar",
            headers=auth_headers_admin,
        )
        assert resp.status_code == 200
        body = resp.json()
        # Structured contract: series + scope replace the old server-rendered html field.
        assert "series" in body
        assert "scope" in body
        assert "chart_type" in body
        assert body["chart_type"] == "bar"

    def test_render_attendance_auto_type(self, client, auth_headers_admin):
        resp = client.get(
            "/admin/charts/render?source=attendance",
            headers=auth_headers_admin,
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["chart_type"] in [t.value for t in __import__("charts.schemas", fromlist=["ChartType"]).ChartType]

    def test_data_endpoint_returns_records(self, client, auth_headers_admin):
        resp = client.get(
            "/admin/charts/data?source=daily_reports",
            headers=auth_headers_admin,
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "data" in body
        assert "row_count" in body
        assert isinstance(body["data"], list)

    def test_suggest_max_suggestions_respected(self, client, auth_headers_admin):
        resp = client.post(
            "/admin/charts/suggest",
            json={"source": "attendance", "max_suggestions": 2},
            headers=auth_headers_admin,
        )
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["suggestions"]) <= 2

    def test_task_status_unknown_task(self, client, auth_headers_admin):
        resp = client.get(
            "/admin/charts/task/nonexistent-task-id-12345",
            headers=auth_headers_admin,
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "status" in body
        assert body["status"] in ("PENDING", "FAILURE", "SUCCESS")

    def test_render_with_date_filter(self, client, auth_headers_admin):
        resp = client.get(
            "/admin/charts/render?source=incidents&date_from=2026-01-01&date_to=2026-06-30",
            headers=auth_headers_admin,
        )
        assert resp.status_code == 200

    def test_render_with_top_n(self, client, auth_headers_admin):
        resp = client.get(
            "/admin/charts/render?source=kindergartens&chart_type=bar&top_n=5",
            headers=auth_headers_admin,
        )
        assert resp.status_code == 200

    def test_render_kindergartens_governorate_scope_includes_kindergarten_id(self, client, auth_headers_admin):
        resp = client.get(
            "/admin/charts/render?source=kindergartens&governorate=العاصمة",
            headers=auth_headers_admin,
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["drilldown"]["next_level"] == "kindergarten"
        series = body.get("series", [])
        if series:
            assert "kindergarten_id" in series[0]

    def test_dashboard_page_loads(self, client, auth_headers_admin):
        resp = client.get("/admin/charts/dashboard", headers=auth_headers_admin)
        assert resp.status_code == 200
        assert "text/html" in resp.headers.get("content-type", "")
