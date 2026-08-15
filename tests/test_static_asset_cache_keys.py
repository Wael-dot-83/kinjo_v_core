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
"""
import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "templates"

# Assets whose reference consistency is contractually protected. Membership is
# about "referenced from more than one shell", not about who changed last.
SHARED_ASSETS = ["design-tokens.css", "admin_design_system.css"]

REF = re.compile(r'href="/static/(css|js)/([a-z0-9_.-]+\.(?:css|js))(?:\?v=([^"]*))?"')


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


def _version_at_ref(ref, asset):
    """The cache key this asset was referenced under at a given git ref."""
    versions = set()
    for tpl in ("templates/admin_base.html", "templates/manager_base.html",
                "templates/base.html"):
        for m in REF.finditer(_git("show", f"{ref}:{tpl}")):
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


BASE = "origin/main~1"


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

    offenders = []
    for asset_path in _changed_static_assets(base):
        asset = asset_path.rsplit("/", 1)[-1]
        before = _version_at_ref(base, asset)
        after = _version_in_worktree(asset)
        if not after:
            continue  # not referenced from a shell template
        if before == after:
            offenders.append(f"{asset_path} changed but stayed at ?v={after}")
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
