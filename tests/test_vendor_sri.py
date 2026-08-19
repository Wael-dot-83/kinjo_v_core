"""Every `integrity` digest must match the bytes the release actually ships.

Chromium does not warn on an SRI mismatch -- it refuses to execute the script.
So a wrong digest is a hard functional break, and this repository has now
produced two of them by two different routes:

  1. A first-party script carried a manually maintained digest. Editing the file
     changed its bytes, the digest went stale, and Chromium refused it. The rule
     since then: first-party same-origin assets get content-hash cache keys and
     NO integrity attribute.

  2. The self-hosted Plotly bundle pinned the CRLF-transformed bytes that a
     Windows `git archive` produced (4,558,703 B) rather than the committed blob
     (4,558,696 B). Production happened to be deployed from that Windows path, so
     it worked -- verified by fetching the live asset from the edge, not assumed
     -- but the very first release built on the ubuntu-latest workflow would have
     shipped the blob and broken the Charts Explorer.

Nothing caught either one: before this file, `grep -rl sha384 tests/` returned
nothing at all. 48 asset tests passed over a digest that matched no canonical
byte-set.

Canonical bytes are defined by scripts/build_release_artifact.sh and are the
committed Git blob bytes. See tests/test_release_artifact_determinism.py.
"""
import base64
import hashlib
import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "templates"

# src="/static/..." plus integrity="sha384-..." in either order, same tag.
TAG = re.compile(r"<script\b[^>]*>", re.I | re.S)
SRC = re.compile(r'src\s*=\s*"([^"]+)"', re.I)
INTEGRITY = re.compile(r'integrity\s*=\s*"([a-z0-9]+)-([A-Za-z0-9+/=]+)"', re.I)


def _canonical_bytes(rel_path):
    """The bytes the release artifact ships for a repo-relative path."""
    r = subprocess.run(["git", "-C", str(ROOT), "cat-file", "blob", f"HEAD:{rel_path}"],
                       capture_output=True, timeout=120)
    return r.stdout if r.returncode == 0 else None


def _digest(algo, data):
    h = {"sha256": hashlib.sha256, "sha384": hashlib.sha384,
         "sha512": hashlib.sha512}[algo.lower()](data)
    return base64.b64encode(h.digest()).decode()


def _pinned_scripts():
    """Every same-origin <script> in the templates that carries an integrity."""
    out = []
    for tpl in sorted(TEMPLATES.rglob("*.html")):
        for tag in TAG.findall(tpl.read_text(encoding="utf-8", errors="replace")):
            integ = INTEGRITY.search(tag)
            src = SRC.search(tag)
            if not integ or not src:
                continue
            url = src.group(1)
            if not url.startswith("/static/"):
                continue  # a genuine third-party CDN; its bytes are not ours
            out.append((tpl.relative_to(ROOT).as_posix(),
                        url.split("?", 1)[0].lstrip("/"),
                        integ.group(1), integ.group(2)))
    return out


def test_there_is_something_to_check():
    """Guards the whole file against becoming vacuous.

    If the scraper stopped matching -- a quoting change, an attribute order it
    does not understand -- every assertion below would pass over an empty list
    and report green while checking nothing.
    """
    assert _pinned_scripts(), (
        "no self-hosted <script> with an integrity attribute was found. Either "
        "vendor SRI was removed (a policy change that must be deliberate), or "
        "this parser no longer matches the markup and is silently checking "
        "nothing."
    )


@pytest.mark.parametrize("case", _pinned_scripts(), ids=lambda c: c[1])
def test_pinned_digest_matches_the_canonical_shipped_bytes(case):
    template, rel, algo, expected = case
    data = _canonical_bytes(rel)
    assert data is not None, (
        f"{template} pins an integrity for {rel}, but that path is not in the "
        "committed tree, so the release cannot ship it at all"
    )
    actual = _digest(algo, data)
    assert actual == expected, (
        f"{template}\n"
        f"  asset    {rel}  ({len(data)} canonical bytes)\n"
        f"  pinned   {algo}-{expected}\n"
        f"  canonical {algo}-{actual}\n"
        "Chromium refuses a script whose SRI does not match the served bytes, so "
        "this is a hard break, not a warning. Canonical bytes are the committed "
        "blob bytes -- see scripts/build_release_artifact.sh."
    )


@pytest.mark.parametrize("case", _pinned_scripts(), ids=lambda c: c[1])
def test_the_crlf_transformed_bytes_would_not_match(case):
    """Falsification: pin the defect that actually shipped.

    The old digest was the hash of the CRLF-transformed export. If a digest ever
    matches BOTH byte-sets the test above proves nothing, and if one matches only
    the CRLF set we are back to the original defect.
    """
    _, rel, algo, expected = case
    data = _canonical_bytes(rel)
    if data is None or b"\n" not in data:
        pytest.skip(f"{rel} has no line endings to transform")
    crlf = data.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
    if crlf == data:
        pytest.skip(f"{rel} is already CRLF throughout")
    assert _digest(algo, crlf) != expected, (
        f"{rel}: the pinned digest matches the CRLF-TRANSFORMED bytes, not the "
        "canonical ones. That is the exact defect this file exists to prevent: "
        "it works only when the artifact happens to be built on Windows."
    )


def test_first_party_scripts_carry_no_manual_integrity():
    """The other half of the policy, and the first way this bit us."""
    offenders = [
        (t, r) for (t, r, _a, _e) in _pinned_scripts()
        if not r.startswith("static/vendor/")
    ]
    assert not offenders, (
        "first-party same-origin scripts must not carry a manually maintained "
        "integrity digest -- it is checkout-dependent and goes stale the moment "
        "the file is edited, at which point Chromium refuses to run it. Use the "
        f"content-hash ?v= cache key instead. Offenders: {offenders}"
    )


def test_an_sri_pinned_asset_also_carries_a_content_hash_cache_key():
    """A digest that changes while the URL does not strands returning visitors.

    Static assets are served `public, max-age=31536000, immutable`. Plotly was
    referenced as a bare `/static/vendor/plotly-2.35.2.min.js` with no key at
    all, so a returning visitor holds those exact bytes for a year. Change the
    bytes and the pinned digest together -- which the canonical-artifact policy
    did, CRLF to LF -- and that visitor's cached copy no longer matches the new
    integrity, so Chromium refuses to execute it. The page breaks for exactly
    the people who have used it before, and never for anyone testing it fresh.

    SRI and immutable caching are only safe together when the URL is
    content-addressed.
    """
    unkeyed = []
    for tpl in sorted(TEMPLATES.rglob("*.html")):
        for tag in TAG.findall(tpl.read_text(encoding="utf-8", errors="replace")):
            if not INTEGRITY.search(tag):
                continue
            src = SRC.search(tag)
            if not src or not src.group(1).startswith("/static/"):
                continue
            url = src.group(1)
            if not re.search(r"\?v=[0-9a-f]{8,}", url):
                unkeyed.append((tpl.relative_to(ROOT).as_posix(), url))
    assert not unkeyed, (
        "these assets carry an integrity digest but no content-hash cache key, "
        "so changing their bytes silently breaks returning visitors whose "
        f"year-long immutable cache still holds the old ones: {unkeyed}"
    )
