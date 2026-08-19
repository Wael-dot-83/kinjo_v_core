"""One commit must export exactly one artifact, on every machine.

`git archive` applies the PRODUCER's core.autocrlf. This project had two
producers -- a Windows workstation with core.autocrlf=true, and a
`runs-on: ubuntu-latest` workflow -- and both called `git archive` directly. So
one SHA legally exported two different artifacts:

    static/vendor/plotly-2.35.2.min.js
      committed blob               4,558,696 bytes
      git archive (autocrlf=true)  4,558,703 bytes   (+7 CRLF)

1,263 of 3,950 files diverged that way, and it broke two things at once:

  * Release identity. "This SHA reproduces this artifact" is not a fact when the
    answer depends on who ran the command.
  * Subresource Integrity. The Plotly `integrity` pinned the CRLF bytes, so a
    release built on Linux would ship the LF blob and Chromium would REFUSE to
    execute it. Production escaped only because it happened to be deployed from
    the Windows path -- measured at the edge, not assumed.

The policy is now: canonical release bytes == committed Git blob bytes, produced
only by scripts/build_release_artifact.sh, which pins the conversion settings on
the command line where they outrank any global or repo config.

WHY THIS FILE IS SHAPED THE WAY IT IS

A same-machine `archive -> extract -> rehash` round trip agrees with itself no
matter how broken the policy is. It would have passed throughout the period the
defect existed. So the hostile configuration is injected explicitly through
GIT_CONFIG_* -- which works even on a Linux runner where autocrlf is false by
default -- and a falsification case proves that config really does move a naive
export. Without that, the equality assertion could quietly become vacuous.
"""
import hashlib
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
BUILDER = ROOT / "scripts" / "build_release_artifact.sh"

# A text file large enough that CRLF conversion is unmistakable.
CANARY = "static/vendor/plotly-2.35.2.min.js"

HOSTILE = {
    "GIT_CONFIG_COUNT": "2",
    "GIT_CONFIG_KEY_0": "core.autocrlf", "GIT_CONFIG_VALUE_0": "true",
    "GIT_CONFIG_KEY_1": "core.eol", "GIT_CONFIG_VALUE_1": "crlf",
}
FRIENDLY = {
    "GIT_CONFIG_COUNT": "2",
    "GIT_CONFIG_KEY_0": "core.autocrlf", "GIT_CONFIG_VALUE_0": "false",
    "GIT_CONFIG_KEY_1": "core.eol", "GIT_CONFIG_VALUE_1": "lf",
}


def _head():
    out = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"],
                         capture_output=True, timeout=60)
    return out.stdout.decode().strip()


def _env(overrides):
    e = dict(os.environ)
    for k in list(e):
        if k.startswith("GIT_CONFIG"):
            del e[k]
    e.update(overrides)
    return e


def _builder_git_flags():
    """Read the -c overrides out of the builder's own git invocation.

    The test runs the builder's POLICY rather than shelling out to it, because
    `bash` on a Windows host resolves to WSL, which cannot see the checkout.
    Parsing the flags keeps the two bound together: weaken the script and this
    test weakens with it, then fails on the determinism assertion below.
    """
    src = BUILDER.read_text(encoding="utf-8")
    line = next((l for l in src.splitlines()
                 if l.strip().startswith("git ") and " archive" in l), None)
    assert line, "the canonical builder no longer contains a `git ... archive` command"
    flags, tokens = [], line.split()
    for i, tok in enumerate(tokens):
        if tok == "-c" and i + 1 < len(tokens):
            flags += ["-c", tokens[i + 1]]
    assert flags, (
        "the builder's git archive carries no -c overrides, so the export again "
        "inherits the producer's core.autocrlf"
    )
    return flags


def _build(sha, out_path, overrides):
    """Export through the canonical producer's exact git configuration."""
    r = subprocess.run(["git", "-C", str(ROOT), *_builder_git_flags(),
                        "archive", "--format=tar", "-o", str(out_path), sha],
                       env=_env(overrides), capture_output=True, timeout=600)
    assert r.returncode == 0, (
        f"the canonical export failed: {r.stderr.decode(errors='replace')[:800]}"
    )
    return hashlib.sha256(out_path.read_bytes()).hexdigest()


def test_the_builder_script_runs_where_a_posix_shell_is_available():
    """Smoke-test the script itself. Non-load-bearing by design.

    On a Windows host `bash` is WSL and cannot reach the checkout, so this
    skips there. The policy it implements is proved portably by the tests
    below; this only catches a syntax error in the wrapper.
    """
    import shutil, tempfile
    if not shutil.which("bash"):
        pytest.skip("no bash on PATH")
    if sys.platform.startswith("win"):
        pytest.skip("bash on this host is WSL and cannot see the checkout; "
                    "the export policy is proved portably by the other tests")
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "smoke.tar"
        r = subprocess.run(["bash", str(BUILDER), _head(), str(out)],
                           cwd=str(ROOT), capture_output=True, timeout=600)
        assert r.returncode == 0, r.stderr.decode(errors="replace")[:800]
        assert out.is_file() and out.stat().st_size > 0


def _naive(sha, out_path, overrides):
    """A plain `git archive`, the way both producers used to call it."""
    r = subprocess.run(["git", "-C", str(ROOT), "archive", "--format=tar",
                        "-o", str(out_path), sha],
                       env=_env(overrides), capture_output=True, timeout=600)
    assert r.returncode == 0, r.stderr.decode(errors="replace")[:800]
    return hashlib.sha256(out_path.read_bytes()).hexdigest()


def test_the_canonical_builder_exists_and_demands_a_full_sha():
    assert BUILDER.is_file(), f"{BUILDER} is missing; there is no canonical producer"
    src = BUILDER.read_text(encoding="utf-8")
    assert "core.autocrlf=false" in src and "core.eol=lf" in src, (
        "the builder no longer pins the conversion settings, so the artifact "
        "again depends on the producer's checkout configuration"
    )
    assert "{40}" in src, (
        "the builder no longer requires a full 40-character SHA"
    )


@pytest.mark.timeout(600)
def test_the_artifact_is_identical_under_a_hostile_git_configuration(tmp_path):
    """The load-bearing assertion: config cannot move release identity."""
    sha = _head()
    hostile = _build(sha, tmp_path / "hostile.tar", HOSTILE)
    friendly = _build(sha, tmp_path / "friendly.tar", FRIENDLY)
    assert hostile == friendly, (
        "the canonical builder produced different artifacts under "
        "core.autocrlf=true and core.autocrlf=false:\n"
        f"  autocrlf=true   {hostile}\n"
        f"  autocrlf=false  {friendly}\n"
        "Release identity is therefore a function of who ran the build, and "
        "'this SHA reproduces this artifact' cannot be asserted."
    )


@pytest.mark.timeout(600)
def test_a_naive_git_archive_really_does_diverge(tmp_path):
    """Falsification. Without this, the test above could prove nothing.

    If a future Git stopped applying autocrlf during `git archive`, the equality
    above would hold for a reason unrelated to the fix, and the control would
    silently stop guarding anything. This asserts the hazard is still real.
    """
    sha = _head()
    hostile = _naive(sha, tmp_path / "naive_hostile.tar", HOSTILE)
    friendly = _naive(sha, tmp_path / "naive_friendly.tar", FRIENDLY)
    if hostile == friendly:
        pytest.skip(
            "this Git no longer applies core.autocrlf during `git archive`, so "
            "the divergence this policy guards against cannot be reproduced "
            "here; the canonical builder remains correct but is unfalsifiable "
            "on this toolchain"
        )
    assert hostile != friendly  # documents the hazard the policy exists for


@pytest.mark.timeout(600)
def test_canonical_bytes_are_the_committed_blob_bytes(tmp_path):
    """Canonical == committed blob, so cache keys describe what is served.

    The `?v=` keys are sha256 prefixes of committed blob bytes. If the artifact
    shipped anything else, every key would be the hash of bytes nobody receives.
    """
    import tarfile

    sha = _head()
    out = tmp_path / "canon.tar"
    _build(sha, out, HOSTILE)

    blob = subprocess.run(["git", "-C", str(ROOT), "cat-file", "blob", f"{sha}:{CANARY}"],
                          capture_output=True, timeout=120).stdout
    assert blob, f"{CANARY} is not in the tree at {sha}"

    with tarfile.open(out) as tf:
        member = tf.extractfile(CANARY)
        assert member is not None, f"{CANARY} is missing from the artifact"
        shipped = member.read()

    assert shipped == blob, (
        f"{CANARY}: the artifact ships {len(shipped)} bytes but the committed "
        f"blob is {len(blob)}. Canonical release bytes must be the blob bytes, "
        "or the content-hash cache keys and the vendor SRI digests describe "
        "bytes nobody is served."
    )


def test_the_release_workflow_uses_the_canonical_builder():
    """A policy only one producer follows is not a policy."""
    wf = ROOT / ".github" / "workflows" / "deploy.yml"
    if not wf.is_file():
        pytest.skip("no deploy workflow in this checkout")
    src = wf.read_text(encoding="utf-8")
    assert "build_release_artifact.sh" in src, (
        "the deploy workflow still calls `git archive` directly, so a CI-built "
        "release can diverge from a workstation-built one -- the exact defect "
        "the canonical builder exists to remove"
    )
