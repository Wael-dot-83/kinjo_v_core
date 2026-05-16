"""Unit tests for analytics domain forecasting and anomaly detection."""
from datetime import date, timedelta

from analytics_domain import SeriesPoint, build_forecast, z_score_anomalies


def test_build_forecast_generates_points():
    start = date(2026, 1, 1)
    series = [SeriesPoint(date=start + timedelta(days=i), value=10 + i) for i in range(10)]
    forecast_points, confidence, meta = build_forecast(series, horizon_days=5)

    assert len(forecast_points) == 5
    assert len(confidence["lower"]) == 5
    assert len(confidence["upper"]) == 5
    assert meta["model_version"] == "linear_v1"


def test_z_score_anomalies_detects_outlier():
    start = date(2026, 1, 1)
    series = [SeriesPoint(date=start + timedelta(days=i), value=10) for i in range(9)]
    series.append(SeriesPoint(date=start + timedelta(days=9), value=30))

    anomalies = z_score_anomalies(series)
    assert len(anomalies) >= 1
    point, score, severity = anomalies[0]
    assert point.value == 30
    assert abs(score) >= 2.0
