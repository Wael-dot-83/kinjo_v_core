import pytest


def test_kpi_dashboard_admin_view(client, test_db, admin_user, auth_headers_admin, sample_kindergarten):
    params = {
        'period_start': '2026-01-01',
        'period_end': '2026-01-31'
    }
    response = client.get('/api/kpi/dashboard-data', headers=auth_headers_admin, params=params)
    assert response.status_code == 200
    data = response.json()
    assert data['kindergarten_id'] == sample_kindergarten.id
    assert 'overall_gcei' in data
    assert isinstance(data['alerts'], list)


def test_kpi_dashboard_manager_scoped(client, test_db, manager_user, auth_headers_manager):
    params = {
        'period_start': '2026-01-01',
        'period_end': '2026-01-10'
    }
    response = client.get('/api/kpi/dashboard-data', headers=auth_headers_manager, params=params)
    assert response.status_code == 200
    data = response.json()
    assert data['kindergarten_id'] == manager_user.kindergarten_id
    assert data['governorate'] is not None
    assert data['overall_gcei']['value'] is not None


def test_kpi_dashboard_manager_governorate_mismatch(client, test_db, manager_user, auth_headers_manager):
    params = {
        'period_start': '2026-01-01',
        'period_end': '2026-01-10',
        'governorate': 'Irbid'
    }
    response = client.get('/api/kpi/dashboard-data', headers=auth_headers_manager, params=params)
    assert response.status_code == 403


def test_kpi_dashboard_requires_admin_or_manager(client, test_db, parent_user, auth_headers_parent):
    params = {
        'period_start': '2026-01-01',
        'period_end': '2026-01-10'
    }
    response = client.get('/api/kpi/dashboard-data', headers=auth_headers_parent, params=params)
    assert response.status_code == 403


def test_kpi_dashboard_low_performers_unique(client, test_db, admin_user, auth_headers_admin, sample_kindergarten):
    params = {
        'period_start': '2026-01-01',
        'period_end': '2026-01-31'
    }
    resp = client.get('/api/kpi/dashboard-data', headers=auth_headers_admin, params=params)
    assert resp.status_code == 200
    data = resp.json()
    low = data.get('low_performers_by_gcei', [])
    ids = [item['id'] for item in low]
    assert len(ids) == len(set(ids)), "Low performers list contains duplicate kindergarten IDs"
    assert len(low) <= 5


def test_kpi_dashboard_admin_city_filter(client, auth_headers_admin, sample_kindergarten):
    params = {
        'period_start': '2026-01-01',
        'period_end': '2026-01-31',
        'district': sample_kindergarten.district,
    }
    response = client.get('/api/kpi/dashboard-data', headers=auth_headers_admin, params=params)
    assert response.status_code == 200
    data = response.json()
    assert data['district'] == sample_kindergarten.district


def test_kpi_dashboard_manager_cannot_access_other_city_dimension(client, auth_headers_manager):
    params = {
        'period_start': '2026-01-01',
        'period_end': '2026-01-10',
        'dimension_type': 'DISTRICT',
        'dimension_id': 'OtherDistrict',
    }
    response = client.get('/api/kpi/dashboard-data', headers=auth_headers_manager, params=params)
    assert response.status_code == 403


def test_manager_dashboard_endpoint_smoke(client, auth_headers_manager):
    params = {
        'period_start': '2026-01-01',
        'period_end': '2026-01-10',
    }
    response = client.get('/api/kpi/manager/dashboard', headers=auth_headers_manager, params=params)
    assert response.status_code == 200
    data = response.json()
    assert 'overall_gcei' in data
    assert data.get('kindergarten_id') is not None


def test_kpi_dashboard_rejects_unsupported_dimension_type(client, auth_headers_admin):
    params = {
        'period_start': '2026-01-01',
        'period_end': '2026-01-10',
        'dimension_type': 'CLASS',
        'dimension_id': '1',
    }
    response = client.get('/api/kpi/dashboard-data', headers=auth_headers_admin, params=params)
    assert response.status_code == 400
    assert 'Invalid dimension_type' in response.json().get('detail', '')


def test_manager_dashboard_endpoint_long_range_avoids_daily_limit(client, auth_headers_manager):
    params = {
        'period_start': '2025-01-01',
        'period_end': '2025-12-31',
    }
    response = client.get('/api/kpi/manager/dashboard', headers=auth_headers_manager, params=params)
    assert response.status_code == 200
    data = response.json()
    assert data['kindergarten_id'] is not None


def test_kpi_dashboard_overall_gcei_quality_not_tied_to_attendance(client, auth_headers_admin, sample_kindergarten):
    params = {
        'period_start': '2026-01-01',
        'period_end': '2026-01-31',
    }
    response = client.get('/api/kpi/dashboard-data', headers=auth_headers_admin, params=params)
    assert response.status_code == 200
    data = response.json()
    assert data['attendance_rate']['has_data'] is False
    assert data['overall_gcei']['has_data'] is True


def test_kpi_dashboard_capacity_quality_uses_capacity_data(client, auth_headers_admin, sample_kindergarten, sample_class):
    params = {
        'period_start': '2026-02-01',
        'period_end': '2026-02-28',
    }
    response = client.get('/api/kpi/dashboard-data', headers=auth_headers_admin, params=params)
    assert response.status_code == 200
    data = response.json()
    assert data['attendance_rate']['has_data'] is False
    assert data['capacity_utilization_rate']['has_data'] is True
