# Official Agency Logos — drop location

Place approved official logo assets here, one per agency, named by code:

- mosd.svg  (وزارة التنمية الاجتماعية)
- moe.svg   (وزارة التربية والتعليم)
- moh.svg   (وزارة الصحة)
- mol.svg    (وزارة العمل)
- ssc.svg    (المؤسسة العامة للضمان الاجتماعي)
- dos.svg    (دائرة الإحصاءات العامة)
- ncfa.svg   (المجلس الوطني لشؤون الأسرة)

Rules:
- SVG is preferred. PNG is acceptable only if SVG is unavailable.
- Use ONLY assets officially provided by the agency / product owner.
- Do NOT commit unofficial, approximated, or placeholder logos.
- After adding a file, set asset_present=True for that code in
  agency_reports_registry.AGENCY_LOGOS so the UI promotes it to official.
- The backend also re-checks file existence at request time, so the logo
  becomes official automatically once the file is present.

Current status (2026-07-09): no official assets committed yet. Every agency
renders a neutral initials fallback badge. See ../../docs/agency_logos.md.