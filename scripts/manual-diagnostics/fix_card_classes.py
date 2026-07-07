"""Repair BEM card classes corrupted by the earlier USWDS->Bootstrap migration.

The migration replaced `usa-card` -> `col-12` before handling `usa-card__*`,
producing non-existent classes like `col-12__container`. Map those (and a few
other mangled tokens) back to real Bootstrap 5.3 classes. Exact-token,
word-boundary replacements only — real classes (col-12, text-gold, border-gold,
bg-success-subtle) are left untouched.
"""
import re
from pathlib import Path

ROOT = Path(r"d:/Final Version/templates")
FILES = [
    "manager/absence_requests.html",
    "manager/benchmarking.html",
    "manager/children.html",
    "manager/daily_reports_review.html",
    "manager/dashboard.html",
    "manager/supervisors.html",
]

# Order matters: longer/more-specific compound tokens first.
REPLACEMENTS = [
    (r"\bcol-12__container\b", "card h-100 shadow-sm"),
    (r"\bcol-12__footer\b", "card-footer bg-transparent border-0"),
    (r"\bcol-12__header\b", "card-header"),
    (r"\bcol-12__heading\b", "card-title"),
    (r"\bcol-12__subhead\b", "card-subtitle text-muted"),
    (r"\bcol-12__body\b", "card-body"),
    (r"\bbg-success-subtleer\b", "bg-success-subtle"),
    (r"\bbg-gold-lighter\b", "bg-warning-subtle"),
    (r"\bborder-gold-light\b", "border-gold"),
    (r"\btext-gold-dark\b", "text-gold"),
    (r"alert alert-heading", "alert-heading"),
]

total = 0
for rel in FILES:
    p = ROOT / rel
    text = p.read_text(encoding="utf-8")
    before = text
    file_count = 0
    for pat, repl in REPLACEMENTS:
        text, n = re.subn(pat, repl, text)
        file_count += n
    if text != before:
        p.write_text(text, encoding="utf-8")
    total += file_count
    print(f"{rel}: {file_count} replacements")

print(f"TOTAL: {total}")
