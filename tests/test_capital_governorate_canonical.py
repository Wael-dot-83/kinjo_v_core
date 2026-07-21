"""Canonical capital-governorate contract, filter alias-awareness, and aggregation merge.

Covers the "العاصمة (governorate) vs عمان (city)" canonicalization:

  Governorate key : amman
  Governorate AR  : العاصمة
  Governorate EN  : Amman
  City AR         : عمان
  Legacy aliases  : عمان, العاصمة, عاصمة, Amman, AMMAN, amman  -> all resolve to amman

These tests assert the *intended* architecture, not the historical defect where the
governorate column held the city name "عمان".
"""
import sqlite3

import pytest

from services.jordan_locations import (
    get_all_governorates,
    get_governorate_by_key,
    get_governorate_by_name,
    get_areas_for_governorate,
    normalize_governorate,
    normalize_governorate_key,
    governorate_name_ar,
    governorate_name_en,
    city_name_ar,
    governorate_display_ar,
    governorate_query_aliases,
)

CAPITAL_ALIASES = ["amman", "Amman", "AMMAN", "عمان", "العاصمة", "عاصمة"]


class TestCanonicalContract:
    def test_governorate_key_is_amman(self):
        assert normalize_governorate_key("العاصمة") == "amman"

    def test_all_aliases_resolve_to_one_key(self):
        keys = {normalize_governorate_key(a) for a in CAPITAL_ALIASES}
        assert keys == {"amman"}

    def test_all_aliases_resolve_to_one_arabic_name(self):
        names = {normalize_governorate(a) for a in CAPITAL_ALIASES}
        assert names == {"العاصمة"}

    def test_canonical_arabic_is_the_capital(self):
        assert governorate_name_ar("amman") == "العاصمة"

    def test_canonical_english_is_amman(self):
        assert governorate_name_en("amman") == "Amman"

    def test_city_amman_is_preserved(self):
        assert city_name_ar("amman", "amman") == "عمان"

    def test_twelve_governorates_capital_once(self):
        names = [g["name_ar"] for g in get_all_governorates()]
        assert len(names) == 12
        assert names.count("العاصمة") == 1

    def test_city_name_is_not_a_governorate(self):
        names = [g["name_ar"] for g in get_all_governorates()]
        assert "عمان" not in names

    def test_city_amman_lives_under_capital_areas(self):
        area_names = [a["name_ar"] for a in get_areas_for_governorate("amman")]
        assert "عمان" in area_names

    def test_lookup_by_legacy_city_name_resolves_to_capital(self):
        g = get_governorate_by_name("عمان")
        assert g is not None
        assert g["key"] == "amman"
        assert g["name_ar"] == "العاصمة"

    def test_display_helper_maps_legacy_value(self):
        assert governorate_display_ar("عمان") == "العاصمة"
        assert governorate_display_ar("Amman") == "العاصمة"


class TestQueryAliases:
    def test_aliases_cover_every_stored_form(self):
        aliases = governorate_query_aliases("العاصمة")
        for form in ["عمان", "العاصمة", "Amman", "amman"]:
            assert form in aliases

    def test_aliases_are_the_same_set_for_every_input_form(self):
        base = set(governorate_query_aliases("العاصمة"))
        for form in CAPITAL_ALIASES:
            assert set(governorate_query_aliases(form)) == base

    def test_unknown_value_returns_itself(self):
        assert governorate_query_aliases("Atlantis") == ["Atlantis"]

    def test_empty_returns_empty(self):
        assert governorate_query_aliases("") == []
        assert governorate_query_aliases(None) == []


class TestFilterServiceAliasAware:
    """The dashboard governorate filter must match rows regardless of which
    legacy form is stored, using stable keys as filter values."""

    def _rows_for(self, gov_filter_value, stored_value):
        import models
        from filter_service import filter_service

        class _FakeCol:
            def __init__(self, name):
                self.name = name
                self.captured = None

            def in_(self, values):
                self.captured = list(values)
                return ("IN", self.name, list(values))

        # Capture what the governorate filter expands to.
        captured = {}

        class _Q:
            def filter(self, *a, **k):
                if a and isinstance(a[0], tuple) and a[0][0] == "IN":
                    captured["values"] = a[0][2]
                return self

        # Monkeypatch the model column with a fake that records .in_()
        real = models.Kindergarten.governorate
        try:
            models.Kindergarten.governorate = _FakeCol("governorate")
            q = _Q()

            class _User:
                role = models.UserRole.ADMIN
                kindergarten_id = None

            filter_service.apply_filters_to_query(q, {"governorates": [gov_filter_value]}, _User())
        finally:
            models.Kindergarten.governorate = real
        return captured.get("values", [])

    def test_key_filter_expands_to_all_aliases(self):
        values = self._rows_for("amman", "العاصمة")
        assert "العاصمة" in values
        assert "عمان" in values

    def test_legacy_name_filter_expands_to_all_aliases(self):
        values = self._rows_for("عمان", "العاصمة")
        assert "العاصمة" in values


class TestAggregationMerge:
    """Mixed legacy governorate values must aggregate into ONE capital bucket
    once normalized/migrated — never split into عمان and العاصمة separately."""

    def test_group_by_after_normalization_is_single_bucket(self):
        # Simulate the migration's canonicalization on an in-memory table.
        con = sqlite3.connect(":memory:")
        con.execute("CREATE TABLE kg (governorate TEXT, district TEXT)")
        rows = [
            ("عمان", "عمان"),
            ("العاصمة", "عمان"),
            ("Amman", "عمان"),
            ("amman", "الجبيهة"),
            ("إربد", "الرمثا"),
        ]
        con.executemany("INSERT INTO kg VALUES (?, ?)", rows)
        con.commit()

        # Apply the same scoped, governorate-only canonicalization the migration does.
        legacy = ("عمان", "عاصمة", "Amman", "amman", "AMMAN")
        placeholders = ",".join("?" for _ in legacy)
        con.execute(
            f"UPDATE kg SET governorate='العاصمة' WHERE governorate IN ({placeholders})",
            legacy,
        )
        con.commit()

        gov_counts = dict(con.execute("SELECT governorate, COUNT(*) FROM kg GROUP BY governorate").fetchall())
        assert gov_counts["العاصمة"] == 4  # all four capital forms merged, none lost
        assert gov_counts["إربد"] == 1
        assert "عمان" not in gov_counts  # no split capital bucket

        # City column (district) is untouched: "عمان" the city is preserved.
        districts = dict(con.execute("SELECT district, COUNT(*) FROM kg GROUP BY district").fetchall())
        assert districts["عمان"] == 3
        con.close()

    def test_no_double_counting(self):
        # Normalizing keys must be a function (idempotent): each value maps to exactly one key.
        values = ["عمان", "العاصمة", "Amman", "amman", "عاصمة"]
        keys = [normalize_governorate_key(v) for v in values]
        assert keys == ["amman"] * len(values)


class TestMigrationModuleShape:
    def test_migration_is_scoped_and_reversible(self):
        import importlib.util
        from pathlib import Path

        path = Path(__file__).resolve().parents[1] / "alembic" / "versions" / "canon_gov_cap_01_canonicalize_capital_governorate.py"
        spec = importlib.util.spec_from_file_location("canon_gov_cap_01", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        # Only governorate-context tables are touched — never district/area.
        assert set(mod._TABLES) == {"kindergartens", "reports"}
        assert mod._CANONICAL_AR == "العاصمة"
        assert "عمان" in mod._LEGACY_FORMS
        assert callable(mod.upgrade) and callable(mod.downgrade)
        assert mod.down_revision == "c7d9e1a4b820"
