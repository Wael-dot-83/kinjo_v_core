"""The heat-map's average-risk card must not claim coverage the service lacks.

`get_map_overview()` builds the payload by looping the 12 governorates and
wrapping each in `except Exception -> logger.warning`, dropping the ones that
raise. `average_risk` is then `overall_risk_total / max(len(governors), 1)` —
divided by the SURVIVORS. So a single failing governorate yields an
11-governorate mean that any "national"/"all 12" wording would misrepresent,
with a 200 and no other signal.

This card has carried a false claim three times (a selected scope that does not
exist in the payload; then a tooltip and sub-label propagating it; then
"across all 12 governorates"). These tests bind the copy to what the service
actually computes, so the next edit has to reckon with the failure path instead
of rediscovering it.
"""
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
HEATMAP = ROOT / "templates" / "admin" / "heatmap.html"


def _card_containing(marker: str) -> str:
    """The whole KPI card holding `marker` — label, value and sub-label.

    Spans start-of-card to start-of-next-card rather than to the first
    </div> (which closes the value div and hides the sub-label) or a fixed
    character count (which silently truncates when an attribute grows).
    """
    html = HEATMAP.read_text(encoding="utf-8")
    idx = html.index(marker)
    start = html.rindex('<div class="kpi-card', 0, idx)
    nxt = html.find('<div class="kpi-card', idx)
    return html[start:nxt if nxt != -1 else len(html)]


def _card() -> str:
    return _card_containing('id="kpiAvgRisk"')


def test_average_risk_card_does_not_claim_completeness_or_scope():
    """The words the service cannot support, in either language."""
    card = _card()
    for banned in (
        "Selected-scope Average Risk",   # no scope exists in the payload
        "all 12 governorates",           # the divisor is the survivors
        "المحافظات الاثنتي عشرة",
        "National average",              # implies coverage that can be partial
        "المتوسط الوطني",
    ):
        assert banned not in card, (
            f"the average-risk card claims {banned!r}, which get_map_overview() "
            f"does not guarantee: it drops governorates whose sub-indicators "
            f"raise and averages only the survivors.\ncard: {card}"
        )


def test_average_risk_card_points_at_the_covered_set_in_both_languages():
    card = _card()
    assert "across covered governorates" in card
    assert "للمحافظات المغطاة" in card
    # The limitation itself must be stated, not merely implied by omission.
    assert "fewer than 12 if any governorate could not be computed" in card
    assert "يقل عددها عن 12" in card


def test_the_service_really_can_drop_a_governorate():
    """Anti-vacuity for the tests above: if the service could not produce a
    partial average, the wording would be pedantry rather than accuracy.

    Asserts the two mechanics the copy depends on: failures are swallowed
    per-governorate, and the divisor is the surviving count.
    """
    service = (ROOT / "heatmap" / "backend" / "service.py").read_text(encoding="utf-8")
    overview = service[service.index("def get_map_overview"):]
    overview = overview[: overview.index("\ndef ")]

    assert "except Exception" in overview, (
        "get_map_overview no longer swallows per-governorate failures — if it "
        "now fails loudly or fills a default, the card's 'covered' wording "
        "should be revisited rather than left stale"
    )
    assert "max(len(governors), 1)" in overview, (
        "the average is no longer divided by the surviving governorate count; "
        "re-derive what the card may claim"
    )


def test_covered_card_still_discloses_the_denominator():
    """The avg-risk card defers to this one for the actual number."""
    covered_card = _card_containing('id="kpiCovered"')
    assert "of 12 governorates" in covered_card
    assert "من 12 محافظة" in covered_card


def test_total_facilities_card_matches_what_kg_count_counts():
    """The card must not claim nurseries, nor an 'active' subset.

    kg_count is sub["active_nurseries"], but that key is fed by
    _query_kindergarten_count(): COUNT(Kindergarten.id) filtered ONLY by
    governorate — no status filter — so the number is the registered count and
    "active" would be the wrong word. The value also sums the same surviving
    governorate list as the average-risk card, hence the coverage caveat.

    "nurseries" is dropped because no nursery type exists to count:
    models.Kindergarten has no type/category column.
    """
    card = _card_containing('id="kpiInstitutions"')
    assert "and nurseries" not in card, (
        "the English tooltip still claims nurseries while the sub-label says "
        "Kindergartens — the card contradicts itself in English only"
    )
    assert "KGs & nurseries" not in card
    assert "حضانة وحضانة" not in card
    assert "in the covered governorates" in card
    assert "في المحافظات المغطاة" in card


def test_kg_count_really_has_no_status_filter():
    """Anti-vacuity for the wording above: if a status filter appears, the card
    should say 'active', and this test should fail rather than let the copy go
    quietly stale."""
    service = (ROOT / "heatmap" / "backend" / "service.py").read_text(encoding="utf-8")
    fn = service[service.index("def _query_kindergarten_count"):]
    fn = fn[: fn.index("\ndef ")]
    assert "Kindergarten.governorate.in_(names)" in fn
    assert "status" not in fn, (
        "_query_kindergarten_count now filters by status, so the Total "
        "Facilities card's 'registered' wording is no longer accurate"
    )
