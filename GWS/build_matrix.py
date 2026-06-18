import json
import csv
import sys

DATA = json.load(open('full_checklist_export.json', encoding='utf-8'))

BATCHES = [
    ("raw_batch_1_accessibility.txt", ['A.1.1 Domain Naming Conventions and Uniform Resource Locators','A.1.2 Discoverability and Search Engine Optimization','A.1.3 Cross Browsing and Screen Resolution','A.1.4 Access to Language','A.1.5 Accessibility Actions','A.1.6 Enable Social Media','A.1.7 RSS Feeds Subscription','A.1.8 Web Performance']),
    ("raw_batch_2_nav_homepage.txt", ['U.2.1 Site Navigation and Effective Sitemap','U.2.2 Homepage']),
    ("raw_batch_3_search_icons_forms.txt", ['U.2.3 Search Functionality','U.2.4 The Use of Icons (Iconography)','U.2.5 Images for Web','U.2.6 Web Forms','U.2.7 Animations','U.2.8 Web Design']),
    ("raw_batch_4_sitemap_sitepages.txt", ['C.3.1 Sitemap','C.3.2 Site Pages']),
    ("raw_batch_5_downloads_contact_cms.txt", ['C.3.3 Downloadable Files','C.3.4 Contact Information','C.3.5 Cross Government Information','C.3.6 FAQ','C.3.7 Website Policies','C.3.8 Content Management System']),
    ("raw_batch_6_responsive_security.txt", ['R.4.1 Design for Mobile','R.4.2 Content','S.5.1 OWASP Top 10','S.5.2 HTTPS protocol','S.5.3 Software Updates','S.5.4 Restrict File Uploads','S.5.5 Using Captcha','S.5.6 Users Passwords','S.5.7 Viruses and Malware','S.5.8 Adjust Default Settings','S.5.9 Error Messages','S.5.10. Secure APIs']),
]

VALID_STATUS = {"MATCH", "PARTIAL", "MISMATCH", "N/A"}

rows_out = []
total_expected = 0
for fname, sections in BATCHES:
    authoritative = [d for d in DATA if d['Guideline section'] in sections]
    total_expected += len(authoritative)
    lines = [l.rstrip('\n') for l in open(fname, encoding='utf-8') if l.strip()]
    if len(lines) != len(authoritative):
        print(f"COUNT MISMATCH in {fname}: expected {len(authoritative)}, got {len(lines)}", file=sys.stderr)
    for i, (auth, line) in enumerate(zip(authoritative, lines)):
        parts = line.split('|', 4)
        if len(parts) != 5:
            print(f"BAD LINE in {fname} at position {i}: {line[:80]}", file=sys.stderr)
            continue
        agent_id, status, evidence, gap, fix = [p.strip() for p in parts]
        status = status.upper()
        if status not in VALID_STATUS:
            print(f"BAD STATUS '{status}' in {fname} at position {i} (auth ID {auth['ID']})", file=sys.stderr)
        if agent_id != auth['ID']:
            print(f"ID LABEL MISMATCH at position {i} in {fname}: authoritative={auth['ID']} agent_wrote={agent_id}", file=sys.stderr)
        item_text = (auth['Checklist item'] or '').replace('\n', ' ').strip()
        rows_out.append({
            "ID": auth['ID'],
            "Requirement": item_text,
            "Applicable": "No" if status == "N/A" else "Yes",
            "Status Before": status,
            "Evidence Before": evidence,
            "Gap": gap,
            "Fix Needed": fix,
            "Status After": "",
            "Evidence After": "",
            "Files Changed": "",
            "Notes": "",
        })

print(f"Total authoritative rows across all batches: {total_expected}")
print(f"Total rows built: {len(rows_out)}")

# Verify against full dataset count and ID coverage
all_ids_expected = {d['ID'] for d in DATA}
all_ids_built = {r['ID'] for r in rows_out}
missing = all_ids_expected - all_ids_built
extra = all_ids_built - all_ids_expected
if missing:
    print(f"MISSING IDs ({len(missing)}): {sorted(missing)}", file=sys.stderr)
if extra:
    print(f"EXTRA IDs ({len(extra)}): {sorted(extra)}", file=sys.stderr)

dupes = len(rows_out) - len(all_ids_built)
if dupes:
    print(f"DUPLICATE rows detected: {dupes}", file=sys.stderr)

with open('matrix_working.json', 'w', encoding='utf-8') as f:
    json.dump(rows_out, f, ensure_ascii=False, indent=1)

print("Wrote matrix_working.json")

status_counts = {}
for r in rows_out:
    status_counts[r['Status Before']] = status_counts.get(r['Status Before'], 0) + 1
print("Status counts:", status_counts)
