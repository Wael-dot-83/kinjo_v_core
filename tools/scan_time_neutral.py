#!/usr/bin/env python3
"""
Time-neutrality scanner for ADMIN_PANEL_REVIEW_REPORT.md

Enforces the compliance gate defined in the report header.
On PASS: rewrites the entire Scan Proof block from scratch.
On FAIL: does NOT touch any part of the file (fail-closed).

Exit codes:
  0 = PASS  (zero editorial violations; Scan Proof rewritten)
  1 = FAIL  (violations found, or structural errors; file untouched)
  2 = SCANNER_ERROR (invalid inputs / missing structure)

CI usage:
  python tools/scan_time_neutral.py ADMIN_PANEL_REVIEW_REPORT.md
  python tools/scan_time_neutral.py ADMIN_PANEL_REVIEW_REPORT.md --verify
    --verify: check that the scanner_sha256 in the footer matches this file's
              hash (for uncommitted-local distribution). Non-zero exit on mismatch.
"""
from __future__ import annotations

import hashlib
import platform
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

__version__ = "1.0.0"

# ── Forbidden keyword pattern (word-boundary enforced) ──────────────────────
FORBIDDEN_KEYWORDS = re.compile(
    r"\b("
    r"seconds?|minutes?|hours?|days?|weeks?|months?|years?"
    r"|daily|weekly|monthly|yearly|quarterly|annually|biweekly|bimonthly"
    r"|soon|recently?|current|next|last"
    r"|today|tomorrow|yesterday|now|later"
    r"|ETA|deadline|roadmap|milestone|sprint"
    r"|schedule|timeline|cadence|duration|ongoing|future|asap"
    r"|immediately|eventually"
    r"|going forward"
    r")\b",
    re.IGNORECASE,
)

FORBIDDEN_PHRASES = re.compile(
    r"in the meantime|at the moment",
    re.IGNORECASE,
)

# ── Forbidden numeric duration pattern ──────────────────────────────────────
FORBIDDEN_NUMERIC = re.compile(
    r"\d+\s*"
    r"(s|sec|secs|second|seconds"
    r"|min|mins|minute|minutes"
    r"|h|hr|hrs|hour|hours"
    r"|d|day|days"
    r"|w|wk|wks|week|weeks"
    r"|mo|mos|month|months"
    r"|y|yr|yrs|year|years)\b",
    re.IGNORECASE,
)

# ── Code-path exemption: backtick-wrapped identifiers ───────────────────────
EXEMPT_BACKTICK = re.compile(r"`[^`]*?`")

# ── Structural markers (exact literals — no fuzzy matching) ─────────────────
CUT_POINT_FIELD = "| report_sha256"  # exact prefix of the table row
SCAN_PROOF_HEADING = "### Scan Proof"
COMPLIANCE_GATE_HEADING = "## Compliance Gate"
END_OF_REPORT_MARKER = "_End of report._"


# ─────────────────────────────────────────────────────────────────────────────
# Boundary detection
# ─────────────────────────────────────────────────────────────────────────────

def find_gate_lines(lines: list[str]) -> set[int]:
    """Return 0-based line indices belonging to the gate header blockquote.

    Includes the trailing '---' separator.
    """
    gate: set[int] = set()
    in_gate = False
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith(">"):
            in_gate = True
            gate.add(i)
        elif in_gate and stripped == "":
            gate.add(i)
        elif in_gate and stripped == "---":
            gate.add(i)
            break
        elif in_gate:
            break
    return gate


def find_heading(lines: list[str], heading: str) -> int | None:
    """Return 0-based index of the first line starting with `heading`."""
    for i, line in enumerate(lines):
        if line.strip().startswith(heading):
            return i
    return None


def find_all_occurrences(lines: list[str], literal: str) -> list[int]:
    """Return 0-based indices of lines whose stripped text starts with `literal`."""
    return [i for i, line in enumerate(lines) if line.strip().startswith(literal)]


def find_scan_proof_bounds(lines: list[str]) -> tuple[int, int] | None:
    """Return (start, end) 0-based indices of the full Scan Proof block.

    The block starts at '### Scan Proof' and ends at the line before
    '_End of report._'.
    """
    start = find_heading(lines, SCAN_PROOF_HEADING)
    if start is None:
        return None
    # Find the end: look for '---' + '_End of report._' after start
    for i in range(start + 1, len(lines)):
        if lines[i].strip() == END_OF_REPORT_MARKER:
            return (start, i + 1)  # exclusive end
    return (start, len(lines))


# ─────────────────────────────────────────────────────────────────────────────
# Line-level scanning
# ─────────────────────────────────────────────────────────────────────────────

def strip_backtick_content(line: str) -> str:
    """Remove backtick-wrapped content so it doesn't trigger false positives."""
    return EXEMPT_BACKTICK.sub("", line)


def scan_line(line: str) -> list[str]:
    """Return list of forbidden matches found in the line (after exemptions)."""
    cleaned = strip_backtick_content(line)
    matches: list[str] = []
    for m in FORBIDDEN_KEYWORDS.finditer(cleaned):
        matches.append(m.group())
    for m in FORBIDDEN_PHRASES.finditer(cleaned):
        matches.append(m.group())
    for m in FORBIDDEN_NUMERIC.finditer(cleaned):
        matches.append(m.group())
    return matches


# ─────────────────────────────────────────────────────────────────────────────
# Hash computation
# ─────────────────────────────────────────────────────────────────────────────

def compute_content_hash(lines: list[str], up_to_line: int) -> str:
    """SHA-256 of file content up to (not including) the given line index."""
    content = "\n".join(lines[:up_to_line]) + "\n"
    return hashlib.sha256(content.encode("utf-8")).hexdigest().upper()


def compute_own_hash() -> str:
    """SHA-256 of this scanner file itself."""
    own_path = Path(__file__).resolve()
    return hashlib.sha256(own_path.read_bytes()).hexdigest().upper()


def get_git_commit() -> str | None:
    """Try to get the git commit hash of this scanner file."""
    import subprocess
    try:
        result = subprocess.run(
            ["git", "log", "-1", "--format=%H", "--", __file__],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Scan Proof block generation
# ─────────────────────────────────────────────────────────────────────────────

def generate_scan_proof_block(
    report_hash: str,
    scan_utc: str,
    scanner_hash: str,
    distribution: str,
    commit_val: str,
    python_ver: str,
) -> list[str]:
    """Generate the complete Scan Proof block (lines without trailing newline)."""
    return [
        "",
        "### Scan Proof",
        "",
        "| Field                | Value                                                              |",
        "| -------------------- | ------------------------------------------------------------------ |",
        f"| report_sha256        | `{report_hash}` |",
        "| hash_scope           | File content up to (but not including) the `report_sha256` line    |",
        f"| scan_utc             | `{scan_utc}` |",
        f"| scanner_version      | `{__version__}` |",
        f"| scanner_distribution | `{distribution}` |",
        f"| scanner_git_commit   | `{commit_val}` |",
        f"| scanner_sha256       | `{scanner_hash}` |",
        f"| python_version       | `{python_ver}` |",
        "",
        "_All fields in Scan Proof are machine metadata; excluded from narrative time-neutrality rules._",
        "",
        "---",
        "",
        "_End of report._",
        "",
    ]


# ─────────────────────────────────────────────────────────────────────────────
# Structural validation (fail-closed)
# ─────────────────────────────────────────────────────────────────────────────

def validate_structure(lines: list[str]) -> str | None:
    """Validate report structure. Returns error message or None if valid."""
    # 1. Compliance Gate heading must exist
    footer_start = find_heading(lines, COMPLIANCE_GATE_HEADING)
    if footer_start is None:
        return f"'{COMPLIANCE_GATE_HEADING}' section not found."

    # 2. Cut-point marker must exist exactly once
    occurrences = find_all_occurrences(lines, CUT_POINT_FIELD)
    if len(occurrences) == 0:
        return (
            f"Cut-point marker '{CUT_POINT_FIELD}' not found. "
            "Cannot determine hash scope."
        )
    if len(occurrences) > 1:
        return (
            f"Cut-point marker '{CUT_POINT_FIELD}' found {len(occurrences)} times "
            f"(lines {[i + 1 for i in occurrences]}). Must appear exactly once."
        )

    # 3. Cut-point must be inside or after the Compliance Gate section
    cut_idx = occurrences[0]
    if cut_idx < footer_start:
        return (
            f"Cut-point marker is at line {cut_idx + 1}, which is BEFORE the "
            f"Compliance Gate section (line {footer_start + 1}). "
            "Marker must not be relocated above the footer."
        )

    # 4. Scan Proof heading must exist
    proof_bounds = find_scan_proof_bounds(lines)
    if proof_bounds is None:
        return f"'{SCAN_PROOF_HEADING}' section not found."

    return None  # valid


# ─────────────────────────────────────────────────────────────────────────────
# --verify mode (CI integrity check)
# ─────────────────────────────────────────────────────────────────────────────

def verify_scanner_hash(lines: list[str]) -> int:
    """CI verification: check scanner_sha256 in footer matches this file.

    Returns 0 on match, 1 on mismatch/missing.
    """
    actual_hash = compute_own_hash()
    for line in lines:
        if line.strip().startswith("| scanner_sha256"):
            # Extract the hash value from the table row
            match = re.search(r"`([A-Fa-f0-9]{64})`", line)
            if match:
                footer_hash = match.group(1).upper()
                if footer_hash == actual_hash:
                    print(f"VERIFY PASS: scanner_sha256 matches ({actual_hash[:16]}...)")
                    return 0
                else:
                    print(
                        f"VERIFY FAIL: scanner_sha256 mismatch\n"
                        f"  Footer:  {footer_hash}\n"
                        f"  Actual:  {actual_hash}",
                        file=sys.stderr,
                    )
                    return 1
    print("VERIFY FAIL: scanner_sha256 field not found in report.", file=sys.stderr)
    return 1


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main() -> int:
    verify_mode = "--verify" in sys.argv
    args = [a for a in sys.argv[1:] if a != "--verify"]

    if len(args) != 1:
        print(
            "Usage: python tools/scan_time_neutral.py <report.md> [--verify]",
            file=sys.stderr,
        )
        return 2

    report_path = Path(args[0])
    if not report_path.exists():
        print(f"SCANNER_ERROR: Report not found: {report_path}", file=sys.stderr)
        return 2

    lines = report_path.read_text(encoding="utf-8").splitlines()

    # ── --verify mode: just check scanner hash and exit ─────────────────
    if verify_mode:
        return verify_scanner_hash(lines)

    # ── Structural validation (fail-closed) ─────────────────────────────
    struct_error = validate_structure(lines)
    if struct_error:
        print(f"FAIL: {struct_error}", file=sys.stderr)
        return 1

    # ── Determine scan boundaries ───────────────────────────────────────
    gate_lines = find_gate_lines(lines)
    footer_start = find_heading(lines, COMPLIANCE_GATE_HEADING)

    # ── Scan body (everything between gate and footer) ──────────────────
    violations: list[tuple[int, str, list[str]]] = []
    exemptions: list[int] = []

    for i, line in enumerate(lines):
        if i in gate_lines or i >= footer_start:
            continue

        matches = scan_line(line)
        if matches:
            cleaned = strip_backtick_content(line)
            if (not FORBIDDEN_KEYWORDS.search(cleaned)
                    and not FORBIDDEN_PHRASES.search(cleaned)
                    and not FORBIDDEN_NUMERIC.search(cleaned)):
                exemptions.append(i + 1)
            else:
                violations.append((i + 1, line.strip()[:120], matches))

    # ── FAIL: print violations, do NOT touch the file ───────────────────
    if violations:
        print(f"FAIL: {len(violations)} editorial violation(s) found:\n")
        for line_num, text, matches in violations:
            print(f"  L{line_num}: [{', '.join(matches)}]")
            print(f"         {text}\n")
        print(f"Exemptions (backtick-wrapped code paths): {len(exemptions)}")
        print("\nFile NOT modified (fail-closed).")
        return 1

    # ── PASS: compute proof fields ──────────────────────────────────────
    cut_idx = find_all_occurrences(lines, CUT_POINT_FIELD)[0]
    report_hash = compute_content_hash(lines, cut_idx)
    scanner_hash = compute_own_hash()
    git_commit = get_git_commit()
    scan_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    python_ver = platform.python_version()

    if git_commit:
        distribution = "git"
        commit_val = git_commit
    else:
        distribution = "uncommitted-local"
        commit_val = "N/A"

    # ── Rewrite the entire Scan Proof block from scratch ────────────────
    proof_bounds = find_scan_proof_bounds(lines)
    proof_start, proof_end = proof_bounds

    # Find the '---' separator line before the Scan Proof block
    separator_idx = proof_start
    for i in range(proof_start - 1, -1, -1):
        if lines[i].strip() == "---":
            separator_idx = i
            break

    new_proof = generate_scan_proof_block(
        report_hash, scan_utc, scanner_hash,
        distribution, commit_val, python_ver,
    )

    # Replace: keep everything before the separator, insert new proof block
    new_lines = lines[:separator_idx] + ["---"] + new_proof
    new_content = "\n".join(new_lines)

    report_path.write_text(new_content, encoding="utf-8")

    print(f"PASS: 0 editorial violations, {len(exemptions)} code-path exemption(s)")
    print(f"Scan Proof block rewritten in {report_path.name}.")
    print(f"\n--- Scan Proof ---")
    print(f"report_sha256:        {report_hash}")
    print(f"hash_scope:           file content up to (but not including) the `report_sha256` line")
    print(f"scan_utc:             {scan_utc}")
    print(f"scanner_version:      {__version__}")
    print(f"scanner_distribution: {distribution}")
    print(f"scanner_git_commit:   {commit_val}")
    print(f"scanner_sha256:       {scanner_hash}")
    print(f"python_version:       {python_ver}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
