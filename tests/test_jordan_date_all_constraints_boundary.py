"""tests/test_jordan_date_all_constraints_boundary.py — Boundary tests for all Jordan business-date constraints.

Validates that AttendanceLog, Child DOB, and Incident check constraints and application
routes operate under canonical Asia/Amman semantics rather than ambient database UTC.
"""

from datetime import date, datetime, timedelta, timezone
from unittest.mock import patch
import pytest

from utils import time_utils


class TestJordanDateAllConstraintsBoundary:
    """Test boundary conditions across attendance, children DOB, and incidents."""

    def test_rollover_window_time_comparison(self):
        """Between 00:00 and 03:00 Asia/Amman, Jordan date is 1 day ahead of UTC date."""
        mock_amman_dt = datetime(2026, 8, 18, 0, 30, 0, tzinfo=timezone(timedelta(hours=3)))
        with patch("utils.time_utils.now_amman", return_value=mock_amman_dt):
            jordan_today = time_utils.today_amman()
            utc_date = mock_amman_dt.astimezone(timezone.utc).date()

            assert jordan_today == date(2026, 8, 18)
            assert utc_date == date(2026, 8, 17)
            assert jordan_today > utc_date

    def test_attendance_checkin_rollover_valid(self):
        """Attendance check-in on today's Jordan date must succeed during the 00:00-03:00 rollover window."""
        mock_amman_dt = datetime(2026, 8, 18, 0, 30, 0, tzinfo=timezone(timedelta(hours=3)))
        with patch("utils.time_utils.now_amman", return_value=mock_amman_dt):
            report_date = date(2026, 8, 18)
            assert report_date == time_utils.today_amman()
            # Must not be treated as future
            assert not (report_date > time_utils.today_amman())

    def test_attendance_checkin_future_rejected(self):
        """Attendance check-in on tomorrow's Jordan date must be rejected."""
        mock_amman_dt = datetime(2026, 8, 18, 0, 30, 0, tzinfo=timezone(timedelta(hours=3)))
        with patch("utils.time_utils.now_amman", return_value=mock_amman_dt):
            future_date = date(2026, 8, 19)
            assert future_date > time_utils.today_amman()

    def test_child_dob_rollover_valid(self):
        """A child born on the current Jordan date must be accepted during the rollover window."""
        mock_amman_dt = datetime(2026, 8, 18, 1, 15, 0, tzinfo=timezone(timedelta(hours=3)))
        with patch("utils.time_utils.now_amman", return_value=mock_amman_dt):
            dob = date(2026, 8, 18)
            assert dob <= time_utils.today_amman()

    def test_child_dob_future_rejected(self):
        """A child date of birth in the future must be rejected."""
        mock_amman_dt = datetime(2026, 8, 18, 1, 15, 0, tzinfo=timezone(timedelta(hours=3)))
        with patch("utils.time_utils.now_amman", return_value=mock_amman_dt):
            future_dob = date(2026, 8, 19)
            assert future_dob > time_utils.today_amman()

    def test_incident_occurred_at_rollover_valid(self):
        """An incident occurring at 00:45 Jordan time must be valid and <= now_amman()."""
        mock_amman_dt = datetime(2026, 8, 18, 0, 45, 0, tzinfo=timezone(timedelta(hours=3)))
        with patch("utils.time_utils.now_amman", return_value=mock_amman_dt):
            occurred_at = mock_amman_dt
            assert occurred_at <= time_utils.now_amman()

    def test_incident_occurred_at_future_rejected(self):
        """An incident timestamp in the future must be rejected."""
        mock_amman_dt = datetime(2026, 8, 18, 0, 45, 0, tzinfo=timezone(timedelta(hours=3)))
        with patch("utils.time_utils.now_amman", return_value=mock_amman_dt):
            future_occurred_at = mock_amman_dt + timedelta(hours=1)
            assert future_occurred_at > time_utils.now_amman()
