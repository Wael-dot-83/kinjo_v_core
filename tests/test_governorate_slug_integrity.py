"""Governorate slug/name integrity across the heatmap and config subsystems.

The response model once declared `tafilah` while the canonical heatmap slug is
`tafileh`, producing a permanent empty phantom entry. These tests pin a single
source of truth and prove the two subsystems' English spellings ("Tafileh" vs
config's "Tafilah") cannot silently drift a governorate's data out of the query.
"""
import pytest

from config import settings
from heatmap.backend import constants as C
from heatmap.backend.service import _names_for_slug

CANONICAL_SLUGS = {
    "amman", "irbid", "zarqa", "aqaba", "mafraq", "jerash",
    "ajloun", "tafileh", "karak", "maan", "balqa", "madaba",
}


def test_exactly_twelve_canonical_governorates():
    slugs = {g["slug"] for g in C.GOVERNORATES}
    assert len(C.GOVERNORATES) == 12
    assert slugs == CANONICAL_SLUGS, (
        f"governorate slug set drifted: {slugs ^ CANONICAL_SLUGS}"
    )


def test_response_model_matches_canonical_slugs():
    from admin_endpoints import HeatmapGovernorateData

    declared = set(HeatmapGovernorateData.model_fields)
    canonical = {g["slug"] for g in C.GOVERNORATES}
    assert declared == canonical, (
        f"schema/constants drift — only in schema: {sorted(declared - canonical)}; "
        f"only in constants: {sorted(canonical - declared)}"
    )


def test_tafileh_is_the_canonical_slug_not_tafilah():
    slugs = {g["slug"] for g in C.GOVERNORATES}
    assert "tafileh" in slugs
    assert "tafilah" not in slugs


@pytest.mark.parametrize("slug", sorted(CANONICAL_SLUGS))
def test_every_slug_resolves_to_name_variants(slug):
    variants = _names_for_slug(slug)
    assert variants, f"{slug} resolved to no name variants"
    g = C.GOVERNORATE_BY_SLUG[slug]
    assert g["name_en"] in variants
    assert g["name_ar"] in variants


def test_names_for_slug_bridges_both_english_spellings_of_tafileh():
    """Tafileh/Tafilah: the heatmap must match data stored under either spelling.

    The heatmap uses "Tafileh"; config.JORDAN_GOVERNORATES_ENGLISH uses "Tafilah".
    Both, plus the shared Arabic name, must be in the query variant set or a
    kindergarten stored under the config spelling would be invisible.
    """
    variants = set(_names_for_slug("tafileh"))
    assert "Tafileh" in variants  # heatmap spelling
    assert "Tafilah" in variants  # config spelling, bridged via the Arabic name
    assert "الطفيلة" in variants  # shared Arabic name


def test_config_english_spellings_are_all_bridged():
    """Every config English governorate name must be reachable from some slug's
    variant set, so no governorate's stored data can fall through the heatmap."""
    covered = set()
    for g in C.GOVERNORATES:
        covered.update(_names_for_slug(g["slug"]))
    missing = [en for en in settings.JORDAN_GOVERNORATES_ENGLISH if en not in covered]
    assert not missing, f"config English names not bridged into any slug: {missing}"
