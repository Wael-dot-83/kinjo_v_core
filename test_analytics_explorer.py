"""Tests for the guided analytics explorer.

These lock down the four correctness properties the module exists to guarantee,
each of which is a defect in the legacy ``charts_api`` path:

  1. The reporting window includes events occurring *during* the final day.
  2. ``records`` (rows counted) and ``groups`` (bars drawn) are reported separately.
  3. ``as_of`` is Jordan time, not naive server time and not UTC.
  4. Every operator-visible string carries both an Arabic and an English variant.
"""

from datetime import date, datetime, timedelta
from pathlib import Path

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


def test_an_absurd_window_is_refused_rather_than_served():
    """`date_from=1900-01-01&date_to=2100-01-01` produced a 73,000-point, 6.3 MB response."""
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc:
        ax._resolve_window("1900-01-01", "2100-01-01")
    assert exc.value.status_code == 422
    assert "maximum" in str(exc.value.detail)


@pytest.mark.parametrize(
    "start,end,expected",
    [
        ("2026-07-01", "2026-07-27", "day"),
        ("2026-06-01", "2026-07-27", "day"),
        ("2026-01-01", "2026-07-27", "week"),
        ("2020-01-01", "2026-07-27", "month"),
    ],
)
def test_bucket_widens_with_the_window(start, end, expected):
    assert ax._resolve_window(start, end).bucket == expected


def test_time_series_stays_bounded_across_the_whole_legal_range(db):
    """Even at the maximum window the series must stay small enough to render."""
    window = ax._resolve_window("2016-08-01", "2026-07-27")
    answer = ax.QUESTIONS["incidents_over_time"].build(db, window, ax._resolve_scope(None, None))
    assert window.bucket == "month"
    assert len(answer.categories) <= 130, "a decade of months, not a decade of days"


# ---------------------------------------------------------------------------
# 2. Scope resolution
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "supplied", ["amman", "Amman", "AMMAN", " amman ", "عمان", "العاصمة", "عاصمة"]
)
def test_every_accepted_form_of_the_capital_resolves_to_one_identity(supplied):
    """Identity comes from the canonical registry, not from a local table.

    The capital is persisted either as the canonical governorate name "العاصمة" or as
    the legacy city-name form "عمان" that migration canon_gov_cap_01 corrects. Every
    accepted input must collapse to a single key whose filter matches both, so the
    result is identical on a migrated and an un-migrated database.
    """
    scope = ax._resolve_scope(supplied, None)
    assert scope.governorate_key == "amman"
    assert scope.governorate == "العاصمة"
    stored_forms = set(scope.governorate_names)
    assert {"عمان", "العاصمة"} <= stored_forms


def test_governorate_names_come_from_the_canonical_registry():
    """No governorate knowledge may be hardcoded in this module."""
    from services.jordan_locations import governorate_query_aliases

    for value in ["إربد", "irbid", "العقبة", "الزرقاء"]:
        assert list(ax._resolve_scope(value, None).governorate_names) == governorate_query_aliases(value)

    # No governorate name may appear as a *live string literal* — prose in comments
    # and docstrings explaining the design is fine, a hardcoded lookup value is not.
    import ast

    from services.jordan_locations import get_all_governorates

    tree = ast.parse((Path(__file__).parent / "analytics_explorer.py").read_text(encoding="utf-8"))
    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            doc = ast.get_docstring(node, clean=False)
            if doc:
                docstrings.add(doc)

    literals = [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and node.value not in docstrings
    ]
    canonical_names = {g["name_ar"] for g in get_all_governorates()}
    leaked = sorted({name for name in canonical_names for lit in literals if name in lit})
    assert not leaked, f"governorate names hardcoded in analytics_explorer.py: {leaked}"


def test_an_unknown_governorate_is_rejected_rather_than_silently_empty():
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc:
        ax._resolve_scope("Atlantis", None)
    assert exc.value.status_code == 422


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


def test_a_nonexistent_kindergarten_is_404_not_an_empty_answer(db):
    """Answering "0 incidents" for a bad id reads as a clean safety record."""
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc:
        ax.answer_question(
            question="incidents_by_type",
            date_from="2026-07-01",
            date_to="2026-07-27",
            governorate=None,
            kindergarten_id=999_999,
            db=db,
        )
    assert exc.value.status_code == 404


def test_as_of_is_reported_in_jordan_time(db):
    as_of = datetime.fromisoformat(_payload(db)["coverage"]["as_of"])
    assert as_of.tzinfo is not None, "as_of must be timezone-aware"
    assert as_of.utcoffset() == timedelta(hours=3), "as_of must be Jordan time (UTC+3)"


@pytest.mark.parametrize(
    "question_key",
    ["incidents_by_type", "incidents_by_severity", "incidents_over_time", "enrollment_status"],
)
def test_governorate_scoping_partitions_the_national_total(db, question_key):
    """Every governorate's slice must sum to the national figure.

    No row lost, none double-counted, for every question that supports geography —
    not only for incidents and not only for the capital.
    """
    window = ax._resolve_window("2026-01-01", "2026-07-27")
    build = ax.QUESTIONS[question_key].build

    national = build(db, window, ax._resolve_scope(None, None)).records
    per_governorate = sum(
        build(db, window, ax._resolve_scope(g["key"], None)).records
        for g in ax._available_governorates(db)
    )
    assert per_governorate == national


def test_partition_holds_when_both_capital_spellings_coexist(db):
    """The hazard case: a half-migrated database holding عمان AND العاصمة.

    Folding onto the canonical key must merge them into one governorate. Treating
    them as two would double-count every capital row.
    """
    ids = [
        row[0]
        for row in db.query(models.Kindergarten.id)
        .filter(models.Kindergarten.governorate.in_(["عمان", "العاصمة"]))
        .all()
    ]
    if len(ids) < 2:
        pytest.skip("fixture needs at least two kindergartens in the capital")

    window = ax._resolve_window("2026-01-01", "2026-07-27")
    build = ax.QUESTIONS["incidents_by_type"].build
    national = build(db, window, ax._resolve_scope(None, None)).records

    try:
        # Split the capital across both spellings.
        db.query(models.Kindergarten).filter(models.Kindergarten.id == ids[0]).update(
            {"governorate": "العاصمة"}, synchronize_session=False
        )
        db.query(models.Kindergarten).filter(models.Kindergarten.id == ids[1]).update(
            {"governorate": "عمان"}, synchronize_session=False
        )
        db.flush()
        db.expire_all()

        options = ax._available_governorates(db)
        keys = [g["key"] for g in options]
        assert keys.count("amman") == 1, "the capital must be offered exactly once"

        assert sum(build(db, window, ax._resolve_scope(k, None)).records for k in keys) == national

        breakdown = ax.QUESTIONS["incidents_by_governorate"].build(
            db, window, ax._resolve_scope(None, None)
        )
        assert [c.key for c in breakdown.categories].count("amman") == 1
        assert sum(c.value for c in breakdown.categories) == national
    finally:
        db.rollback()


def test_a_geography_breakdown_honours_a_geography_filter(db):
    """Scoping to one governorate then asking "which governorate?" must not widen back."""
    window = ax._resolve_window("2026-01-01", "2026-07-27")
    build = ax.QUESTIONS["incidents_by_governorate"].build

    national = build(db, window, ax._resolve_scope(None, None))
    assert len(national.categories) > 1, "fixture needs several governorates"

    scoped = build(db, window, ax._resolve_scope("irbid", None))
    assert [c.key for c in scoped.categories] == ["irbid"]


def test_kindergarten_label_does_not_repeat_the_word_kindergarten(db):
    kg = db.query(models.Kindergarten).filter(models.Kindergarten.deleted_at.is_(None)).first()
    label = ax._resolve_scope(None, kg.id).label(db)
    assert label.ar.count("حضانة") == 1, label.ar
    assert label.en.lower().count("kindergarten") == 1, label.en


def test_kindergarten_list_narrows_with_the_governorate(db):
    body = ax.list_kindergartens(governorate=None, search=None, db=db)
    everywhere = body["kindergartens"]
    assert everywhere, "the fixture database should contain kindergartens"
    for kg in everywhere:
        assert set(kg["name"]) == {"ar", "en"}, "options must be bilingual"
        assert kg["name"]["ar"].strip() and kg["name"]["en"].strip()

    gov = db.query(models.Kindergarten.governorate).filter(
        models.Kindergarten.deleted_at.is_(None)
    ).first()[0]
    scoped = ax.list_kindergartens(governorate=gov, search=None, db=db)["kindergartens"]
    assert 0 < len(scoped) <= len(everywhere)


def test_kindergarten_list_is_capped_and_declares_truncation(db):
    body = ax.list_kindergartens(governorate=None, search=None, db=db)
    assert len(body["kindergartens"]) <= ax._KINDERGARTEN_PICKER_LIMIT
    assert body["truncated"] is (body["total"] > len(body["kindergartens"]))


def test_kindergarten_search_matches_either_language(db):
    kg = db.query(models.Kindergarten).filter(models.Kindergarten.deleted_at.is_(None)).first()
    for term in (kg.name_ar.split()[-1], (kg.name_en or "").split()[0]):
        if not term:
            continue
        found = ax.list_kindergartens(governorate=None, search=term, db=db)["kindergartens"]
        assert any(k["id"] == kg.id for k in found), f"search {term!r} should find {kg.name_ar!r}"


@pytest.mark.parametrize("wildcard", ["%", "_", "%%", "a%b"])
def test_kindergarten_search_treats_like_wildcards_as_literal_text(db, wildcard):
    """Binding stops injection; escaping stops '%' from silently matching everything."""
    everything = ax.list_kindergartens(governorate=None, search=None, db=db)["total"]
    assert everything > 0, "fixture needs kindergartens"

    found = ax.list_kindergartens(governorate=None, search=wildcard, db=db)["total"]
    assert found < everything, f"{wildcard!r} was treated as a wildcard, not as text"


def test_escape_like_neutralises_every_metacharacter():
    assert ax._escape_like("100%") == "100\\%"
    assert ax._escape_like("a_b") == "a\\_b"
    # The escape character itself must be escaped first, or it corrupts the pattern.
    assert ax._escape_like("a\\b") == "a\\\\b"


def test_capacity_reports_kindergartens_not_bars(db):
    """`records` must stay "rows counted"; conflating it with bar count is the core defect."""
    window = ax._resolve_window("2026-01-01", "2026-07-27")
    answer = ax.QUESTIONS["kindergarten_capacity"].build(db, window, ax._resolve_scope(None, None))

    live = (
        db.query(models.Kindergarten)
        .filter(models.Kindergarten.deleted_at.is_(None))
        .count()
    )
    assert answer.records == live
    assert all(0 <= c.value <= 100 for c in answer.categories), "occupancy is a percentage"


def test_governorate_options_are_canonical_and_unique(db):
    body = ax.list_governorates(db=db)["governorates"]
    keys = [g["key"] for g in body]
    assert keys, "fixture needs kindergartens with governorates"
    assert len(keys) == len(set(keys)), "each governorate may appear only once"
    for g in body:
        assert set(g["name"]) == {"ar", "en"}
        assert g["name"]["ar"].strip() and g["name"]["en"].strip()
        # The key must round-trip through scope resolution.
        assert ax._resolve_scope(g["key"], None).governorate_key == g["key"]


@pytest.mark.parametrize(
    "start,end", [("2026-07-01", "2026-07-27"), ("2026-01-01", "2026-07-27"), ("2020-01-01", "2026-07-27")]
)
def test_time_series_explanation_matches_the_bucket_in_both_languages(db, start, end):
    """The wording must describe the grouping actually used, not always say "day"."""
    window = ax._resolve_window(start, end)
    answer = ax.QUESTIONS["incidents_over_time"].build(db, window, ax._resolve_scope(None, None))

    assert answer.category_axis.ar == window.bucket_label().ar
    assert answer.category_axis.en == window.bucket_label().en
    assert window.bucket_label().en.lower() in answer.what.en.lower()
    for text in (answer.what, answer.how, answer.value_axis):
        assert text.ar.strip() and text.en.strip()


def test_answer_payload_is_fully_bilingual(db):
    payload = _payload(db)
    for section in (payload["headline"], payload["coverage"]["period"], payload["coverage"]["scope"]):
        assert set(section) == {"ar", "en"}
    for value in payload["explanation"].values():
        assert set(value) == {"ar", "en"}
    for category in payload["chart"]["categories"]:
        assert set(category["label"]) == {"ar", "en"}
