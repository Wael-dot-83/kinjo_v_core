"""Tests for the guided analytics explorer.

These lock down the four correctness properties the module exists to guarantee,
each of which is a defect in the legacy ``charts_api`` path:

  1. The reporting window includes events occurring *during* the final day.
  2. ``records`` (rows counted) and ``groups`` (bars drawn) are reported separately.
  3. ``as_of`` is Jordan time, not naive server time and not UTC.
  4. Every operator-visible string carries both an Arabic and an English variant.
"""

from datetime import date, datetime, timedelta

import pytest

import analytics_explorer as ax
import models


# ---------------------------------------------------------------------------
# 1. Date window boundaries
# ---------------------------------------------------------------------------


def test_window_end_is_exclusive_midnight_of_the_next_day():
    """An event at 23:59 on the final day must fall inside the window.

    The legacy loader compared a DateTime column against a bare date
    (``occurred_at <= date_to``), which excludes the whole of the last day.
    """
    window = ax.Window(start=date(2026, 7, 1), end=date(2026, 7, 27))

    assert window.dt_start == datetime(2026, 7, 1, 0, 0)
    assert window.dt_end_exclusive == datetime(2026, 7, 28, 0, 0)

    last_moment = datetime(2026, 7, 27, 23, 59, 59)
    assert window.dt_start <= last_moment < window.dt_end_exclusive

    # And the legacy comparison would have dropped it.
    assert not last_moment <= datetime.combine(window.end, datetime.min.time())


def test_single_day_window_spans_exactly_24_hours():
    window = ax.Window(start=date(2026, 7, 27), end=date(2026, 7, 27))
    assert window.dt_end_exclusive - window.dt_start == timedelta(days=1)


def test_window_rejects_reversed_dates():
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc:
        ax._resolve_window("2026-07-27", "2026-07-01")
    assert exc.value.status_code == 422


def test_window_rejects_malformed_dates():
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc:
        ax._resolve_window("27-07-2026", None)
    assert exc.value.status_code == 422


# ---------------------------------------------------------------------------
# 2. Scope resolution
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("supplied", ["amman", "Amman", "AMMAN", "عمان", "العاصمة"])
def test_every_amman_spelling_matches_both_stored_names(supplied):
    """The capital is stored as عمان here and as العاصمة elsewhere.

    The legacy loader rewrote every alias to a single winner, which returns zero
    rows on any deployment holding the other spelling. The filter must match either.
    """
    scope = ax._resolve_scope(supplied, None)
    assert set(scope.governorate_names) == {"عمان", "العاصمة"}
    # The English alias is an input convenience and must never reach the query.
    assert all(not name.isascii() for name in scope.governorate_names)


def test_a_governorate_without_synonyms_matches_itself_only():
    assert ax._resolve_scope("إربد", None).governorate_names == ("إربد",)


def test_scope_level_reflects_the_narrowest_filter():
    assert ax._resolve_scope(None, None).level == "national"
    assert ax._resolve_scope("العاصمة", None).level == "governorate"
    assert ax._resolve_scope("العاصمة", 7).level == "kindergarten"


# ---------------------------------------------------------------------------
# 3. Bilingual contract
# ---------------------------------------------------------------------------


def test_every_question_declares_both_languages():
    assert ax.QUESTIONS, "the catalogue must not be empty"
    for key, question in ax.QUESTIONS.items():
        for label in (question.title, question.subtitle):
            assert label.ar.strip(), f"{key} is missing Arabic text"
            assert label.en.strip(), f"{key} is missing English text"
            assert label.ar != label.en, f"{key} has an untranslated string"


def test_known_moods_are_translated_and_unknown_ones_pass_through():
    assert ax._mood_label("سعيد 😊").en == "Happy 😊"
    # An unrecognised value must survive intact rather than becoming "Unknown".
    assert ax._mood_label("مزاج جديد").en == "مزاج جديد"


def test_enum_labels_strip_the_class_prefix():
    assert ax._enum_key("IncidentType.INJURY") == "INJURY"
    assert ax._label_for("SeverityLevel.HIGH").ar == "مرتفعة"


# ---------------------------------------------------------------------------
# 4. Answer payloads against the real database
# ---------------------------------------------------------------------------


@pytest.fixture(name="db")
def _db():
    from database import SessionLocal

    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.mark.parametrize("question_key", sorted(ax.QUESTIONS))
def test_every_question_builds_a_coherent_answer(db, question_key):
    window = ax._resolve_window("2026-01-01", "2026-07-27")
    answer = ax.QUESTIONS[question_key].build(db, window, ax._resolve_scope(None, None))

    assert answer.chart_type in {"bar", "line"}
    assert answer.records >= 0
    assert all(c.value >= 0 for c in answer.categories)

    # Every explanatory field must be populated in both languages — this is the
    # whole point of the surface.
    for label in (answer.headline, answer.what, answer.how, answer.origin, answer.excluded):
        assert label.ar.strip(), f"{question_key}: empty Arabic"
        assert label.en.strip(), f"{question_key}: empty English"

    # Next steps must point at questions that actually exist.
    for step in answer.next_steps:
        assert step.question in ax.QUESTIONS, f"{question_key} links to a missing question"


def test_records_and_groups_are_distinct_measures(db):
    """The legacy page displayed the number of bars under the word "records"."""
    window = ax._resolve_window("2026-07-01", "2026-07-27")
    answer = ax.QUESTIONS["incidents_by_type"].build(db, window, ax._resolve_scope(None, None))

    # records is the sum over the groups, never the count of them.
    assert answer.records == sum(c.value for c in answer.categories)


def test_daily_series_has_no_gaps(db):
    """A day with zero incidents must appear as zero, not vanish from the axis."""
    window = ax._resolve_window("2026-07-01", "2026-07-27")
    answer = ax.QUESTIONS["incidents_over_time"].build(db, window, ax._resolve_scope(None, None))

    expected_days = (window.end - window.start).days + 1
    assert len(answer.categories) == expected_days
    assert answer.categories[0].key == "2026-07-01"
    assert answer.categories[-1].key == "2026-07-27"


def _payload(db, question="incidents_by_type"):
    """Invoke the endpoint directly.

    Calling the function bypasses FastAPI's dependency injection, so the optional
    filters must be supplied explicitly — otherwise they arrive as ``Query`` marker
    objects rather than ``None``.
    """
    return ax.answer_question(
        question=question,
        date_from="2026-07-01",
        date_to="2026-07-27",
        governorate=None,
        kindergarten_id=None,
        db=db,
    )


def test_unknown_question_is_rejected(db):
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc:
        _payload(db, question="not_a_real_question")
    assert exc.value.status_code == 404


def test_as_of_is_reported_in_jordan_time(db):
    as_of = datetime.fromisoformat(_payload(db)["coverage"]["as_of"])
    assert as_of.tzinfo is not None, "as_of must be timezone-aware"
    assert as_of.utcoffset() == timedelta(hours=3), "as_of must be Jordan time (UTC+3)"


def test_governorate_scoping_partitions_the_national_total(db):
    """Every governorate's slice must sum to the national figure — no row lost, none double-counted."""
    window = ax._resolve_window("2026-01-01", "2026-07-27")
    build = ax.QUESTIONS["incidents_by_type"].build

    national = build(db, window, ax._resolve_scope(None, None)).records
    governorates = [
        row[0]
        for row in db.query(models.Kindergarten.governorate)
        .filter(models.Kindergarten.deleted_at.is_(None))
        .distinct()
        .all()
        if row[0]
    ]
    per_governorate = sum(
        build(db, window, ax._resolve_scope(gov, None)).records for gov in governorates
    )
    assert per_governorate == national


def test_kindergarten_label_does_not_repeat_the_word_kindergarten(db):
    kg = db.query(models.Kindergarten).filter(models.Kindergarten.deleted_at.is_(None)).first()
    label = ax._resolve_scope(None, kg.id).label(db)
    assert label.ar.count("حضانة") == 1, label.ar
    assert label.en.lower().count("kindergarten") == 1, label.en


def test_kindergarten_list_narrows_with_the_governorate(db):
    everywhere = ax.list_kindergartens(governorate=None, db=db)["kindergartens"]
    assert everywhere, "the fixture database should contain kindergartens"
    for kg in everywhere:
        assert set(kg["name"]) == {"ar", "en"}, "options must be bilingual"
        assert kg["name"]["ar"].strip() and kg["name"]["en"].strip()

    gov = db.query(models.Kindergarten.governorate).filter(
        models.Kindergarten.deleted_at.is_(None)
    ).first()[0]
    scoped = ax.list_kindergartens(governorate=gov, db=db)["kindergartens"]
    assert 0 < len(scoped) <= len(everywhere)


def test_answer_payload_is_fully_bilingual(db):
    payload = _payload(db)
    for section in (payload["headline"], payload["coverage"]["period"], payload["coverage"]["scope"]):
        assert set(section) == {"ar", "en"}
    for value in payload["explanation"].values():
        assert set(value) == {"ar", "en"}
    for category in payload["chart"]["categories"]:
        assert set(category["label"]) == {"ar", "en"}
