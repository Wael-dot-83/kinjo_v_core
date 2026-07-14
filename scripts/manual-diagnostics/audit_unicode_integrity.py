"""Audit first-party platform text for UTF-8, mojibake, and brand integrity."""

from __future__ import annotations

import subprocess
import sys
import re
from pathlib import Path


TEXT_SUFFIXES = {
    "", ".bat", ".cfg", ".conf", ".css", ".csv", ".example", ".geojson",
    ".html", ".ini", ".js", ".json", ".jsonc", ".mako", ".md", ".po",
    ".pot", ".ps1", ".py", ".sh", ".sql", ".svg", ".template", ".toml",
    ".ts", ".tsx", ".txt", ".vue", ".yaml", ".yml",
}
EXCLUDED_PREFIXES = ("static/vendor/",)
EXCLUDED_FILES: set[str] = set()
MOJIBAKE_MARKERS = tuple(
    chr(codepoint)
    for codepoint in (0x00C2, 0x00C3, 0x00D8, 0x00D9, 0x00E2, 0x00EF, 0xFFFD)
)
FORBIDDEN_ARABIC_BRAND = "\u0643\u064a\u0646\u062c\u0648"
FORBIDDEN_ROMANIZATION = re.compile(
    "|".join(("kin" + "go", "ken" + "go", "ken" + "jo")), re.IGNORECASE
)
BRAND_TOKEN = re.compile(r"\bkinjo\b", re.IGNORECASE)
ALLOWED_TECHNICAL_BRAND_TOKENS = {"KinJo", "kinjo", "KINJO"}


def tracked_text_files(root: Path) -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files", "-z"], cwd=root, check=True, capture_output=True
    )
    files = []
    for raw_name in result.stdout.split(b"\0"):
        if not raw_name:
            continue
        relative = raw_name.decode("utf-8").replace("\\", "/")
        if relative in EXCLUDED_FILES or relative.startswith(EXCLUDED_PREFIXES):
            continue
        path = root / relative
        if path.suffix.lower() in TEXT_SUFFIXES:
            files.append(path)
    return files


def audit_source_files(root: Path) -> list[str]:
    errors: list[str] = []
    for path in tracked_text_files(root):
        relative = path.relative_to(root).as_posix()
        try:
            text = path.read_text(encoding="utf-8", errors="strict")
        except UnicodeDecodeError as exc:
            errors.append(f"{relative}: invalid UTF-8 at byte {exc.start}")
            continue

        for line_number, line in enumerate(text.splitlines(), start=1):
            intentional_fixture = (
                relative == "tests/test_admin_agency_reports_custom.py"
                and "for junk in (" in line
            )
            intentional_evidence = (
                relative == "docs/reports/UNICODE_ARABIC_COMPLIANCE_2026-07-14.md"
                and line_number == 15
            )
            if not (intentional_fixture or intentional_evidence) and any(
                marker in line for marker in MOJIBAKE_MARKERS
            ):
                errors.append(f"{relative}:{line_number}: mojibake marker")
            if FORBIDDEN_ARABIC_BRAND in line:
                errors.append(f"{relative}:{line_number}: use KinJo brand spelling")
            intentional_brand_evidence = (
                relative == "docs/reports/UNICODE_ARABIC_COMPLIANCE_2026-07-14.md"
                and line_number == 30
            )
            if not intentional_brand_evidence and FORBIDDEN_ROMANIZATION.search(line):
                errors.append(f"{relative}:{line_number}: inconsistent KinJo spelling")
            for match in BRAND_TOKEN.finditer(line):
                if match.group(0) not in ALLOWED_TECHNICAL_BRAND_TOKENS:
                    errors.append(
                        f"{relative}:{line_number}: invalid KinJo capitalization"
                    )
    return errors


def main() -> int:
    root = Path(__file__).resolve().parents[2]
    errors = audit_source_files(root)
    if errors:
        print("Unicode integrity audit failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    print("Unicode integrity audit passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
