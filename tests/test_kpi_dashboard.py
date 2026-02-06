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
