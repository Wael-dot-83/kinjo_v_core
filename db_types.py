"""Custom SQLAlchemy column types.

`UTCDateTime` exists to fix a silent, backend-dependent data-loss bug (D-11).

**The problem it solves.** Production writes timezone-aware Jordan datetimes
(e.g. `routers/supervisor.py` uses `datetime.now(_JORDAN_TZ)`), and
`utils.time_utils.jordan_date_range_filter` builds its window in UTC. Whether those
two agree was left to the database:

| Backend | Behaviour with a plain ``DateTime(timezone=True)`` |
|---|---|
| PostgreSQL, session ``TimeZone=UTC`` | correct — ``timestamptz`` normalises on write |
| PostgreSQL, session ``TimeZone=Asia/Amman`` | **wrong** — naive bounds are read as Jordan time |
| SQLite | **wrong** — the offset is *discarded*, not applied |

Both wrong cases lose every row whose Jordan-local time falls between 21:00 and
24:00 — silently, with no error, on the development and CI default backend.

**How it fixes it.** Normalising in Python removes the dependency on the backend
entirely: every value is converted to UTC on the way in and returned as an aware
UTC datetime on the way out, so comparisons are unambiguous on every dialect and
under any session timezone.

**No migration is required.** The rendered DDL is byte-identical to what
``DateTime(timezone=True)`` already produced — ``TIMESTAMP WITH TIME ZONE`` on
PostgreSQL, ``DATETIME`` on SQLite. Only the Python-side bind/result processing
changes.

**One caveat, development-only.** Rows already written to a *SQLite* file hold
Jordan wall-clock with the offset dropped, and will now be read back as though
they were UTC — a 3-hour shift on pre-existing local data. PostgreSQL is
unaffected (it already stored true UTC), and production forbids SQLite
(`config.validate_production_settings`). Tests build their schema per run, so they
are unaffected. Recreate local SQLite fixtures if exact historical timestamps matter.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime
from sqlalchemy.types import TypeDecorator


class UTCDateTime(TypeDecorator):
    """A ``DateTime`` that always stores and returns UTC.

    Naive input is treated as already-UTC rather than rejected: a great deal of
    existing code and many fixtures pass naive datetimes, and raising here would
    turn a data-hygiene issue into an outage. Aware input is converted.
    """

    impl = DateTime
    cache_ok = True

    def load_dialect_impl(self, dialect):
        # PostgreSQL keeps timestamptz so the database itself stays self-describing;
        # SQLite has no real tz support, so store naive UTC and normalise in Python.
        return dialect.type_descriptor(DateTime(timezone=(dialect.name == "postgresql")))

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if not isinstance(value, datetime):
            return value
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        value = value.astimezone(timezone.utc)
        if dialect.name == "postgresql":
            return value
        # SQLite compares DATETIME lexically, so an offset suffix would break
        # ordering. Store naive UTC — which is exactly what Postgres holds internally.
        return value.replace(tzinfo=None)

    def process_result_value(self, value, dialect):
        if value is None or not isinstance(value, datetime):
            return value
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
