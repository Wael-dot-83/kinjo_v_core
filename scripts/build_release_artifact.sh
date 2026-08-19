#!/usr/bin/env bash
# =============================================================================
# THE canonical KinJo release artifact producer. Every production deployment
# must obtain its tarball from this script, on any machine.
#
# WHY THIS EXISTS
#
# `git archive` applies the *producer's* core.autocrlf. This workstation has
# core.autocrlf=true globally, the release workflow runs on ubuntu-latest, and
# both called `git archive` directly -- so one commit legally exported two
# different artifacts:
#
#   static/vendor/plotly-2.35.2.min.js
#     committed blob                4,558,696 bytes
#     git archive (autocrlf=true)   4,558,703 bytes   (+7 CRLF)
#     git archive (autocrlf=false)  4,558,696 bytes
#
# 1,263 of 3,950 files diverged that way. That breaks two things at once:
#
#   * Release identity. "This SHA reproduces this artifact" cannot be true when
#     the SHA exports different bytes depending on who ran the command.
#   * Subresource Integrity. The Plotly `integrity` attribute pinned the
#     CRLF-transformed bytes, so a release built on Linux would have served the
#     LF blob and Chromium would have REFUSED to execute Plotly on the Charts
#     Explorer. Production only escaped this because it happened to be deployed
#     from the Windows path.
#
# THE POLICY
#
# Canonical release bytes == committed Git blob bytes. Always, everywhere.
#
# `-c core.autocrlf=false -c core.eol=lf` on the command line overrides any
# global, system or repository config, so the export is identical whatever the
# producer's checkout looks like. This deliberately does NOT change anyone's
# working tree -- no renormalisation, no mass file rewrite, no worktree turning
# dirty mid-release. It changes only how the artifact is exported.
#
# This also makes the static cache-key invariant self-consistent: the `?v=`
# keys are sha256 prefixes of committed blob bytes, and those are now exactly
# the bytes shipped and served.
#
# .gitattributes keeps `*.sh`/`*.conf text eol=lf` -- same class of bug, found
# earlier, when CRLF in the deploy wrapper made bash fail on the carriage
# return. This generalises the remedy to the whole artifact.
#
# Enforced by tests/test_release_artifact_determinism.py, which builds under a
# hostile core.autocrlf=true and requires the digest not to move -- and proves
# a naive `git archive` under that same config DOES move, so the control cannot
# quietly become vacuous.
#
# Usage:
#   scripts/build_release_artifact.sh <full-sha> <output.tar>
# =============================================================================
set -euo pipefail

SHA="${1:-}"
OUT="${2:-}"

if [[ -z "$SHA" || -z "$OUT" ]]; then
  echo "usage: $0 <full-40-char-sha> <output.tar>" >&2
  exit 2
fi

if [[ ! "$SHA" =~ ^[0-9a-f]{40}$ ]]; then
  echo "ERROR: release artifacts are built from a full 40-character SHA; got: $SHA" >&2
  exit 2
fi

git rev-parse --verify --quiet "${SHA}^{commit}" >/dev/null \
  || { echo "ERROR: not a commit in this repository: $SHA" >&2; exit 2; }

git -c core.autocrlf=false -c core.eol=lf archive --format=tar -o "$OUT" "$SHA"

echo "artifact:     $OUT"
echo "source_sha:   $SHA"
echo "sha256:       $(sha256sum "$OUT" | awk '{print $1}')"
# --force-local: GNU tar reads a colon in the path as host:path, so an
# absolute Windows path (C:/...) would otherwise be treated as a remote.
echo "members:      $(tar --force-local -tf "$OUT" | grep -vc '/$')"
