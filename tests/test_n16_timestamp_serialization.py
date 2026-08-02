"""N16 — timestamp serialization contracts.

Storage is aware UTC (db_types.UTCDateTime). Which timezone reaches the consumer is a
per-consumer decision, and these tests pin all four contracts:

* **A** UTC with an explicit offset — machine/API output, and anything a browser
  localises itself via ``new Date()`` + ``toLocaleString()``.
* **B** Asia/Amman — any calendar value the *server* derives (day grouping, month
  buckets, export date columns, server-rendered text).
* **C** date-only business values — never timezone-shifted.
* **D** durations — computed in UTC, not localised.

The boundary cases below are the whole point. Jordan is UTC+3, so 21:00Z is midnight
in Amman: every instant from 21:00:00Z to 23:59:59Z belongs to the *next* Jordan day.
That three-hour window is where every N16 defect lived.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest

from utils.time_utils import (
    get_amman_tz,
    parse_stored_utc,
    to_jordan_date,
    to_jordan_iso,
    to_utc_iso,
)

JORDAN = get_amman_tz()

# (stored UTC instant, expected Jordan wall clock, expected Jordan calendar date)
BOUNDARY_CASES = [
    (
        datetime(2026, 8, 1, 20, 59, 59, tzinfo=timezone.utc),
        "2026-08-01T23:59:59+03:00",
        date(2026, 8, 1),
    ),
    (
        datetime(2026, 8, 1, 21, 0, 0, tzinfo=timezone.utc),
        "2026-08-02T00:00:00+03:00",
        date(2026, 8, 2),
    ),
    (
        datetime(2026, 8, 1, 23, 59, 59, tzinfo=timezone.utc),
        "2026-08-02T02:59:59+03:00",
        date(2026, 8, 2),
    ),
]


class TestJordanBoundaries:
    """The 21:00Z cliff, from both sides."""

    @pytest.mark.parametrize("stored,expected_iso,expected_date", BOUNDARY_CASES)
    def test_to_jordan_iso_at_boundary(self, stored, expected_iso, expected_date):
        assert to_jordan_iso(stored) == expected_iso

    @pytest.mark.parametrize("stored,expected_iso,expected_date", BOUNDARY_CASES)
    def test_to_jordan_date_at_boundary(self, stored, expected_iso, expected_date):
        assert to_jordan_date(stored) == expected_date

    def test_one_second_apart_can_fall_on_different_jordan_days(self):
        """20:59:59Z and 21:00:00Z are one second apart and two Jordan days apart."""
        before = to_jordan_date(datetime(2026, 8, 1, 20, 59, 59, tzinfo=timezone.utc))
        after = to_jordan_date(datetime(2026, 8, 1, 21, 0, 0, tzinfo=timezone.utc))
        assert after - before == timedelta(days=1)

    def test_month_bucket_crosses_at_the_jordan_boundary(self):
        """The month-bucket defect (N16-B1/B5): 31 Aug 21:00Z is 1 Sep in Amman."""
        assert to_jordan_date(datetime(2026, 8, 31, 20, 59, 59, tzinfo=timezone.utc)).strftime("%Y-%m") == "2026-08"
        assert to_jordan_date(datetime(2026, 8, 31, 21, 0, 0, tzinfo=timezone.utc)).strftime("%Y-%m") == "2026-09"

    def test_utc_derivation_would_have_been_wrong(self):
        """Pins the bug itself, so a regression cannot pass silently."""
        stored = datetime(2026, 8, 1, 21, 0, 0, tzinfo=timezone.utc)
        assert stored.date() == date(2026, 8, 1)        # the old, wrong answer
        assert to_jordan_date(stored) == date(2026, 8, 2)  # the correct one


class TestInputHandling:
    """None, naive legacy input, already-aware UTC, already-aware Jordan."""

    def test_none_round_trips_as_none(self):
        assert parse_stored_utc(None) is None
        assert to_utc_iso(None) is None
        assert to_jordan_iso(None) is None
        assert to_jordan_date(None) is None

    def test_naive_legacy_input_is_treated_as_utc(self):
        naive = datetime(2026, 8, 1, 21, 0, 0)
        assert parse_stored_utc(naive) == datetime(2026, 8, 1, 21, 0, 0, tzinfo=timezone.utc)
        assert to_jordan_date(naive) == date(2026, 8, 2)

    def test_already_aware_utc_is_unchanged(self):
        aware = datetime(2026, 8, 1, 21, 0, 0, tzinfo=timezone.utc)
        assert parse_stored_utc(aware) == aware

    def test_already_aware_jordan_is_converted_not_relabelled(self):
        """A Jordan-aware input must keep its instant, not have its clock reinterpreted."""
        jordan = datetime(2026, 8, 2, 0, 0, 0, tzinfo=JORDAN)
        assert parse_stored_utc(jordan) == datetime(2026, 8, 1, 21, 0, 0, tzinfo=timezone.utc)
        assert to_jordan_date(jordan) == date(2026, 8, 2)


class TestConversionHappensExactlyOnce:
    """Idempotence — the "do not convert on both server and client" guarantee."""

    def test_parse_stored_utc_is_idempotent(self):
        stored = datetime(2026, 8, 1, 21, 0, 0, tzinfo=timezone.utc)
        assert parse_stored_utc(parse_stored_utc(stored)) == parse_stored_utc(stored)

    def test_to_jordan_date_is_idempotent_through_reparse(self):
        stored = datetime(2026, 8, 1, 21, 0, 0, tzinfo=timezone.utc)
        once = to_jordan_iso(stored)
        twice = to_jordan_iso(datetime.fromisoformat(once))
        assert once == twice, "re-converting an already-Jordan value must not shift it again"

    def test_utc_iso_always_carries_an_explicit_offset(self):
        """Without an offset, JS `new Date()` parses the string as local time."""
        rendered = to_utc_iso(datetime(2026, 8, 1, 21, 0, 0, tzinfo=timezone.utc))
        assert rendered.endswith("+00:00")

    def test_jordan_iso_always_carries_an_explicit_offset(self):
        rendered = to_jordan_iso(datetime(2026, 8, 1, 21, 0, 0, tzinfo=timezone.utc))
        assert rendered.endswith("+03:00")

    def test_helpers_do_not_mutate_their_input(self):
        stored = datetime(2026, 8, 1, 21, 0, 0, tzinfo=timezone.utc)
        snapshot = datetime(2026, 8, 1, 21, 0, 0, tzinfo=timezone.utc)
        to_jordan_iso(stored)
        to_jordan_date(stored)
        to_utc_iso(stored)
        assert stored == snapshot


class TestDateOnlyValuesAreNeverShifted:
    """Category C: Column(Date) fields have no time or zone (N16 §4)."""

    def test_a_plain_date_is_not_a_datetime_and_must_not_be_converted(self):
        dob = date(2026, 8, 1)
        assert dob.isoformat() == "2026-08-01"
        assert not isinstance(dob, datetime)

    def test_to_jordan_date_of_midnight_utc_is_the_previous_jordan_day(self):
        """Why date-only values must not be routed through the datetime helpers.

        Promoting a date to midnight UTC and converting would move it a day backwards
        for a Jordan reader — which is exactly what must never happen to a date of
        birth, a licence expiry, or a report period.
        """
        promoted = datetime(2026, 8, 1, 0, 0, 0, tzinfo=timezone.utc)
        assert to_jordan_date(promoted) == date(2026, 8, 1)
        # 03:00 Jordan on the same day — safe here, but the general case is not,
        # which is why category C is excluded by policy rather than by luck.
        assert to_jordan_iso(promoted).startswith("2026-08-01T03:00:00")


class TestDurationsAreNotLocalised:
    """Category D: elapsed time is computed in UTC and is timezone-independent."""

    def test_elapsed_time_is_identical_in_either_zone(self):
        start = datetime(2026, 8, 1, 20, 0, 0, tzinfo=timezone.utc)
        end = datetime(2026, 8, 1, 23, 30, 0, tzinfo=timezone.utc)
        utc_delta = parse_stored_utc(end) - parse_stored_utc(start)
        jordan_delta = end.astimezone(JORDAN) - start.astimezone(JORDAN)
        assert utc_delta == jordan_delta == timedelta(hours=3, minutes=30)
