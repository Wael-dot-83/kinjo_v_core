# KinJo Unicode and Arabic Compliance Report

Date: 2026-07-14

## Scope

The audit covered all tracked first-party Python, Jinja/HTML, JavaScript, JSON,
translation, email-adjacent, configuration, documentation, and test sources. The
application is FastAPI/Jinja/JavaScript; it contains no Blade, PHP, Vue, React,
JSX, or TSX application sources.

## Corruption repaired

- Authentication logout confirmation (corrupt source evidence):
  `Ù‡Ù„ Ø£Ù†Øª Ù…ØªØ£ÙƒØ¯ Ù…Ù† ØªØ³Ø¬ÙŠÙ„ Ø§Ù„Ø®Ø±ÙˆØ¬ØŸ`
  Correct Arabic: `هل أنت متأكد من تسجيل الخروج؟`
- MFA setup and verification messages in `static/js/auth.js` were restored to
  valid Arabic.
- All Arabic content in the forgot-password and reset-password screens was
  restored from mojibake, including titles, labels, validation, loading,
  success, and error messages.
- Shared base-template Arabic accessibility labels and metadata were restored.
- Stale compatibility-source Arabic labels and punctuation were restored.
- Corrupted em dashes and decorative separators in first-party sources were
  normalized to their intended Unicode characters.

## Brand normalization

All tracked first-party occurrences of the Arabic product spelling were changed
to the official `KinJo` spelling. Incorrect `Kingo`, `Kengo`, and `Kenjo`
variants in localization overrides were also corrected. Arabic sentences and
RTL structure were otherwise preserved.

## Encoding controls

- All audited first-party text decodes strictly as UTF-8.
- Base HTML layouts declare `<meta charset="UTF-8">`.
- HTML and JavaScript responses receive an explicit UTF-8 charset through the
  application middleware.
- PostgreSQL connections request `client_encoding=utf8`.
- SQLite connections retain `PRAGMA encoding = 'UTF-8'`.

`utf8mb4` and `utf8mb4_unicode_ci` are MySQL-specific settings and do not apply
to KinJo's PostgreSQL production database. PostgreSQL's corresponding server
encoding is `UTF8`; Arabic and supplementary Unicode characters are supported
without a separate `utf8mb4` charset.

## Database record verification

The available local SQLite databases were scanned across text columns. No
mojibake strings or stale Arabic product-name records were found. Production
data was not mutated; the same scan must be run through an approved,
read-only production connection before deployment if production records are in
scope.

## Permanent prevention

`scripts/manual-diagnostics/audit_unicode_integrity.py` performs strict UTF-8,
mojibake-marker, and brand-spelling checks across tracked first-party text.
`tests/test_unicode_integrity.py` makes those checks, HTML metadata, response
headers, and database client-encoding controls regression gates.

## Verdict

UTF-8 COMPLIANT for the audited codebase and available local data.
