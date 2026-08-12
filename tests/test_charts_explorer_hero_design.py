"""Centred hero and the source-spectrum legend on the charts explorer."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "templates" / "admin" / "analytics" / "charts_dashboard.html"

SOURCES = ("incidents", "attendance", "daily_reports", "enrollments", "kindergartens")


def _html() -> str:
    return TEMPLATE.read_text(encoding="utf-8")


def test_hero_is_centred():
    html = _html()
    assert "ce-hero" in html
    # Two rules open with `.ce-hero {` -- the shared token block and the layout
    # rule. The layout one is last.
    block = html.rsplit(".ce-hero {", 1)[1].split("}", 1)[0]
    assert "text-align: center" in block
    assert "margin: 0 auto" in block


def test_hero_keeps_both_languages():
    html = _html()
    assert "مستكشف الرسوم البيانية" in html
    assert "Charts Explorer" in html
    assert "استكشاف تحليلي تفاعلي" in html


def test_title_scales_with_the_viewport():
    """A fixed display size either overflows on mobile or looks timid on
    desktop."""
    block = _html().split(".ce-hero__title {", 1)[1].split("}", 1)[0]
    assert "clamp(" in block


def test_spectrum_covers_every_source():
    """The spectrum is the page's legend, so a source missing from it would
    leave that colour unexplained."""
    html = _html()
    for src in SOURCES:
        assert f'data-src="{src}"' in html
        assert f'.ce-spectrum__seg[data-src="{src}"]' in html


def test_spectrum_tracks_the_selected_source():
    html = _html()
    assert "seg.dataset.src === source" in html
    assert ".ce-spectrum__seg.is-active" in html


def test_spectrum_is_decorative_to_screen_readers():
    """It restates the selected source, which is already announced by the
    source control itself."""
    block = _html().split('id="ceSpectrum"', 1)[0][-120:]
    assert 'aria-hidden="true"' in _html().split('id="ceSpectrum"', 1)[1][:80] or 'aria-hidden' in block


def test_each_source_owns_one_hue_everywhere():
    """A colour must mean the same thing in the spectrum, the source card and
    the figure."""
    html = _html()
    for src in SOURCES:
        assert f'.ce-source-card[data-source="{src}"]' in html
        assert f"{src}:" in html.split("SOURCE_HUES = {", 1)[1].split("}", 1)[0]


def test_figure_leads_with_the_active_source_colour():
    html = _html()
    assert "colorway: sourceColorway(data.source)" in html
    body = html.split("function sourceColorway", 1)[1].split("\n  function ", 1)[0]
    assert "[lead].concat" in body          # active hue first, no duplicate


def test_motion_is_optional():
    html = _html()
    assert "prefers-reduced-motion" in html
    block = html.split("@media (prefers-reduced-motion: reduce) {", 1)[1].split("}", 1)[0]
    assert "transition: none" in block
