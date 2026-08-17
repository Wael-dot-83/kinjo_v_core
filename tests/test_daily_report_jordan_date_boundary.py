"""Regression tests for DailyReport Jordan business-date semantics and timezone boundary.

Tests scenarios:
A. Jordan rollover window (e.g. 00:30 Asia/Amman, 21:30 previous day UTC):
   Report for the new Jordan calendar date must be VALID.
B. Genuine future Jordan date (e.g. tomorrow in Jordan):
   Report must be REJECTED.
C. Just before Jordan midnight (23:59:50):
   Same-day report is VALID.
D. Just after Jordan midnight (00:00:10):
   New Jordan-day report is VALID, previous day is VALID, day after tomorrow is REJECTED.
E. Manual supervisor report, manager create report, and AI draft/confirm paths obey identical date rules.
"""

from datetime import date, datetime, timedelta, timezone
import zoneinfo
from unittest.mock import patch
import pytest
from fastapi.testclient import TestClient

from main import app
from database import get_db
import models
from utils.time_utils import get_amman_tz, today_amman, now_amman


AMMAN_TZ = get_amman_tz()


def _make_amman_datetime(year: int, month: int, day: int, hour: int, minute: int, second: int = 0) -> datetime:
    return datetime(year, month, day, hour, minute, second, tzinfo=AMMAN_TZ)


class TestDailyReportJordanDateBoundary:

    def test_today_amman_differs_from_utc_date_during_midnight_window(self):
        """Between 00:00 and 03:00 Asia/Amman, UTC date is yesterday while Jordan date is today."""
        # 00:30 Amman on 2026-08-18 is 21:30 UTC on 2026-08-17
        mock_amman_dt = _make_amman_datetime(2026, 8, 18, 0, 30, 0)
        with patch("utils.time_utils.now_amman", return_value=mock_amman_dt):
            jordan_date = today_amman()
            utc_date = mock_amman_dt.astimezone(timezone.utc).date()

            assert jordan_date == date(2026, 8, 18)
            assert utc_date == date(2026, 8, 17)
            assert jordan_date != utc_date

    def test_daily_report_request_validation_scenario_a_rollover_valid(self):
        """Scenario A: Jordan 2026-08-18 00:30 (UTC 2026-08-17 21:30).
        DailyReport date 2026-08-18 is VALID.
        """
        mock_amman_dt = _make_amman_datetime(2026, 8, 18, 0, 30, 0)
        with patch("utils.time_utils.now_amman", return_value=mock_amman_dt):
            from api.daily_reports_routes import DailyReportCreateRequest
            req = DailyReportCreateRequest(
                child_id=1,
                date="2026-08-18",
                arrival_time="08:00",
                leave_time="14:00",
            )
            assert req.date == "2026-08-18"

    def test_daily_report_request_validation_scenario_b_future_rejected(self):
        """Scenario B: Jordan 2026-08-18 00:30.
        DailyReport date 2026-08-19 (Jordan tomorrow) must be REJECTED.
        """
        mock_amman_dt = _make_amman_datetime(2026, 8, 18, 0, 30, 0)
        with patch("utils.time_utils.now_amman", return_value=mock_amman_dt):
            from api.daily_reports_routes import DailyReportCreateRequest
            with pytest.raises(ValueError, match="date cannot be in the future"):
                DailyReportCreateRequest(
                    child_id=1,
                    date="2026-08-19",
                    arrival_time="08:00",
                    leave_time="14:00",
                )

    def test_daily_report_request_validation_scenario_c_before_midnight(self):
        """Scenario C: Jordan 2026-08-18 23:59:50.
        Report for 2026-08-18 is VALID; report for 2026-08-19 is REJECTED.
        """
        mock_amman_dt = _make_amman_datetime(2026, 8, 18, 23, 59, 50)
        with patch("utils.time_utils.now_amman", return_value=mock_amman_dt):
            from api.daily_reports_routes import DailyReportCreateRequest
            req = DailyReportCreateRequest(
                child_id=1,
                date="2026-08-18",
                arrival_time="08:00",
                leave_time="14:00",
            )
            assert req.date == "2026-08-18"

            with pytest.raises(ValueError, match="date cannot be in the future"):
                DailyReportCreateRequest(
                    child_id=1,
                    date="2026-08-19",
                    arrival_time="08:00",
                    leave_time="14:00",
                )

    def test_daily_report_request_validation_scenario_d_after_midnight(self):
        """Scenario D: Jordan 2026-08-19 00:00:10.
        Report for 2026-08-19 is now VALID; report for past date 2026-08-18 is VALID;
        report for 2026-08-20 is REJECTED.
        """
        mock_amman_dt = _make_amman_datetime(2026, 8, 19, 0, 0, 10)
        with patch("utils.time_utils.now_amman", return_value=mock_amman_dt):
            from api.daily_reports_routes import DailyReportCreateRequest
            req_today = DailyReportCreateRequest(
                child_id=1,
                date="2026-08-19",
                arrival_time="08:00",
                leave_time="14:00",
            )
            assert req_today.date == "2026-08-19"

            req_yesterday = DailyReportCreateRequest(
                child_id=1,
                date="2026-08-18",
                arrival_time="08:00",
                leave_time="14:00",
            )
            assert req_yesterday.date == "2026-08-18"

            with pytest.raises(ValueError, match="date cannot be in the future"):
                DailyReportCreateRequest(
                    child_id=1,
                    date="2026-08-20",
                    arrival_time="08:00",
                    leave_time="14:00",
                )

    def test_scenario_e_ai_draft_inherits_identical_jordan_date_rules(self):
        """Scenario E: AI Supervisor Draft request inherits from DailyReportCreateRequest
        and enforces identical Jordan date validation.
        """
        mock_amman_dt = _make_amman_datetime(2026, 8, 18, 1, 15, 0)
        with patch("utils.time_utils.now_amman", return_value=mock_amman_dt):
            from routers.ai import SupervisorDailyReportDraftRequest
            # Current Jordan date (2026-08-18) is valid
            draft = SupervisorDailyReportDraftRequest(
                child_id=1,
                date="2026-08-18",
                arrival_time="08:00",
                leave_time="14:00",
            )
            assert draft.date == "2026-08-18"

            # Future Jordan date (2026-08-19) is rejected
            with pytest.raises(ValueError, match="date cannot be in the future"):
                SupervisorDailyReportDraftRequest(
                    child_id=1,
                    date="2026-08-19",
                    arrival_time="08:00",
                    leave_time="14:00",
                )
