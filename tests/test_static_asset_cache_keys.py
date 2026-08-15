"""Immutable static assets must get a new cache key when their bytes change.

Production serves /static/* with `cache-control: public, max-age=31536000,
immutable`, so a changed file behind an unchanged ?v= is invisible to every
browser and to the CDN edge for a year.

This is written from a release that failed exactly that way. c12ea5e changed
static/css/admin_design_system.css (three surface fixes, five foreground
fixes and an explicit .ce-data-table background) but left both templates
referencing ?v=3.2. The deployed containers ran the exact tested tree, yet the
canonical user-facing URL kept serving the pre-release bytes:

    admin_design_system.css?v=3.2
        live   b23ae7d2...  157,802 bytes   cf-cache-status: HIT
        tested 736497f3...  158,316 bytes

The visible symptom was the Charts Explorer data table staying white in dark
mode while every other repaired surface went dark.

An earlier guard existed but was scoped to design-tokens.css by name, so it
could not see the next asset to change. The preflight below therefore
discovers changed assets from the Git diff instead of from a hardcoded list.

This file is also a cautionary record of the guard's own blind spots, because
each one produced a green test over a real release:

  * the matcher read `href=` only, so every `<script src=...>` reference —
    i.e. every JS asset — was invisible to both the consistency contract and
    the preflight. The language-preference fix changed four JS files; none of
    those bumps was ever verified until the matcher learned `src=`.
  * the ref-scoped lookup hardcoded three shell templates while the worktree
    model globbed every template, so an asset referenced from any other
    template read as "no previous reference" at the base.
  * `stalled_assets` skipped assets with no reference in the worktree
    (`if not after: continue`), so a changed asset whose references vanished
    silently passed. Empty is now an explicit state.
"""
import functools
import os
import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "templates"

# Assets whose reference consistency is contractually protected. Membership is
# about "referenced from more than one shell", not about who changed last.
SHARED_ASSETS = ["design-tokens.css", "admin_design_system.css"]

# Both href= (stylesheet links) and src= (script tags) feed the one
# asset-keyed model. A matcher that only read href= could not see a single
# JS asset: `<script src="/static/js/x.js?v=1">` went unmatched, so the
# preflight never compared the key of any changed .js file.
REF = re.compile(r'(?:href|src)="/static/(css|js)/([a-z0-9_.-]+\.(?:css|js))(?:\?v=([^"]*))?"')


def _references():
    """{asset: {version: [templates]}} across every template."""
    out = {}
    for tpl in sorted(TEMPLATES.rglob("*.html")):
        for m in REF.finditer(tpl.read_text(encoding="utf-8")):
            out.setdefault(m.group(2), {}).setdefault(m.group(3), []).append(
                str(tpl.relative_to(ROOT))
            )
    return out


@pytest.mark.parametrize("asset", SHARED_ASSETS)
def test_shared_asset_reference_is_consistent(asset):
    refs = _references().get(asset)
    assert refs, f"{asset} is referenced by no template"
    missing = refs.get(None) or refs.get("")
    assert not missing, f"{asset} referenced with no cache key in {missing}"
    assert len(refs) == 1, (
        f"{asset} is referenced under multiple cache keys, so one shell serves "
        f"stale immutable bytes: { {v: t for v, t in refs.items()} }"
    )


def _git(*args):
    # encoding must be explicit: the templates contain Arabic, and text=True
    # decodes with the Windows ANSI codepage, which raises inside subprocess's
    # reader thread and hands back an empty string. That failure is silent and
    # made this guard read "no previous reference" instead of "v3.2" -- a
    # vacuous pass on the exact defect it exists to catch.
    r = subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True,
                       encoding="utf-8", errors="replace")
    return r.stdout or ""


def _changed_static_assets(base):
    """Static assets whose bytes differ between `base` and HEAD."""
    names = _git("diff", "--name-only", f"{base}...HEAD", "--", "static/").split("\n")
    return [n for n in names if n.strip().endswith((".css", ".js"))]


@functools.lru_cache(maxsize=None)
def _templates_at_ref(ref):
    """{template path: source} at a git ref — same rglob scope as the
    worktree model, so the 'before' side sees exactly what the 'after' side
    sees. The historic hardcoded three-shell list missed an asset referenced
    from any other template, and that empty 'before' read as a pass."""
    out = {}
    for path in _git("ls-tree", "-r", "--name-only", ref, "--", "templates/").split("\n"):
        path = path.strip()
        if path.endswith(".html"):
            out[path] = _git("show", f"{ref}:{path}")
    return out


def _version_at_ref(ref, asset):
    """The cache keys this asset is referenced under at a given git ref."""
    versions = set()
    for source in _templates_at_ref(ref).values():
        for m in REF.finditer(source):
            if m.group(2) == asset:
                versions.add(m.group(3))
    return versions


def _version_in_worktree(asset):
    """The cache key as it stands on disk right now.

    Deliberately reads the working tree rather than HEAD: a guard that only
    compares two commits cannot block the commit being written, which is
    exactly the state a developer is in when the mistake happens.
    """
    return set(_references().get(asset, {}).keys())


# The baseline is supplied by the caller, not derived from whatever branch
# currently happens to be origin/main.
#
# This distinction is the whole point. A remediation release changes only the
# reference, not the asset: admin_design_system.css is byte-identical between
# c12ea5e and this commit, so a diff against origin/main (= c12ea5e) reports
# no changed asset at all and the guard sees nothing. The bytes changed one
# release earlier. The correct question is always "did the cache key move
# relative to the baseline that introduced these bytes", so that baseline has
# to be named explicitly.
#
#   normal release:  KINJO_RELEASE_BASE=<origin/main before the work started>
#   this remediation: KINJO_RELEASE_BASE=dd58c93 (the pre-c12ea5e baseline)
BASE = os.environ.get("KINJO_RELEASE_BASE", "origin/main")


def stalled_assets(changed, before_versions, after_versions):
    """Pure decision function, so the rule can be tested without git.

    changed:          [asset filename, ...] whose bytes differ from BASE
    before_versions:  {asset: set(cache keys at BASE)}
    after_versions:   {asset: set(cache keys now)}

    A changed asset must be referenced under exactly one cache key, and that
    key must not be one of the keys it was referenced under at BASE. Every
    state is explicit:

      * single key, unchanged                     -> offender (stalled key)
      * references disagree (multiple keys)      -> offender (one of them is
        serving the old bytes; set-equality alone read this as "moved",
        which is precisely how a partial bump slipped through)
      * referenced at BASE, no reference now     -> offender (references
        vanished while the bytes changed; previously skipped by
        `if not after: continue`)
      * never referenced                         -> not this guard's business
      * newly referenced under one key           -> fine, nothing stale
    """
    out = []
    for asset in changed:
        before = before_versions.get(asset) or set()
        after = after_versions.get(asset) or set()
        if before and not after:
            out.append(asset)
        elif len(after) > 1:
            out.append(asset)
        elif after and after <= before:
            out.append(asset)
    return out


def test_stalled_detection_handles_a_remediation_release():
    """The three-state scenario, with no filename hardcoded and no git.

      BASE          old bytes, referenced ?v=3.2
      INTERMEDIATE  new bytes, still      ?v=3.2   <- the defect
      FOLLOW-UP     same bytes as INTERMEDIATE,    ?v=3.3
    """
    asset = "some_shared_sheet.css"

    # Against the BASE that introduced the new bytes, the intermediate release
    # is a defect: the asset changed and the key did not move.
    assert stalled_assets([asset], {asset: {"3.2"}}, {asset: {"3.2"}}) == [asset]

    # The follow-up, measured against that same BASE, is correct.
    assert stalled_assets([asset], {asset: {"3.2"}}, {asset: {"3.3"}}) == []

    # And measured against the INTERMEDIATE release the asset is not in the
    # changed set at all, so the guard must stay silent rather than guess.
    assert stalled_assets([], {asset: {"3.2"}}, {asset: {"3.3"}}) == []

    # An asset nothing references is not this guard's business.
    assert stalled_assets([asset], {}, {}) == []

    # The explicit third state: the bytes changed and the references vanished.
    # The historic `if not after: continue` skipped this silently, so a
    # moved-but-unreferenced asset read as "fine".
    assert stalled_assets([asset], {asset: {"3.2"}}, {}) == [asset]

    # A reference appearing for the first time cannot be stale.
    assert stalled_assets([asset], {}, {asset: {"3.3"}}) == []


def test_changed_static_assets_moved_their_cache_key():
    """The preflight: every static asset this branch changed must also have
    moved its user-facing cache key.

    Discovers the asset list from `git diff`, so it protects assets nobody
    remembered to enumerate -- which is precisely how admin_design_system.css
    slipped through.
    """
    base = _git("rev-parse", "--verify", "--quiet", BASE).strip()
    if not base:
        pytest.skip(f"{BASE} not resolvable in this checkout")

    changed = [p.rsplit("/", 1)[-1] for p in _changed_static_assets(base)]
    before = {a: _version_at_ref(base, a) for a in changed}
    after = {a: _version_in_worktree(a) for a in changed}
    offenders = []
    for asset in stalled_assets(changed, before, after):
        keys = after.get(asset)
        if not keys:
            offenders.append(f"{asset} changed but is no longer referenced "
                             "by any template")
        elif len(keys) > 1:
            offenders.append(f"{asset} changed but its references disagree: "
                             f"?v={sorted(keys)}")
        else:
            offenders.append(f"{asset} changed but stayed at ?v={keys}")
    assert not offenders, (
        "changed immutable assets kept their cache key, so the edge will serve "
        f"the old bytes for a year: {offenders}"
    )


def test_preflight_reads_the_working_tree_not_just_head():
    """Control A support: the preflight must consult on-disk state.

    Comparing two commits would let a bad cache key sail through the very
    commit that introduces it -- the guard would only complain afterwards.
    """
    import inspect
    src = inspect.getsource(test_changed_static_assets_moved_their_cache_key)
    assert "_version_in_worktree" in src, (
        "the preflight must read the working tree for the 'after' side"
    )
    assert _version_in_worktree("admin_design_system.css"), (
        "expected the working tree to expose a cache key for the asset"
    )


def test_consistency_detector_catches_a_split_key():
    """Control B: two references under different keys must be detected."""
    sample = """<link href="/static/css/admin_design_system.css?v=3.2" />
                <link href="/static/css/admin_design_system.css?v=3.3" />"""
    found = {m.group(3) for m in REF.finditer(sample)}
    assert found == {"3.2", "3.3"}, f"matcher lost the split: {found}"
    assert len(found) > 1


def test_matcher_still_sees_a_missing_key():
    """Control C: an unversioned reference must not read as versioned."""
    sample = '<link href="/static/css/admin_design_system.css" />'
    found = [m.group(3) for m in REF.finditer(sample)]
    assert found == [None], f"expected a missing key, got {found}"


def test_matcher_extracts_script_src_references():
    """Control D: a `<script src=...>` reference must feed the same
    asset-keyed model as `href=`. The old href-only matcher saw no JS asset
    at all, so a changed app_i18n.js behind an unmoved ?v= passed the
    preflight by invisibility."""
    sample = '<script src="/static/js/example.js?v=1"></script>'
    found = {m.group(2): m.group(3) for m in REF.finditer(sample)}
    assert found == {"example.js": "1"}, f"matcher lost the src ref: {found}"

    # The worktree model must actually see the real JS assets today, not just
    # the sample above.
    worktree = _references()
    assert "app_i18n.js" in worktree, "script src refs are invisible to the model"
    assert "kinjo-app.js" in worktree, "script src refs are invisible to the model"


def test_stale_language_asset_key_is_flagged():
    """Language-regression mutation control: a stale app_i18n.js key must
    fail, with the guard's decision rule exercised against the real asset
    name so a rename breaks this test loudly instead of silently."""
    assert stalled_assets(["app_i18n.js"], {"app_i18n.js": {"2.2"}},
                          {"app_i18n.js": {"2.2"}}) == ["app_i18n.js"]

    # A PARTIAL bump must fail too: one reference moved to v2.2 while another
    # stayed at v2.1. The set changed, so the old set-equality rule read this
    # as "the key moved" and passed over the stale reference.
    assert stalled_assets(["app_i18n.js"],
                          {"app_i18n.js": {"1.0", "2.1"}},
                          {"app_i18n.js": {"2.1", "2.2"}}) == ["app_i18n.js"]

    # The ref-scoped scan must reach every template, not the historic
    # three-shell list. admin_classification.js is referenced only from
    # page templates outside the three shells, so a lookup scoped to those
    # shells would report an empty 'before' set and the preflight would be
    # vacuous for every page-scoped asset.
    base = _git("rev-parse", "--verify", "--quiet", BASE).strip()
    if base:
        at_ref = _version_at_ref(base, "admin_classification.js")
        assert at_ref, (
            "ref-scoped scan must reach templates outside the three shells, "
            "so admin_classification.js at the base ref must be visible"
        )
