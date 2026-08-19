"""The contrast harness's compositor, pinned by its own failure history.

Every rule in this file exists because the compositor got that exact case wrong
and reported a number anyway. That is the failure mode worth guarding: it never
crashed, it produced clean-looking output while quietly excluding the surfaces
most likely to fail.

The history, in order:

  1. Any element over a `background-image` was reported "indeterminate" and
     skipped -- 29 nodes on /admin/heatmap, 69 on /services. Nearly every dark
     panel in this product is a gradient, so a large share of the UI had never
     been measured. Hidden behind that label: a 1.42:1 sign-in button, a 1.02:1
     user name, a 1.19:1 CTA in the shared navbar.

  2. The first fix flattened every `rgba()` in the whole background-image
     property into one list of stops. That broke on LAYERED backgrounds: the
     /my-reports hero is

         radial-gradient(..., rgba(201,135,67,.2), transparent 28%),
         linear-gradient(135deg, #163d2e, #1f5e47, #2f7d62)

     and the top layer's `transparent` was composited against the page canvas
     instead of revealing the dark green underneath it. The harness declared the
     dark hero near-white and its white heading 1.05:1 -- a harness bug that
     would have been "fixed" by making white text on a dark hero darker still.

  3. A parent that was itself a gradient returned `{grounds: [...]}` while the
     child read `behind.rgb`, which is undefined -- a TypeError mid-audit.

So: layers composite bottom-up, transparency reveals what is beneath, and the
worst stop wins because text over a gradient has to be legible against all of
it.

These run headless against `data:` documents. No server, no fixtures, so there
is no path where they quietly skip.
"""
import pytest

HARNESS_IMPORT_ERROR = None
try:
    from tests.browser.audit_harness import CONTRAST_JS
except Exception:  # pragma: no cover - exercised only when vendoring changes
    try:
        import sys
        from pathlib import Path

        sys.path.insert(0, str(Path(__file__).resolve().parent / "browser"))
        from audit_harness import CONTRAST_JS
    except Exception as exc:
        CONTRAST_JS = None
        HARNESS_IMPORT_ERROR = exc


def _measure(html):
    """Run the real CONTRAST_JS over a synthetic document."""
    if CONTRAST_JS is None:
        pytest.fail(f"the audit harness could not be imported: {HARNESS_IMPORT_ERROR}")
    pw = pytest.importorskip("playwright.sync_api")
    with pw.sync_playwright() as p:
        b = p.chromium.launch()
        try:
            pg = b.new_page()
            pg.set_content(html)
            pg.wait_for_timeout(120)
            return pg.evaluate(CONTRAST_JS)
        finally:
            b.close()


# --------------------------------------------------------------------------
# The critical regression control: transparency over a dark layer.
# --------------------------------------------------------------------------

LAYERED_DARK = """<!doctype html><html lang="ar" dir="rtl"><head><style>
  body { background: #faf9f6; margin: 0; }
  .hero {
    padding: 40px;
    background:
      radial-gradient(circle at top left, rgba(201,135,67,0.2), transparent 28%),
      linear-gradient(135deg, #163d2e 0%, #1f5e47 55%, #2f7d62 100%);
  }
  .hero h2 { color: #ffffff; font-size: 28px; margin: 0; }
</style></head><body>
  <section class="hero"><h2>رؤية أوضح ليوم أطفالك</h2></section>
</body></html>"""


def test_transparent_top_layer_reveals_the_layer_beneath_not_the_page():
    """White on a dark hero must pass, even under a transparent top layer.

    This is the /my-reports case verbatim. If the compositor regresses to
    flattening layers, the top gradient's `transparent` stop composites against
    the near-white body and this white heading is reported at ~1.05:1 -- and
    someone "fixes" a dark hero by darkening its text.
    """
    data = _measure(LAYERED_DARK)
    fails = [f for f in data["fails"] if "رؤية" in f["text"]]
    assert not fails, (
        "white text on a DARK layered hero was reported as a contrast failure: "
        f"{fails}. The top layer is transparent over #163d2e-#2f7d62; a "
        "transparent stop must reveal the layer beneath it, not the page canvas."
    )
    assert data["indeterminate"] == 0, (
        "the layered hero was reported indeterminate; gradients with parseable "
        "colour stops must be measured, not skipped"
    )


# --------------------------------------------------------------------------
# The opposite control: a genuinely light gradient must still fail.
# --------------------------------------------------------------------------

LIGHT_GRADIENT = """<!doctype html><html lang="en"><head><style>
  body { background: #ffffff; margin: 0; }
  .band { padding: 40px; background: linear-gradient(135deg, #ff9c6c 0%, #ffd36b 100%); }
  .band span { color: #ffffff; font-size: 16px; }
</style></head><body>
  <div class="band"><span>Sign in</span></div>
</body></html>"""


def test_white_on_a_light_gradient_is_still_caught():
    """The sign-in button case: white on gold, measured at 1.42:1 in production.

    Without this, a compositor that returned "indeterminate" for everything --
    or that always picked the darkest imaginable ground -- would pass the test
    above while detecting nothing at all.
    """
    data = _measure(LIGHT_GRADIENT)
    hits = [f for f in data["fails"] if f["text"].strip() == "Sign in"]
    assert hits, (
        "white text on a #ff9c6c-#ffd36b gradient was NOT flagged. That is the "
        "exact defect this compositor was written to find; if it passes here, a "
        "clean sweep means nothing."
    )
    assert hits[0]["ratio"] < 2.5, f"expected a severe failure, got {hits[0]}"


def test_worst_stop_wins_across_a_mixed_gradient():
    """A gradient running dark to light must be judged by its light end.

    Text has to be legible over the whole gradient, not its midpoint. A
    compositor that averaged the stops would pass this and ship unreadable text
    at one end of the band.
    """
    html = """<!doctype html><html lang="en"><head><style>
      body { background: #ffffff; margin: 0; }
      .band { padding: 30px; background: linear-gradient(90deg, #0b1524 0%, #ffe07c 100%); }
      .band span { color: #ffffff; font-size: 16px; }
    </style></head><body><div class="band"><span>Mixed</span></div></body></html>"""
    data = _measure(html)
    hits = [f for f in data["fails"] if f["text"].strip() == "Mixed"]
    assert hits, (
        "white over a gradient whose light end is #ffe07c was not flagged -- the "
        "compositor is not taking the worst stop"
    )


# --------------------------------------------------------------------------
# Structural controls: nesting, and things that are genuinely unknowable.
# --------------------------------------------------------------------------

def test_a_gradient_inside_a_gradient_does_not_crash():
    """Nested gradients used to raise a TypeError mid-audit.

    `backing()` returned {grounds:[...]} for the parent while the child read
    `behind.rgb`. The audit died partway through and the surface silently went
    unmeasured.
    """
    html = """<!doctype html><html lang="en"><head><style>
      body { background: #ffffff; margin: 0; }
      /* Deliberately dark at BOTH ends. An earlier draft ended at #2f7d62,
         which a 12% white veil lifts to rgb(72,141,117) -- white on that is
         3.95:1, so the compositor was right and the fixture was wrong. Kept as
         a note because it is the same trap the product hit. */
      .outer { padding: 30px; background: linear-gradient(135deg, #0b1524, #163d2e); }
      .inner { padding: 20px; background: linear-gradient(180deg, rgba(255,255,255,.12), transparent); }
      .inner span { color: #ffffff; font-size: 16px; }
    </style></head><body>
      <div class="outer"><div class="inner"><span>Nested</span></div></div>
    </body></html>"""
    data = _measure(html)  # must not raise
    assert data["indeterminate"] == 0
    assert not [f for f in data["fails"] if f["text"].strip() == "Nested"], (
        "white on a translucent panel over a dark gradient should pass"
    )


def test_an_unparseable_background_image_stays_indeterminate():
    """A photo or url() has no colour stops, so it is honestly unknowable.

    The compositor must keep saying so rather than inventing a ground. Guessing
    here would be worse than skipping: it would produce confident numbers about
    text over an image nobody measured.
    """
    html = """<!doctype html><html lang="en"><head><style>
      body { background: #ffffff; margin: 0; }
      .photo { padding: 30px;
        background-image: url('data:image/gif;base64,R0lGODlhAQABAIAAAP///wAAACH5BAEAAAAALAAAAAABAAEAAAICRAEAOw=='); }
      .photo span { color: #9a9a9a; font-size: 16px; }
    </style></head><body><div class="photo"><span>Over an image</span></div></body></html>"""
    data = _measure(html)
    assert data["indeterminate"] >= 1, (
        "text over a raster background was given a definite contrast ratio; a "
        "bitmap has no single colour and must stay indeterminate"
    )


# --------------------------------------------------------------------------
# `none` is a layer that paints nothing -- not an image nobody can read.
# --------------------------------------------------------------------------

NONE_LAYER = """<!doctype html><html lang="ar" dir="rtl"><head><style>
  body { background: #faf9f6; margin: 0; }
  .admin-page-header {
    padding: 32px;
    background-image: linear-gradient(135deg, #0b1524 0%, #163d2e 100%), none;
  }
  .admin-page-header h1 { color: #ffffff; font-size: 24px; margin: 0; }
  .admin-page-header p  { color: #e2e8f0; font-size: 15px; margin: 8px 0 0; }
</style></head><body>
  <header class="admin-page-header">
    <h1>لوحة التحكم</h1><p>نظرة عامة على النشاط</p>
  </header>
</body></html>"""


def test_a_none_layer_does_not_make_the_whole_stack_indeterminate():
    """The /admin/dashboard case: `linear-gradient(...), none`.

    `none` is a perfectly parseable layer that contributes nothing. Treating it
    as an unreadable image made layerStops bail for the entire element, so the
    header came back indeterminate -- 2 nodes per engine, on all three engines,
    never measured at all. Indeterminate must mean "genuinely unknowable", or
    it becomes a place for real surfaces to hide.
    """
    data = _measure(NONE_LAYER)
    assert data["indeterminate"] == 0, (
        "a background-image whose only unparseable layer is the literal `none` "
        "was reported indeterminate; `none` paints nothing and must be dropped, "
        "not treated as an opaque texture"
    )
    hits = [f for f in data["fails"] if "لوحة" in f["text"] or "نظرة" in f["text"]]
    assert not hits, (
        f"light text on a dark header was flagged as failing: {hits}. If the "
        "`none` layer were composited as a ground, the dark gradient beneath it "
        "would be lost."
    )


def test_a_real_image_layer_still_bails():
    """Control: dropping `none` must not make url() readable by accident."""
    html = """<!doctype html><html lang="en"><head><style>
      body { background: #ffffff; margin: 0; }
      .hero { padding: 30px;
        background-image: linear-gradient(135deg, #0b1524, #163d2e),
          url('data:image/gif;base64,R0lGODlhAQABAIAAAP///wAAACH5BAEAAAAALAAAAAABAAEAAAICRAEAOw=='); }
      .hero span { color: #9a9a9a; font-size: 16px; }
    </style></head><body><div class="hero"><span>Over an image</span></div></body></html>"""
    data = _measure(html)
    assert data["indeterminate"] >= 1, (
        "a real raster layer stopped being reported as indeterminate; only the "
        "literal `none` may be dropped"
    )
