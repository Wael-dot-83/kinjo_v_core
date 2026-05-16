from datetime import date, timedelta

import models


def _seed_active_enrollment(test_db, sample_kindergarten, sample_class, sample_child):
    enrollment = models.EnrollmentApplication(
        child_id=sample_child.id,
        kindergarten_id=sample_kindergarten.id,
        class_id=sample_class.id,
        status=models.EnrollmentStatus.ACTIVE,
        enrollment_start_date=date.today() - timedelta(days=20),
    )
    test_db.add(enrollment)
    test_db.commit()
    return enrollment


def test_admin_classification_filters_smoke(client, auth_headers_admin):
    response = client.get("/api/admin/classification/filters", headers=auth_headers_admin)
    assert response.status_code == 200
    data = response.json()
    assert "levels" in data
    assert "size_modes" in data
    assert "countries" in data


def test_admin_kindergarten_leaderboard_smoke(client, auth_headers_admin):
    params = {
        "period_start": "2026-01-01",
        "period_end": "2026-01-31",
        "level": "NETWORK",
        "size_mode": "ENROLLMENT",
    }
    response = client.get("/api/admin/classification/kindergartens", headers=auth_headers_admin, params=params)
    assert response.status_code == 200
    data = response.json()
    assert "rows" in data
    assert isinstance(data["rows"], list)


def test_manager_cannot_access_admin_classification(client, auth_headers_manager):
    response = client.get("/api/admin/classification/kindergartens", headers=auth_headers_manager)
    assert response.status_code == 403


def test_manager_benchmarking_summary_smoke(client, auth_headers_manager):
    params = {
        "period_start": "2026-01-01",
        "period_end": "2026-01-31",
        "size_mode": "ENROLLMENT",
    }
    response = client.get("/api/manager/benchmarking/summary", headers=auth_headers_manager, params=params)
    assert response.status_code == 200
    data = response.json()
    assert "manager_id" in data
    assert "anonymized_peers" in data
    assert isinstance(data["anonymized_peers"], list)
    if data["anonymized_peers"]:
        assert "peer_code" in data["anonymized_peers"][0]
        assert "display_name" not in data["anonymized_peers"][0]


def test_supervisor_performance_summary_smoke(client, auth_headers_supervisor):
    params = {
        "period_start": "2026-01-01",
        "period_end": "2026-01-31",
    }
    response = client.get("/api/supervisor/performance/summary", headers=auth_headers_supervisor, params=params)
    assert response.status_code == 200
    data = response.json()
    assert "supervisor_id" in data
    assert "aspects" in data


def test_parent_quality_band_smoke(
    client,
    test_db,
    auth_headers_parent,
    sample_kindergarten,
    sample_class,
    sample_child,
):
    _seed_active_enrollment(test_db, sample_kindergarten, sample_class, sample_child)
    params = {
        "period_start": "2026-01-01",
        "period_end": "2026-01-31",
    }
    response = client.get("/api/parent/kindergarten/quality-band", headers=auth_headers_parent, params=params)
    assert response.status_code == 200
    data = response.json()
    assert data["kindergarten_id"] == sample_kindergarten.id
    assert "band_label" in data


def test_admin_can_load_detail_for_kindergarten(client, auth_headers_admin, sample_kindergarten):
    params = {
        "entity_type": "KINDERGARTEN",
        "entity_id": sample_kindergarten.id,
        "period_start": "2026-01-01",
        "period_end": "2026-01-31",
    }
    response = client.get("/api/admin/classification/detail", headers=auth_headers_admin, params=params)
    assert response.status_code == 200
    data = response.json()
    assert data["entity_type"] == "KINDERGARTEN"
    assert data["entity_id"] == sample_kindergarten.id
    assert "trend_points" in data
