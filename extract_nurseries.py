import re
import json
import csv

# Read the HTML file
with open(r'C:\Users\waelj\.local\share\kilo\tool-output\tool_ef0822499001BDyMRAUWwREy9a', 'r', encoding='utf-8') as f:
    html_content = f.read()

# Find all data rows (excluding the header row-1)
pattern = r'<tr class="row-(\d+)">\s*<td class="column-1">([^<]*)</td><td class="column-2">([^<]*)</td><td class="column-3">([^<]*)</td><td class="column-4">([^<]*)</td>\s*</tr>'

matches = re.findall(pattern, html_content)

records = []
for match in matches:
    row_num = int(match[0])
    if row_num == 1:
        continue
    
    name = match[1].strip()
    address = match[2].strip()
    phone = match[3].strip()
    branch = match[4].strip()
    
    records.append({
        "name": name,
        "address": address,
        "phone": phone,
        "branch": branch,
        "row_number": row_num
    })

records.sort(key=lambda x: x["row_number"])

# Write JSON
with open(r'D:\Final Version\ssc_nurseries.json', 'w', encoding='utf-8') as f:
    json.dump(records, f, ensure_ascii=False, indent=2)

# Write CSV with UTF-8 BOM
with open(r'D:\Final Version\ssc_nurseries.csv', 'w', encoding='utf-8-sig', newline='') as f:
    writer = csv.DictWriter(f, fieldnames=["row_number", "name", "address", "phone", "branch"])
    writer.writeheader()
    writer.writerows(records)

# Validation
expected_rows = set(range(2, 447))
found_rows = set(r["row_number"] for r in records)
missing_rows = expected_rows - found_rows

branches = sorted(set(r["branch"] for r in records))
null_phones = [r for r in records if r["phone"] == "NULL"]
placeholder_phones = [r for r in records if r["phone"] and r["phone"].isdigit() and len(set(r["phone"])) == 1]
zero_phones = [r for r in records if r["phone"] == "0"]

print("=== EXTRACTION SUMMARY ===")
print(f"Total records extracted: {len(records)}")
print(f"Expected records: 445")
if missing_rows:
    print(f"Missing rows: {sorted(missing_rows)}")
else:
    print("All rows present!")

print(f"\n=== BRANCHES ({len(branches)}) ===")
for b in branches:
    count = sum(1 for r in records if r["branch"] == b)
    print(f"  {b}: {count}")

print(f"\n=== DATA QUALITY NOTES ===")
print(f"NULL phones: {len(null_phones)}")
print(f"Placeholder numbers (repeating digits): {len(placeholder_phones)}")
for r in placeholder_phones:
    print(f"  Row {r['row_number']}: {r['phone']} - {r['name']}")
print(f"Zero phone values: {len(zero_phones)}")
for r in zero_phones:
    print(f"  Row {r['row_number']}: {r['phone']} - {r['name']}")

print(f"\n=== FILES CREATED ===")
print(r"JSON: D:\Final Version\ssc_nurseries.json")
print(r"CSV: D:\Final Version\ssc_nurseries.csv")