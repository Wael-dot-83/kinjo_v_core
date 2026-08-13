"""
Daily Report Analytics — NULL resilience and mood vocabulary
=============================================================
Regression cover for the production outage on 2026-08-13: every
/api/reports-analytics/* endpoint returned 500 with
``'float' object has no attribute 'split'`` and the dashboard showed
"فشل تحميل البيانات: Failed to load summary".

Root cause: pandas 3 infers ``StringDtype(na_value=nan)`` for the time columns,
so a SQL NULL ``leave_time`` reached ``_hhmm_to_minutes`` as float ``nan``
(truthy) instead of ``None``. Four rows out of 66,424 took the page down.

The same production data also proved two silent inaccuracies:
  * moods are stored uppercase (HAPPY/CALM/ENERGETIC/TIRED/UPSET) while the
    analytics only understood lowercase happy/normal/sad/tired/sick;
  * ``health_notes`` was NULL on every row, which makes the column numeric and
    breaks the ``.str`` accessor.
"""
import os
import secrets
from datetime import date, datetime, timedelta

import pytest

os.environ["TESTING"] = "true"

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from database import Base, get_db
from main import app
from auth import get_password_hash
import models

from daily_report_analytics import (
    DailyReportAnalytics,
    DailyReportViz,
    _hhmm_to_minutes,
    _normalize_mood,
)


# ─── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture(scope="function")
def nv_db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = Session()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="function")
def nv_client(nv_db):
    def _override():
        yield nv_db

    app.dependency_overrides[get_db] = _override
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def nv_kindergarten(nv_db):
    kg = models.Kindergarten(
        name_ar="حضانة النهضة",
        name_en="Al Nahda Nursery",
        governorate="Amman",
        district="Amman",
        area="Downtown",
        address_line="1 Main St",
        contact_phone="+962790000000",
        status=models.KindergartenStatus.ACTIVE,
    )
    nv_db.add(kg)
    nv_db.commit()
    nv_db.refresh(kg)
    return kg


@pytest.fixture
def nv_admin(nv_db):
    u = models.User(
        username="nv_admin",
        email="nv_admin@test.com",
        hashed_password=get_password_hash("Admin123!"),
        role=models.UserRole.ADMIN,
        status=models.UserStatus.ACTIVE,
    )
    nv_db.add(u)
    nv_db.commit()
    nv_db.refresh(u)
    return u


@pytest.fixture
def nv_parent(nv_db):
    u = models.User(
        username="nv_parent@test.com",
        email="nv_parent@test.com",
        hashed_password=get_password_hash("Parent123!"),
        role=models.UserRole.PARENT,
        status=models.UserStatus.ACTIVE,
    )
    nv_db.add(u)
    nv_db.commit()
    nv_db.refresh(u)
    profile = models.ParentProfile(
        user_id=u.id,
        first_name="Test",
        last_name="Parent",
        phone_number="+962790000001",
        gender=models.Gender.MALE,
        nationality="Jordanian",
        national_id="9999999998",
        home_governorate="Amman",
        home_district="Amman",
        home_area="Abdoun",
        home_address_line="2 Main St",
        correspondence_preference=True,
    )
    nv_db.add(profile)
    nv_db.commit()
    nv_db.refresh(profile)
    u.parent_profile = profile
    nv_db.commit()
    nv_db.refresh(u)
    return u


BASE_DATE = date(2026, 8, 5)
# Mirrors production: uppercase vocabulary written by the bulk seeder.
PROD_MOODS = ["HAPPY", "CALM", "ENERGETIC", "TIRED", "UPSET"]


@pytest.fixture
def prodlike_reports(nv_db, nv_kindergarten, nv_parent, nv_admin):
    """6 children × 5 days, shaped like production.

    Row 0 of each day carries the NULL combination that crashed the live
    endpoints (leave_time / mood / nap_duration_minutes / breakfast), and
    health_notes is NULL on every row exactly as it is in production.
    """
    children = []
    for i in range(6):
        c = models.Child(
            parent_id=nv_parent.parent_profile.id,
            first_name=f"طفل{i}",
            last_name="تجربة",
            gender=models.Gender.MALE,
            date_of_birth=date(2022, 6, 15),
            father_name="أب",
            mother_first_name="أم",
            mother_last_name="أم",
            mother_nationality="Jordanian",
            media_consent=True,
        )
        nv_db.add(c)
        children.append(c)
    nv_db.commit()
    for c in children:
        nv_db.refresh(c)

    statuses = [
        models.DailyReportStatus.APPROVED,
        models.DailyReportStatus.SENT_TO_PARENT,
        models.DailyReportStatus.APPROVED,
        models.DailyReportStatus.SUBMITTED,
        models.DailyReportStatus.DRAFT,
        models.DailyReportStatus.REJECTED,
    ]

    reports = []
    for day in range(5):
        d = BASE_DATE + timedelta(days=day)
        for idx, child in enumerate(children):
            # The last child only attends the first day — a real absentee.
            if idx == 5 and day > 0:
                continue
            null_row = idx == 0
            status = statuses[idx]
            r = models.DailyReport(
                child_id=child.id,
                kindergarten_id=nv_kindergarten.id,
                date=d,
                status=status,
                submitted_by=nv_admin.id,
                arrival_time=f"07:{30 + idx:02d}",
                leave_time=None if null_row else f"14:{20 + idx:02d}",
                mood=None if null_row else PROD_MOODS[idx % len(PROD_MOODS)],
                health_notes=None,                       # NULL on every row, as in production
                breakfast=None if null_row else (idx % 2 == 0),
                snack=True,
                milk=True,
                lunch=True,
                nap_start="11:00",
                nap_end="12:00",
                nap_duration_minutes=None if null_row else 45 + idx,
                bathroom_count=idx,
                diaper_wet=False,
                diaper_soiled=False,
                activities="لعب حر",
                rejected_reason="بيانات ناقصة" if status == models.DailyReportStatus.REJECTED else None,
                submitted_at=datetime(d.year, d.month, d.day, 14, 0)
                if status != models.DailyReportStatus.DRAFT else None,
                approved_at=datetime(d.year, d.month, d.day, 16, 0)
                if status in (models.DailyReportStatus.APPROVED,
                              models.DailyReportStatus.SENT_TO_PARENT) else None,
            )
            nv_db.add(r)
            reports.append(r)
    nv_db.commit()
    return children, reports


def _auth_headers(client, username, password):
    resp = client.post("/token", data={"username": username, "password": password})
    assert resp.status_code == 200, resp.text
    token = resp.json()["access_token"]
    csrf = secrets.token_hex(32)
    return {
        "Authorization": f"Bearer {token}",
        "X-CSRF-Token": csrf,
        "Cookie": f"kinjo_csrf_token={csrf}",
    }


RANGE = {"date_from": "2026-08-05", "date_to": "2026-08-13"}


# ─── Unit: the exact crash ────────────────────────────────────────────────────

class TestHhmmParsing:
    def test_nan_is_treated_as_missing(self):
        """float('nan') is truthy — the old falsy check let it reach .split()."""
        assert _hhmm_to_minutes(float("nan")) is None

    @pytest.mark.parametrize("value", [None, "", "   ", "not-a-time", "13", 13, 13.5,
                                       "99:99", "aa:bb", True])
    def test_unparseable_values_are_missing(self, value):
        assert _hhmm_to_minutes(value) is None

    @pytest.mark.parametrize("value,expected", [("07:30", 450), (" 14:05 ", 845),
                                                ("00:00", 0), ("23:59", 1439)])
    def test_valid_times(self, value, expected):
        assert _hhmm_to_minutes(value) == expected


class TestMoodNormalization:
    @pytest.mark.parametrize("raw,expected", [
        ("HAPPY", "happy"), ("happy", "happy"), (" Calm ", "calm"),
        ("ENERGETIC", "energetic"), ("UPSET", "upset"), ("sick", "sick"),
        ("", "unknown"), (None, "unknown"), (float("nan"), "unknown"),
    ])
    def test_both_vocabularies_fold_to_one(self, raw, expected):
        assert _normalize_mood(raw) == expected

    def test_every_canonical_mood_has_a_label_and_colour(self):
        from daily_report_analytics import MOOD_ORDER
        for mood in MOOD_ORDER:
            assert mood in DailyReportViz.MOOD_LABELS
            assert mood in DailyReportViz.MOOD_LABELS_EN
            assert mood in DailyReportViz.COLORS


# ─── API: the endpoints that 500'd in production ──────────────────────────────

class TestEndpointsSurviveNulls:
    def test_summary_returns_200(self, nv_client, prodlike_reports, nv_admin):
        headers = _auth_headers(nv_client, "nv_admin", "Admin123!")
        resp = nv_client.get("/api/reports-analytics/summary", params=RANGE, headers=headers)
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["total_reports"] > 0
        # The NULL leave_time rows must be skipped, not poison the average.
        assert data["attendance"]["avg_leave"] != "--:--"
        assert data["attendance"]["avg_arrival"] != "--:--"

    def test_charts_returns_200(self, nv_client, prodlike_reports, nv_admin):
        headers = _auth_headers(nv_client, "nv_admin", "Admin123!")
        resp = nv_client.get("/api/reports-analytics/charts", params=RANGE, headers=headers)
        assert resp.status_code == 200, resp.text
        assert resp.json()["charts"]["mood_pie"]["data"]

    def test_sample_data_returns_200(self, nv_client, prodlike_reports, nv_admin):
        headers = _auth_headers(nv_client, "nv_admin", "Admin123!")
        resp = nv_client.get("/api/reports-analytics/sample-data",
                             params={**RANGE, "limit": 10}, headers=headers)
        assert resp.status_code == 200, resp.text
        assert resp.json()["rows"]

    def test_anomalies_returns_200(self, nv_client, prodlike_reports, nv_admin):
        headers = _auth_headers(nv_client, "nv_admin", "Admin123!")
        resp = nv_client.get("/api/reports-analytics/anomalies", params=RANGE, headers=headers)
        assert resp.status_code == 200, resp.text

    def test_export_csv_returns_200(self, nv_client, prodlike_reports, nv_admin):
        headers = _auth_headers(nv_client, "nv_admin", "Admin123!")
        resp = nv_client.get("/api/reports-analytics/export",
                             params={**RANGE, "format": "csv"}, headers=headers)
        assert resp.status_code == 200, resp.text

    def test_summary_payload_is_json_strict(self, nv_client, prodlike_reports, nv_admin):
        """No NaN/Infinity literals — FastAPI serializes with allow_nan=False."""
        headers = _auth_headers(nv_client, "nv_admin", "Admin123!")
        resp = nv_client.get("/api/reports-analytics/summary", params=RANGE, headers=headers)
        assert resp.status_code == 200
        assert "NaN" not in resp.text and "Infinity" not in resp.text


class TestProductionMoodVocabulary:
    def test_uppercase_moods_are_bucketed(self, nv_client, prodlike_reports, nv_admin):
        headers = _auth_headers(nv_client, "nv_admin", "Admin123!")
        resp = nv_client.get("/api/reports-analytics/summary", params=RANGE, headers=headers)
        overall = resp.json()["mood_trends"]["overall"]
        assert "HAPPY" not in overall, "raw uppercase mood leaked into the payload"
        assert {"calm", "energetic", "upset"} <= set(overall)
        assert overall["unknown"] > 0, "NULL moods must be reported as unknown"

    def test_mood_line_plots_the_seeded_vocabulary(self, nv_client, prodlike_reports, nv_admin):
        headers = _auth_headers(nv_client, "nv_admin", "Admin123!")
        resp = nv_client.get("/api/reports-analytics/charts", params=RANGE, headers=headers)
        traces = resp.json()["charts"]["mood_line"]["data"]
        names = {t["name"] for t in traces}
        # Previously the chart only looked for happy/normal/sad/tired/sick and
        # came back with zero traces for production data.
        assert len(traces) >= 3
        assert DailyReportViz.MOOD_LABELS["calm"] in names

    def test_sample_rows_expose_canonical_moods(self, nv_client, prodlike_reports, nv_admin):
        headers = _auth_headers(nv_client, "nv_admin", "Admin123!")
        resp = nv_client.get("/api/reports-analytics/sample-data",
                             params={**RANGE, "limit": 10}, headers=headers)
        moods = {r["mood"] for r in resp.json()["rows"]}
        assert moods <= set(DailyReportViz.MOOD_LABELS)


class TestChartLanguage:
    def test_english_titles_when_requested(self, nv_client, prodlike_reports, nv_admin):
        headers = _auth_headers(nv_client, "nv_admin", "Admin123!")
        resp = nv_client.get("/api/reports-analytics/charts",
                             params={**RANGE, "lang": "en"}, headers=headers)
        charts = resp.json()["charts"]
        assert charts["mood_pie"]["layout"]["title"]["text"] == "Mood distribution"
        assert charts["attendance_line"]["layout"]["xaxis"]["title"]["text"] == "Date"

    def test_arabic_is_the_default(self, nv_client, prodlike_reports, nv_admin):
        headers = _auth_headers(nv_client, "nv_admin", "Admin123!")
        resp = nv_client.get("/api/reports-analytics/charts", params=RANGE, headers=headers)
        assert resp.json()["charts"]["mood_pie"]["layout"]["title"]["text"] == "توزيع المزاج"


class TestHealthFlagsWithoutNotes:
    def test_all_null_health_notes_does_not_crash(self, nv_client, prodlike_reports, nv_admin):
        """An all-NULL notes column is numeric; .str.contains raises on it."""
        headers = _auth_headers(nv_client, "nv_admin", "Admin123!")
        resp = nv_client.get("/api/reports-analytics/summary", params=RANGE, headers=headers)
        assert resp.status_code == 200, resp.text
        assert resp.json()["health_flags"]["flagged_keywords"] == []


class TestAnomalyAccuracy:
    def test_absence_uses_operating_days_not_calendar_days(self, nv_client,
                                                           prodlike_reports, nv_admin):
        """The window is 9 calendar days but the kindergarten filed on 5.

        Children present every operating day must not be flagged; the child who
        attended once must be.
        """
        headers = _auth_headers(nv_client, "nv_admin", "Admin123!")
        resp = nv_client.get("/api/reports-analytics/summary", params=RANGE, headers=headers)
        absences = [a for a in resp.json()["anomalies"] if a["type"] == "absence"]
        assert len(absences) == 1, absences
        assert "5" in absences[0]["message_en"]          # 4 of 5 operating days
        assert absences[0]["message_en"].startswith("Child ")

    def test_alerts_carry_both_languages(self, nv_client, prodlike_reports, nv_admin):
        headers = _auth_headers(nv_client, "nv_admin", "Admin123!")
        resp = nv_client.get("/api/reports-analytics/summary", params=RANGE, headers=headers)
        anomalies = resp.json()["anomalies"]
        assert anomalies
        for alert in anomalies:
            assert alert["message"] and alert["message_en"]
            assert alert["message"] != alert["message_en"]

    def test_kindergarten_alerts_name_the_kindergarten(self, nv_client,
                                                      prodlike_reports, nv_admin):
        headers = _auth_headers(nv_client, "nv_admin", "Admin123!")
        resp = nv_client.get("/api/reports-analytics/summary", params=RANGE, headers=headers)
        kg_alerts = [a for a in resp.json()["anomalies"]
                     if a["type"] in ("high_rejection", "low_meal")]
        assert kg_alerts, "expected a rejection or low-meal alert for the seeded data"
        for alert in kg_alerts:
            assert "حضانة النهضة" in alert["message"]
            assert "Al Nahda Nursery" in alert["message_en"]


class TestAlertVolumeIsBounded:
    """Production would have emitted 11,562 absence alerts in one payload."""

    def _frame(self, children: int, days: int):
        import pandas as pd
        from daily_report_analytics import _finalize_reports_df

        rows = []
        rid = 0
        for child in range(children):
            # every child attends only the first day of a long operating window
            for day in range(1):
                d = BASE_DATE + timedelta(days=day)
                rows.append((rid, child, 1, d, "APPROVED", 1,
                             datetime(d.year, d.month, d.day, 14, 0), 1,
                             datetime(d.year, d.month, d.day, 16, 0), None, None,
                             "07:30", "14:00", "HAPPY", None,
                             True, True, True, True, "11:00", "12:00", 60,
                             1, False, False, "لعب", None,
                             datetime(d.year, d.month, d.day, 8, 0),
                             f"طفل{child}", "تجربة", date(2022, 6, 15),
                             "حضانة النهضة", "Al Nahda Nursery"))
                rid += 1
        # one child attends every day so the kindergarten has `days` operating days
        for day in range(days):
            d = BASE_DATE + timedelta(days=day)
            rows.append((rid, 999999, 1, d, "APPROVED", 1,
                         datetime(d.year, d.month, d.day, 14, 0), 1,
                         datetime(d.year, d.month, d.day, 16, 0), None, None,
                         "07:30", "14:00", "HAPPY", None,
                         True, True, True, True, "11:00", "12:00", 60,
                         1, False, False, "لعب", None,
                         datetime(d.year, d.month, d.day, 8, 0),
                         "طفل ملتزم", "تجربة", date(2022, 6, 15),
                         "حضانة النهضة", "Al Nahda Nursery"))
            rid += 1

        df = pd.DataFrame(rows, columns=[
            "id", "child_id", "kindergarten_id", "date", "status",
            "submitted_by", "submitted_at", "approved_by", "approved_at",
            "sent_to_parent_at", "rejected_reason",
            "arrival_time", "leave_time", "mood", "health_notes",
            "breakfast", "snack", "milk", "lunch",
            "nap_start", "nap_end", "nap_duration_minutes",
            "bathroom_count", "diaper_wet", "diaper_soiled",
            "activities", "notes", "created_at",
            "child_first_name", "child_last_name", "child_dob",
            "kindergarten_name_ar", "kindergarten_name_en",
        ])
        return _finalize_reports_df(df)

    def test_absence_alerts_are_capped_with_a_rollup(self):
        df = self._frame(children=400, days=8)
        alerts = DailyReportAnalytics(df).detect_anomalies(BASE_DATE, BASE_DATE + timedelta(days=8))
        absences = [a for a in alerts if a["type"] == "absence"]
        rollup = [a for a in alerts if a["type"] == "absence_more"]
        assert len(absences) == DailyReportAnalytics.MAX_ALERTS_PER_RULE
        assert len(rollup) == 1
        assert rollup[0]["count"] == 400 - DailyReportAnalytics.MAX_ALERTS_PER_RULE

    def test_full_attendance_is_never_flagged(self):
        df = self._frame(children=1, days=8)
        alerts = DailyReportAnalytics(df).detect_anomalies(BASE_DATE, BASE_DATE + timedelta(days=8))
        flagged_children = {a.get("child_id") for a in alerts if a["type"] == "absence"}
        assert 999999 not in flagged_children
