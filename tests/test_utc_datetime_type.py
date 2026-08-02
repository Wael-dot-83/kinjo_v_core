"""Regression tests for db_types.UTCDateTime (D-11).

The bug these lock down: production writes timezone-aware Jordan datetimes, while
jordan_date_range_filter builds its window in UTC. Before UTCDateTime, whether those
agreed was decided by the backend — SQLite discarded the offset outright, and
PostgreSQL only got it right when its session TimeZone happened to be UTC. Both
failure modes silently dropped every record between 21:00 and 24:00 Jordan time.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import Column, Integer, create_engine, select
from sqlalchemy.orm import Session, declarative_base

from db_types import UTCDateTime

JORDAN = timezone(timedelta(hours=3))
Base = declarative_base()


class _Row(Base):
    __tablename__ = "utc_datetime_probe"
    id = Column(Integer, primary_key=True)
    at = Column(UTCDateTime, nullable=True)


@pytest.fixture()
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


def _roundtrip(session, value):
    row = _Row(at=value)
    session.add(row)
    session.commit()
    session.expire_all()
    return session.scalars(select(_Row.at)).one()


def test_jordan_aware_value_is_converted_to_utc(session):
    """23:00+03:00 must come back as 20:00Z — the offset applied, not discarded."""
    stored = _roundtrip(session, datetime(2026, 8, 1, 23, 0, tzinfo=JORDAN))
    assert stored.tzinfo is not None
    assert stored.utcoffset() == timedelta(0)
    assert stored.replace(tzinfo=None) == datetime(2026, 8, 1, 20, 0)


def test_result_is_always_timezone_aware(session):
    stored = _roundtrip(session, datetime(2026, 8, 1, 12, 0, tzinfo=timezone.utc))
    assert stored.tzinfo is not None
    assert stored.utcoffset() == timedelta(0)


def test_naive_input_is_treated_as_utc(session):
    """Naive input is assumed UTC rather than rejected.

    A great deal of existing code and many fixtures pass naive datetimes; raising
    here would turn a data-hygiene problem into an outage.
    """
    stored = _roundtrip(session, datetime(2026, 8, 1, 20, 0))
    assert stored.replace(tzinfo=None) == datetime(2026, 8, 1, 20, 0)
    assert stored.utcoffset() == timedelta(0)


def test_none_round_trips(session):
    assert _roundtrip(session, None) is None


def test_equivalent_instants_in_different_zones_compare_equal(session):
    """23:00+03:00 and 20:00Z are the same instant and must store identically."""
    jordan = _roundtrip(session, datetime(2026, 8, 1, 23, 0, tzinfo=JORDAN))
    session.query(_Row).delete()
    session.commit()
    utc = _roundtrip(session, datetime(2026, 8, 1, 20, 0, tzinfo=timezone.utc))
    assert jordan == utc


def test_late_jordan_evening_falls_inside_its_own_jordan_day(session):
    """The exact regression: 23:00 Jordan belongs to that Jordan day, not the next.

    Uses the production filter so the type and the query helper are verified together.
    """
    from utils.time_utils import jordan_date_range_filter

    day = datetime(2026, 8, 1).date()
    session.add(_Row(at=datetime(2026, 8, 1, 23, 0, tzinfo=JORDAN)))
    session.commit()

    matched = session.scalars(
        select(_Row.id).where(*jordan_date_range_filter(_Row.at, day, day))
    ).all()
    assert len(matched) == 1, "23:00 Jordan was dropped from its own Jordan day"


def test_just_past_midnight_jordan_is_excluded_from_the_previous_day(session):
    """The other side of the boundary, so the fix cannot pass by matching everything."""
    from utils.time_utils import jordan_date_range_filter

    day = datetime(2026, 8, 1).date()
    session.add(_Row(at=datetime(2026, 8, 2, 0, 30, tzinfo=JORDAN)))
    session.commit()

    matched = session.scalars(
        select(_Row.id).where(*jordan_date_range_filter(_Row.at, day, day))
    ).all()
    assert matched == []
