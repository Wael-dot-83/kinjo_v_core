# Official Agency Logos — Asset Status

**Project:** KinJo Administration Dashboard & Official Agency Reports
**Last reviewed:** 2026-07-09
**Owner action required:** supply approved official SVG/PNG assets before production branding.

## Rules applied

1. No official, fake, placeholder, or approximated government logos are committed.
2. Until the product owner supplies approved assets, every agency renders a
   **neutral initials fallback badge** (e.g. `MOSD`, `MOE`, `MOH`, `MOL`,
   `SSC`, `DOS`, `NCFA`). The fallback is explicitly **not** presented as an
   official logo (`official: false`, `path: null`).
3. The backend re-checks file existence at request time. Dropping an approved
   `static/img/agencies/<code>.svg` automatically promotes it to `official`
   without code changes.
4. The agency name is always rendered as real text beside the logo, so identity
   never depends on the image alone.

## Asset status table

| Agency | Code | Expected asset path | Official asset present | Fallback used | Source / owner confirmation | Date confirmed | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| وزارة التنمية الاجتماعية | mosd | /static/img/agencies/mosd.svg | No | Yes (MOSD) | Not yet provided by owner | 2026-07-09 | Awaiting approved SVG |
| وزارة التربية والتعليم | moe | /static/img/agencies/moe.svg | No | Yes (MOE) | Not yet provided by owner | 2026-07-09 | Name corrected to وزارة التربية والتعليم |
| وزارة الصحة | moh | /static/img/agencies/moh.svg | No | Yes (MOH) | Not yet provided by owner | 2026-07-09 | Awaiting approved SVG |
| وزارة العمل | mol | /static/img/agencies/mol.svg | No | Yes (MOL) | Not yet provided by owner | 2026-07-09 | Awaiting approved SVG |
| المؤسسة العامة للضمان الاجتماعي | ssc | /static/img/agencies/ssc.svg | No | Yes (SSC) | Not yet provided by owner | 2026-07-09 | Added to official scope; reports require structured data |
| دائرة الإحصاءات العامة | dos | /static/img/agencies/dos.svg | No | Yes (DOS) | Not yet provided by owner | 2026-07-09 | Awaiting approved SVG |
| المجلس الوطني لشؤون الأسرة | ncfa | /static/img/agencies/ncfa.svg | No | Yes (NCFA) | Not yet provided by owner | 2026-07-09 | Awaiting approved SVG |

## Additional (non-official) agency

| Agency | Code | In registry | In official scope | Notes |
| --- | --- | --- | --- | --- |
| وزارة التخطيط والتعاون الدولي | mopic | Yes | No | Retained for an existing ready report; excluded from the official catalog/summary and shown only via direct report routes. |

## How to add an official asset

1. Obtain the approved SVG (preferred) or PNG from the agency / product owner.
2. Place it at `static/img/agencies/<code>.svg` (e.g. `mosd.svg`).
3. Update `AGENCY_LOGOS[<code>]["asset_present"] = True` in
   `agency_reports_registry.py` (or rely on the runtime file-existence check).
4. Re-run `pytest tests/test_admin_agency_logos.py` — the logo-path test
   verifies the file exists and is flagged official.

## Non-goals

- No hotlinked external logos.
- No fabricated or approximated branding.
- No exported/branded report headers are produced (the backend does not
  support branded exports for these reports).