"""Smoke + integration tests for the Admin Jordan Heat Map feature."""
import math
import os
import sys
from datetime import date, timedelta
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import models
from database import Base, get_db
import dependencies
import admin_endpoints

# Use in-memory SQLite for testing (per project test conventions)
SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()


Base.metadata.create_all(engine)


def _reset_kindergarten_heatmap_data():
    with TestingSessionLocal() as db:
        for model in [
            models.DailyReport,
            models.EnrollmentApplication,
            models.GovernanceScore,
            models.Class,
            models.SupervisorProfile,
            models.User,
            models.Child,
            models.ParentProfile,
            models.Kindergarten,
        ]:
            db.query(model).delete()
        db.commit()


def _seed_kindergarten(db, *, kg_id: int, governorate: str, district: str, status, high_score: bool):
    kg = models.Kindergarten(
        id=kg_id,
        name_ar=f"روضة {kg_id}",
        name_en=f"KG {kg_id}",
        governorate=governorate,
        district=city,
        area="Area",
        address_line="Street",
        contact_phone="0790000000",
        contact_email=f"kg{kg_id}@test.com",
        status=status,
        latitude=31.95 if high_score else None,
        longitude=35.95 if high_score else None,
        license_valid_until=date.today() + timedelta(days=30),
    )
    db.add(kg)
    db.flush()

    if high_score:
        parent_user = models.User(
            id=100 + kg_id,
            username=f"parent{kg_id}",
            role=models.UserRole.PARENT,
            hashed_password="x",
        )
        parent = models.ParentProfile(
            id=100 + kg_id,
            user_id=parent_user.id,
            first_name="Parent",
            last_name="Test",
            phone_number="0791111111",
            gender=models.Gender.FEMALE,
            nationality="Jordanian",
            home_governorate=governorate,
            home_district=city,
            home_area="Area",
            home_address_line="Home",
            correspondence_preference=True,
            notification_language="ar",
        )
        child = models.Child(
            id=200 + kg_id,
            parent_id=parent.id,
            first_name="Child",
            last_name="Test",
            gender=models.Gender.FEMALE,
            date_of_birth=date.today() - timedelta(days=365 * 4),
            father_name="Father",
            mother_first_name="Mother",
            mother_last_name="Test",
            mother_nationality="Jordanian",
        )
        supervisor = models.User(
            id=300 + kg_id,
            username=f"supervisor{kg_id}",
            role=models.UserRole.SUPERVISOR,
            kindergarten_id=kg.id,
            hashed_password="x",
        )
        classroom = models.Class(
            id=400 + kg_id,
            kindergarten_id=kg.id,
            name_ar="صف",
            class_code=f"CLS{kg_id}",
            age_group="AGE_0_1",
            enrolled_children_count=1,
            capacity_total=20,
            min_age_months=36,
            max_age_months=72,
        )
        db.add_all([parent_user, parent, child, supervisor, classroom])
        db.flush()
        db.add(models.SupervisorProfile(user_id=supervisor.id, kindergarten_id=kg.id))
        db.add(
            models.EnrollmentApplication(
                child_id=child.id,
                kindergarten_id=kg.id,
                class_id=classroom.id,
                status=models.EnrollmentStatus.ACTIVE,
                source="TEST",
            )
        )
        for day_offset in range(30):
            db.add(
                models.DailyReport(
                    child_id=child.id,
                    kindergarten_id=kg.id,
                    date=date.today() - timedelta(days=day_offset),
                    status=models.DailyReportStatus.SUBMITTED,
                    submitted_by=supervisor.id,
                    arrival_time="08:00",
                )
            )
        db.add(
            models.GovernanceScore(
                kindergarten_id=kg.id,
                period_start=date.today() - timedelta(days=30),
                period_end=date.today(),
                governance_quality_index=95,
                child_experience_index=95,
                final_governance_score=95,
                band="A",
            )
        )


async def override_current_user():
    u = models.User(id=1, email="admin@test.com", role=models.UserRole.ADMIN)
    return u


# Build a fresh app for testing (no static files needed)
from fastapi import FastAPI
from heatmap.backend.admin_router import router as heat_map_router

app = FastAPI()
app.include_router(heat_map_router, prefix="/api")
app.dependency_overrides[dependencies.get_current_user] = override_current_user


# ---------------------------------------------------------------------------
# Unit tests for the heat map service
# ---------------------------------------------------------------------------
def test_governorates_canonical():
    from heatmap.backend import service
    govs = service.get_governorates()
    assert len(govs) == 12
    expected = ['amman', 'irbid', 'zarqa', 'mafraq', 'jerash', 'ajloun',
                'balqa', 'madaba', 'karak', 'tafileh', 'maan', 'aqaba']
    assert sorted([g['slug'] for g in govs]) == sorted(expected)


def test_indicators_canonical():
    from heatmap.backend import service
    inds = service.get_indicators()
    assert len(inds) == 6
    expected = ['nursery_status', 'children_registration', 'staff_classrooms',
                'safety_incidents', 'reports_attendance', 'tasks_governance']
    assert sorted([i['key'] for i in inds]) == sorted(expected)


def test_sub_indicators_present():
    from heatmap.backend import service, constants
    inds = service.get_indicators()
    for ind in inds:
        assert ind['sub_indicators'], f"Indicator {ind['key']} has no sub-indicators"
        for sub in ind['sub_indicators']:
            assert sub['name_en']
            assert sub['name_ar']
            assert sub['unit']
            assert 'threshold_high' in sub
            assert 'threshold_low' in sub


def test_risk_levels():
    from heatmap.backend import constants
    assert len(constants.RISK_LEVELS) == 4
    levels = [r['key'] for r in constants.RISK_LEVELS]
    assert levels == ['low', 'medium', 'high', 'critical']
    # Verify boundary logic (boundaries: low=0-24, medium=25-49, high=50-74, critical=75-100)
    assert constants.risk_level_for_score(0)['key'] == 'low'
    assert constants.risk_level_for_score(24)['key'] == 'low'
    assert constants.risk_level_for_score(25)['key'] == 'medium'
    assert constants.risk_level_for_score(49)['key'] == 'medium'
    assert constants.risk_level_for_score(50)['key'] == 'high'
    assert constants.risk_level_for_score(74)['key'] == 'high'
    assert constants.risk_level_for_score(75)['key'] == 'critical'
    assert constants.risk_level_for_score(100)['key'] == 'critical'


def test_correlation_levels():
    from heatmap.backend import constants
    assert len(constants.CORRELATION_LEVELS) == 4
    # Pearson r values
    assert constants.correlation_level_for(0.0)['key'] == 'weak'
    assert constants.correlation_level_for(0.29)['key'] == 'weak'
    assert constants.correlation_level_for(0.30)['key'] == 'moderate'
    assert constants.correlation_level_for(0.59)['key'] == 'moderate'
    assert constants.correlation_level_for(0.60)['key'] == 'strong'
    assert constants.correlation_level_for(0.79)['key'] == 'strong'
    assert constants.correlation_level_for(0.80)['key'] == 'very_strong'
    assert constants.correlation_level_for(1.00)['key'] == 'very_strong'
    # Symmetric (absolute value)
    assert constants.correlation_level_for(-0.85)['key'] == 'very_strong'


def test_governorate_normalization():
    from heatmap.backend import constants
    # Canonical English
    assert constants.normalize_governorate('amman') == 'amman'
    assert constants.normalize_governorate('Amman') == 'amman'
    # Arabic
    assert constants.normalize_governorate('عمان') == 'amman'
    # English with apostrophe
    assert constants.normalize_governorate("Ma'an") == 'maan'
    # Unknown
    assert constants.normalize_governorate('unknown') == 'unknown'


def test_geojson_loads():
    from heatmap.backend import service
    gj = service.load_jordan_geojson()
    assert gj['type'] == 'FeatureCollection'
    features = gj.get('features', [])
    assert len(features) > 0
    gov_features = [f for f in features if f.get('properties', {}).get('level') == 'governorate']
    assert len(gov_features) == 12, f"Expected 12 governorate features, got {len(gov_features)}"


def test_correlations_with_no_db():
    """Service should handle no-DB gracefully."""
    from heatmap.backend import service
    data = service.get_correlations(db=None)
    assert 'matrix' in data
    assert 'method' in data
    assert data['method'] == 'pearson'


def test_regression_with_no_db():
    from heatmap.backend import service
    data = service.get_regression_weights(db=None)
    assert 'weights' in data
    assert 'note' in data


def test_daily_update_summary():
    from heatmap.backend import service
    s = service.daily_update_summary(db=None)
    assert 'last_update' in s
    assert 'schedule' in s
    assert 'data_sources' in s
    assert 'daily' in s['schedule'].lower()


def test_service_governance_score_uses_governance_score_table():
    from heatmap.backend import service
    _reset_kindergarten_heatmap_data()
    with TestingSessionLocal() as db:
        _seed_kindergarten(db, kg_id=11, governorate="Amman", district="Amman", status=models.KindergartenStatus.ACTIVE, high_score=True)
        _seed_kindergarten(db, kg_id=12, governorate="Amman", district="Amman", status=models.KindergartenStatus.ACTIVE, high_score=True)
        _seed_kindergarten(db, kg_id=13, governorate="Irbid", district="Irbid", status=models.KindergartenStatus.ACTIVE, high_score=True)
        db.flush()
        db.query(models.GovernanceScore).filter_by(kindergarten_id=11).one().final_governance_score = 80
        db.query(models.GovernanceScore).filter_by(kindergarten_id=12).one().final_governance_score = 100
        db.query(models.GovernanceScore).filter_by(kindergarten_id=13).one().final_governance_score = 10
        db.commit()

    with TestingSessionLocal() as db:
        assert math.isclose(service._query_governance_score(db, "amman"), 90.0)


def test_pipeline_governance_score_uses_governance_score_table():
    from heatmap.backend import pipeline
    _reset_kindergarten_heatmap_data()
    with TestingSessionLocal() as db:
        _seed_kindergarten(db, kg_id=21, governorate="Amman", district="Amman", status=models.KindergartenStatus.ACTIVE, high_score=True)
        _seed_kindergarten(db, kg_id=22, governorate="Amman", district="Amman", status=models.KindergartenStatus.ACTIVE, high_score=True)
        _seed_kindergarten(db, kg_id=23, governorate="Irbid", district="Irbid", status=models.KindergartenStatus.ACTIVE, high_score=True)
        db.flush()
        db.query(models.GovernanceScore).filter_by(kindergarten_id=21).one().final_governance_score = 80
        db.query(models.GovernanceScore).filter_by(kindergarten_id=22).one().final_governance_score = 100
        db.query(models.GovernanceScore).filter_by(kindergarten_id=23).one().final_governance_score = 10
        db.commit()

    with TestingSessionLocal() as db:
        assert math.isclose(pipeline._query_governance_score(db, "Amman"), 90.0)


# ---------------------------------------------------------------------------
# Integration tests for the admin API
# ---------------------------------------------------------------------------
def test_api_governorates():
    with TestClient(app) as client:
        r = client.get('/api/admin/heat-map/governorates')
        assert r.status_code == 200
        data = r.json()
        assert data['count'] == 12
        assert all('slug' in g and 'name_en' in g and 'name_ar' in g for g in data['governorates'])


def test_api_indicators():
    with TestClient(app) as client:
        r = client.get('/api/admin/heat-map/indicators')
        assert r.status_code == 200
        data = r.json()
        assert data['count'] == 6
        for ind in data['indicators']:
            assert 'name_en' in ind
            assert 'name_ar' in ind
            assert 'sub_indicators' in ind
            assert 'alert_threshold' in ind


def test_api_data():
    with TestClient(app) as client:
        r = client.get('/api/admin/heat-map/data')
        assert r.status_code == 200
        data = r.json()
        assert 'governorates' in data
        assert 'indicators' in data
        assert 'risk_legend' in data
        assert 'summary' in data
        # 12 governorates
        assert len(data['governorates']) == 12
        # Each governorate has the required fields
        for g in data['governorates']:
            assert 'slug' in g
            assert 'main_indicators' in g
            assert 'risk_score' in g
            assert 'risk_level' in g


def test_api_governorate_detail():
    with TestClient(app) as client:
        r = client.get('/api/admin/heat-map/governorate/amman')
        assert r.status_code == 200
        data = r.json()
        assert data['slug'] == 'amman'
        assert 'main_indicators' in data
        assert 'sub_indicators' in data
        assert 'risk_score' in data
        assert 'risk_level' in data
        assert 'trends' in data
        assert 'alerts' in data
        assert 'recommended_action' in data
        assert 'last_update' in data


def test_api_kindergartens_list_filters_and_pagination():
    _reset_kindergarten_heatmap_data()
    with TestingSessionLocal() as db:
        _seed_kindergarten(db, kg_id=1, governorate="Amman", district="Amman", status=models.KindergartenStatus.ACTIVE, high_score=True)
        _seed_kindergarten(db, kg_id=2, governorate="Irbid", district="Irbid", status=models.KindergartenStatus.INACTIVE, high_score=False)
        db.commit()

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as client:
            r = client.get('/api/admin/heat-map/kindergartens?governorate=amman&page=1&page_size=1')
            assert r.status_code == 200, r.text
            data = r.json()
            assert data['total'] == 1
            assert data['count'] == 1
            assert data['pagination']['page'] == 1
            assert data['pagination']['page_size'] == 1
            assert data['items'][0]['latitude'] == 31.95
            assert data['items'][0]['longitude'] == 35.95
            assert data['items'][0]['kpi_status'] == 'normal'
    finally:
        if get_db in app.dependency_overrides:
            del app.dependency_overrides[get_db]


def test_api_kindergarten_detail():
    _reset_kindergarten_heatmap_data()
    with TestingSessionLocal() as db:
        _seed_kindergarten(db, kg_id=3, governorate="Amman", district="Amman", status=models.KindergartenStatus.ACTIVE, high_score=True)
        db.commit()

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as client:
            r = client.get('/api/admin/heat-map/kindergartens/3')
            assert r.status_code == 200, r.text
            data = r.json()
            assert data['kindergarten']['id'] == 3
            assert data['kindergarten']['kpi_status'] == 'normal'
            assert data['kindergarten']['main_indicators']['nursery_status']['status'] == 'normal'
    finally:
        if get_db in app.dependency_overrides:
            del app.dependency_overrides[get_db]


def test_api_kindergartens_map_data():
    _reset_kindergarten_heatmap_data()
    with TestingSessionLocal() as db:
        _seed_kindergarten(db, kg_id=4, governorate="Amman", district="Amman", status=models.KindergartenStatus.ACTIVE, high_score=True)
        _seed_kindergarten(db, kg_id=5, governorate="Amman", district="Amman", status=models.KindergartenStatus.INACTIVE, high_score=False)
        db.commit()

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as client:
            r = client.get('/api/admin/heat-map/kindergartens/map-data?district=Amman')
            assert r.status_code == 200, r.text
            data = r.json()
            assert data['type'] == 'FeatureCollection'
            assert data['total_kindergartens'] == 2
            # kg4 has explicit coords; kg5 (no lat/lon) gets Amman governorate-center fallback
            assert data['count'] >= 1
            assert data['missing_location_count'] >= 0
            coords_list = [f['geometry']['coordinates'] for f in data['features']]
            assert [35.95, 31.95] in coords_list
    finally:
        if get_db in app.dependency_overrides:
            del app.dependency_overrides[get_db]


def test_api_kindergartens_stats():
    _reset_kindergarten_heatmap_data()
    with TestingSessionLocal() as db:
        _seed_kindergarten(db, kg_id=6, governorate="Amman", district="Amman", status=models.KindergartenStatus.ACTIVE, high_score=True)
        _seed_kindergarten(db, kg_id=7, governorate="Irbid", district="Irbid", status=models.KindergartenStatus.INACTIVE, high_score=False)
        db.commit()

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as client:
            r = client.get('/api/admin/heat-map/kindergartens/stats')
            assert r.status_code == 200, r.text
            data = r.json()
            assert data['total'] == 2
            assert sum(data['status_counts'].values()) == 2
            assert data['governorate_counts']['amman']['total'] == 1
            assert data['city_counts']['Amman']['total'] == 1
    finally:
        if get_db in app.dependency_overrides:
            del app.dependency_overrides[get_db]


def test_api_governorate_404():
    with TestClient(app) as client:
        r = client.get('/api/admin/heat-map/governorate/nonexistent')
        assert r.status_code == 404


def test_api_geojson():
    with TestClient(app) as client:
        r = client.get('/api/admin/heat-map/geojson')
        assert r.status_code == 200
        data = r.json()
        assert data['type'] == 'FeatureCollection'
        assert 'features' in data
        assert len(data['features']) > 0


def test_api_correlations():
    with TestClient(app) as client:
        r = client.get('/api/admin/heat-map/correlations')
        assert r.status_code == 200
        data = r.json()
        assert 'matrix' in data
        assert 'method' in data
        assert data['method'] == 'pearson'


def test_api_correlations_filtered():
    with TestClient(app) as client:
        r = client.get('/api/admin/heat-map/correlations?main_indicator=nursery_status')
        assert r.status_code == 200
        data = r.json()
        assert all(row.get('row') == 'nursery_status' or row.get('column') == 'nursery_status' for row in data['matrix'])


def test_api_regression():
    with TestClient(app) as client:
        r = client.get('/api/admin/heat-map/regression')
        assert r.status_code == 200
        data = r.json()
        assert 'weights' in data


def test_api_daily_update():
    with TestClient(app) as client:
        r = client.get('/api/admin/heat-map/daily-update')
        assert r.status_code == 200
        data = r.json()
        assert 'last_update' in data


def test_api_refresh_post():
    """POST /refresh triggers the daily ETL pipeline.

    The test app uses a fresh in-memory DB; we use the seeder to create
    the snapshot tables and seed the 12 governorates, then assert that
    the endpoint returns 200 with a valid summary.
    """
    from sqlalchemy.pool import StaticPool
    from database import Base
    from heatmap.scripts.seed_snapshot_data import seed_governorates
    from heatmap.backend import pipeline

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session_ = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    def fresh_db():
        db = Session_()
        try:
            yield db
        finally:
            db.close()
    app.dependency_overrides[get_db] = fresh_db

    # Seed the 12 governorates (no data yet) so the pipeline has something to work with
    with Session_() as db:
        seed_governorates(db)

    try:
        with TestClient(app) as client:
            r = client.post('/api/admin/heat-map/refresh')
            assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text[:200]}"
            data = r.json()
            assert data["status"] == "success"
            assert data["governorates"] == 12
    finally:
        # Reset the dependency override so other tests aren't affected
        if get_db in app.dependency_overrides:
            del app.dependency_overrides[get_db]


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
