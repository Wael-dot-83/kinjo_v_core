"""Integration tests for analytics enhancement endpoints."""
from datetime import date, timedelta, datetime

import models
from auth import get_password_hash


def _login_admin(client, admin_user):
    response = client.post("/token", data={"username": admin_user.username, "password": "Admin123!"})
    assert response.status_code == 200
    return response.json()["access_token"]


def test_predictive_endpoint(client, admin_user):
    token = _login_admin(client, admin_user)
    payload = {
        "scope_type": "NETWORK",
        "scope_id": None,
        "start_date": (date.today() - timedelta(days=7)).isoformat(),
        "end_date": date.today().isoformat(),
        "horizon_days": 7,
    }
    response = client.post(
        "/api/analytics/predict/attendance",
        headers={"Authorization": f"Bearer {token}"},
        json=payload,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["metric"] == "attendance"
    assert "forecast_points" in data


def test_anomalies_endpoint(client, admin_user, sample_kindergarten, sample_class, sample_child, parent_enrollment, test_db):
    token = _login_admin(client, admin_user)
    start_date = date.today() - timedelta(days=7)
    for i in range(7):
        test_db.add(models.AttendanceLog(
            child_id=sample_child.id,
            class_id=sample_class.id,
            date=start_date + timedelta(days=i),
            status=models.AttendanceStatus.PRESENT,
            recorded_by=admin_user.id,
        ))
    test_db.commit()

    response = client.get(
        f"/api/analytics/anomalies?scope_type=NETWORK&metric_type=attendance&from={start_date.isoformat()}&to={date.today().isoformat()}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "anomalies" in data


def test_alert_thresholds(client, admin_user):
    token = _login_admin(client, admin_user)
    response = client.put(
        "/api/analytics/alerts/thresholds",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "metric_type": "attendance_rate",
            "scope_type": "NETWORK",
            "operator": "LT",
            "threshold_value": 99,
            "window_days": 7,
            "severity": "MEDIUM",
            "is_active": True,
        },
    )
    assert response.status_code == 200

    alert_response = client.get(
        "/api/analytics/alerts",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert alert_response.status_code == 200
    assert "alerts" in alert_response.json()


def test_targets_endpoint(client, admin_user):
    token = _login_admin(client, admin_user)
    response = client.put(
        "/api/analytics/targets",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "metric_type": "attendance_rate",
            "scope_type": "NETWORK",
            "scope_id": None,
            "target_value": 90,
            "effective_date": date.today().isoformat(),
        },
    )
    assert response.status_code == 200

    get_response = client.get(
        "/api/analytics/targets",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert get_response.status_code == 200
    assert len(get_response.json()["targets"]) >= 1


def test_benchmarks_endpoint(client, admin_user, sample_kindergarten, test_db):
    token = _login_admin(client, admin_user)
    benchmark = models.BenchmarkData(
        metric_type="attendance_rate",
        scope_type="KINDERGARTEN",
        scope_id=str(sample_kindergarten.id),
        comparison_group="NETWORK",
        period_start=date.today() - timedelta(days=30),
        period_end=date.today(),
        value=88.0,
    )
    test_db.add(benchmark)
    test_db.commit()

    response = client.get(
        f"/api/analytics/benchmarks/{sample_kindergarten.id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "benchmarks" in data
    assert len(data["benchmarks"]) == 1


def test_recommendations_endpoint(client, admin_user, sample_kindergarten):
    token = _login_admin(client, admin_user)
    response = client.get(
        f"/api/analytics/recommendations/{sample_kindergarten.id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "recommendations" in data


def test_action_plan_progress(client, admin_user, sample_kindergarten):
    token = _login_admin(client, admin_user)
    create_response = client.post(
        "/api/analytics/actions",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "kindergarten_id": sample_kindergarten.id,
            "title": "رفع نسبة الحضور",
            "description": "خطة تحسين الحضور",
        },
    )
    assert create_response.status_code == 200
    action_id = create_response.json()["id"]

    progress_response = client.get(
        f"/api/analytics/actions/{action_id}/progress",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert progress_response.status_code == 200
    assert progress_response.json()["progress_percent"] == 0


def test_data_quality_report(client, admin_user):
    token = _login_admin(client, admin_user)
    response = client.get(
        "/api/analytics/data-quality",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200

    report_response = client.get(
        "/api/analytics/data-quality/report",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert report_response.status_code == 200
    assert "reports" in report_response.json()
