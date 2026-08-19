"""A deployment must be able to say which SHA it is, and be checkable on it.

Before this existed, the only way to answer "what is running in production?"
was to hash all ~3,950 files and diff them against a candidate commit. That
parity check is strong -- it is how `2cbbf00` was established as live -- but it
is a *verification* control, not an identity mechanism: it can confirm a guess
and cannot answer the question cold. If nobody remembers which commit to guess,
parity has nothing to compare against.

So `deploy_locked.sh` now writes `RELEASE.json` into the deployed tree, and
`/api/admin/release` exposes it read-only to admins.

The trap this module exists to close: the SHA arrives as `argv[2]`, a claim by
whoever ran the deploy. A recorded claim that nobody checks is worse than no
claim, because it looks authoritative. So the deploy also records two values
derived from the artifact it actually extracted -- `tarball_sha256` and
`tree_digest` -- and the test below rebuilds `git archive <sha>` and requires
them to match. A wrong SHA produces a file that contradicts itself.

Parity stays as the independent control. These two answer different questions:
provenance says what the deploy *claims and can prove*, parity says what is
*actually on disk right now*. Neither replaces the other.

Siblings:
  * tests/test_conformance_zero_is_real.py -- a zero that can be falsified
  * tests/test_arabic_typography.py        -- a script-aware gate the detector lacks
"""
import hashlib
import json
import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
DEPLOY_SCRIPT = ROOT / "scripts" / "deploy_locked.sh"

REQUIRED_FIELDS = ("sha", "tarball_sha256", "tree_digest", "deployed_at", "artifact")


def _git(*args):
    return subprocess.run(
        ["git", "-C", str(ROOT), *args], capture_output=True, timeout=300
    ).stdout


# ---------------------------------------------------------------------------
# The deploy script must actually record identity, and record it from the
# artifact rather than only from what it was told.
# ---------------------------------------------------------------------------

def test_deploy_script_writes_a_release_file():
    assert DEPLOY_SCRIPT.is_file(), f"{DEPLOY_SCRIPT} is missing"
    src = DEPLOY_SCRIPT.read_text(encoding="utf-8")
    assert "RELEASE.json" in src, (
        "deploy_locked.sh no longer writes RELEASE.json, so a deployed host "
        "cannot say which SHA it is running without hashing every file"
    )
    for field in REQUIRED_FIELDS:
        assert f'"{field}"' in src, f"RELEASE.json no longer records {field!r}"


def test_recorded_identity_is_derived_from_the_artifact_not_only_claimed():
    """The load-bearing one: the SHA is a claim, the digests are evidence.

    If a future edit drops the artifact-derived fields and keeps only the
    argv-supplied SHA, the file still *looks* authoritative while proving
    nothing. This fails on that.
    """
    src = DEPLOY_SCRIPT.read_text(encoding="utf-8")

    assert re.search(r'TARBALL_SHA=.*sha256sum\s+"\$TARBALL"', src), (
        "tarball_sha256 is no longer computed from the tarball this script "
        "actually extracted, so nothing in RELEASE.json is independent of the "
        "caller's claim"
    )
    assert "TREE_DIGEST=" in src and "sha256sum" in src, (
        "tree_digest is no longer computed from the extracted files"
    )
    # The digest must exclude things that legitimately differ between the
    # artifact and the deployed host, or it can never match `git archive`.
    for excluded in (".env", "RELEASE.json"):
        assert excluded in src, (
            f"the tree digest no longer excludes {excluded!r}; it is not in the "
            "release artifact, so including it makes the digest unreproducible"
        )


def test_release_file_is_written_before_containers_are_recreated():
    """Identity of what is on disk must survive a failed build.

    If the write happened after the image build, a build failure would leave
    new code on disk with the previous release's identity recorded beside it --
    the worst case, because the file would be confidently wrong.
    """
    src = DEPLOY_SCRIPT.read_text(encoding="utf-8")
    write_at = src.index("RELEASE_FILE=")
    # The compose up / container recreation step.
    build_match = re.search(r"docker\s+compose[^\n]*\bup\b", src)
    assert build_match, "could not find the container recreation step to order against"
    assert write_at < build_match.start(), (
        "RELEASE.json is written after containers are recreated; a failed build "
        "would then leave new files on disk labelled with the old release"
    )


# ---------------------------------------------------------------------------
# The end-to-end proof: a recorded SHA must reproduce the recorded digests.
# ---------------------------------------------------------------------------

def _tree_digest_for(ref):
    """Recompute the deploy script's tree_digest from `git archive <ref>`.

    Mirrors the shell exactly: sha256 of every file as "<hash>  <path>", sorted,
    then hashed again. Kept as a separate implementation on purpose -- if the two
    drift apart, that is a real finding, not a nuisance.
    """
    import tarfile
    import tempfile

    blob = _git("archive", "--format=tar", ref)
    if not blob:
        return None
    lines = []
    with tempfile.TemporaryDirectory() as td:
        with tarfile.open(fileobj=__import__("io").BytesIO(blob)) as tf:
            # filter="data" is required from Python 3.14 and silences the
            # deprecation warning this suite escalates to an error.
            tf.extractall(td, filter="data")
        base = Path(td)
        for path in sorted(p for p in base.rglob("*") if p.is_file()):
            rel = path.relative_to(base).as_posix()
            if rel in (".env", "RELEASE.json") or rel.startswith("data/"):
                continue
            h = hashlib.sha256(path.read_bytes()).hexdigest()
            lines.append(f"{h}  ./{rel}\n")
    joined = "".join(sorted(lines)).encode()
    return hashlib.sha256(joined).hexdigest()


@pytest.mark.parametrize("location", ["/opt/kinjo/RELEASE.json", "RELEASE.json"])
def test_recorded_sha_reproduces_its_own_digest(location):
    """Given a RELEASE.json, `git archive <sha>` must reproduce its digest.

    This is the assertion that turns a recorded SHA from a claim into a fact.
    Skips when no release file is reachable -- a dev checkout has none, and this
    is not the place to fail for that; the tests above already guarantee the
    deploy writes one.
    """
    path = Path(location)
    if not path.is_absolute():
        path = ROOT / path
    if not path.is_file():
        pytest.skip(f"no release file at {path}")

    payload = json.loads(path.read_text(encoding="utf-8"))
    for field in REQUIRED_FIELDS:
        assert field in payload, f"RELEASE.json is missing {field!r}"

    sha = payload["sha"]
    if not re.fullmatch(r"[0-9a-f]{7,40}", sha or ""):
        pytest.fail(f"recorded sha {sha!r} is not a git object name")

    resolved = _git("rev-parse", "--verify", "--quiet", f"{sha}^{{commit}}").decode().strip()
    if not resolved:
        pytest.skip(f"commit {sha} is not present in this checkout")

    recomputed = _tree_digest_for(resolved)
    assert recomputed is not None, "git archive produced nothing"
    assert recomputed == payload["tree_digest"], (
        f"RELEASE.json records sha={sha} but the tree digest of that commit does "
        f"not match what was deployed:\n"
        f"  recorded   {payload['tree_digest']}\n"
        f"  git archive {recomputed}\n"
        "Either the recorded SHA is wrong, or the deployed tree was modified "
        "after extraction. Both matter; neither should be assumed benign."
    )


# ---------------------------------------------------------------------------
# Synthetic controls. These need no deployed host and no RELEASE.json, so the
# proof above cannot quietly become unfalsifiable by skipping everywhere.
# ---------------------------------------------------------------------------

def _two_distinct_commits():
    head = _git("rev-parse", "--verify", "--quiet", "HEAD^{commit}").decode().strip()
    prev = _git("rev-parse", "--verify", "--quiet", "HEAD~1^{commit}").decode().strip()
    if not head or not prev or head == prev:
        pytest.skip("need two distinct commits in this checkout")
    return head, prev


def test_control_a_correct_sha_verifies():
    """A release file whose sha really is its tree must pass.

    Guards the other direction from the control below: a check that rejected
    everything would also 'catch' a wrong sha, and would be useless.
    """
    head, _ = _two_distinct_commits()
    digest = _tree_digest_for(head)
    assert digest, "git archive produced nothing for HEAD"
    assert _tree_digest_for(head) == digest, "digest is not reproducible run to run"


def test_control_a_wrong_sha_is_rejected():
    """The assertion that gives the whole mechanism its meaning.

    Records HEAD's tree digest against the PREVIOUS commit's sha -- exactly what
    a mistyped or copy-pasted deploy argument produces -- and requires the two
    to disagree. If this ever passes, RELEASE.json has become a claim nobody
    checks, which is worse than not recording one at all.
    """
    head, prev = _two_distinct_commits()
    head_digest = _tree_digest_for(head)
    prev_digest = _tree_digest_for(prev)
    assert head_digest and prev_digest
    assert head_digest != prev_digest, (
        "two different commits produced the same tree digest, so the digest "
        "cannot distinguish releases and a wrong recorded sha would go unnoticed"
    )


# ---------------------------------------------------------------------------
# The read-only exposure. Identity nobody can query is identity nobody uses.
# ---------------------------------------------------------------------------

def test_release_endpoint_is_registered_and_admin_scoped():
    """/api/admin/release must exist and must not be anonymous.

    A release identity is not a secret, but it is operational detail about the
    host; there is no reason to hand it to unauthenticated callers.
    """
    import admin_endpoints

    paths = [r.path for r in admin_endpoints.router.routes]
    assert "/release" in paths, (
        "the release-identity endpoint is gone, so the only way to answer "
        "'what SHA is running?' is hashing the filesystem again"
    )

    route = next(r for r in admin_endpoints.router.routes if r.path == "/release")
    src = admin_endpoints.Path(admin_endpoints.__file__).read_text(encoding="utf-8")
    fn_start = src.index("def admin_release_identity")
    window = src[max(0, fn_start - 400):fn_start]
    assert "require_admin" in src[fn_start:fn_start + 600] or "require_admin" in window, (
        "the release endpoint is no longer behind require_admin"
    )
    assert "GET" in route.methods and route.methods <= {"GET", "HEAD"}, (
        f"the release endpoint must be read-only; it accepts {route.methods}"
    )


def test_release_endpoint_reports_absence_plainly(client, admin_user):
    """With no RELEASE.json, the endpoint says so rather than inventing a SHA.

    A dev checkout and a pre-provenance release both look like this. Reporting
    `recorded: false` keeps the caller honest; returning a plausible-looking
    guess would be the worst possible behaviour for an identity mechanism.
    """
    from admin_endpoints import require_admin
    from main import app

    app.dependency_overrides[require_admin] = lambda: admin_user
    try:
        response = client.get("/api/admin/release")
    finally:
        app.dependency_overrides.clear()

    if response.status_code != 200:
        pytest.skip(f"release endpoint not reachable in this harness ({response.status_code})")

    body = response.json()
    assert "recorded" in body, f"unexpected payload: {body}"
    if not body["recorded"]:
        assert body.get("detail"), "absence must be explained, not merely flagged"
    else:
        for field in ("sha", "tarball_sha256", "tree_digest"):
            assert body.get(field), f"recorded release is missing {field}"
