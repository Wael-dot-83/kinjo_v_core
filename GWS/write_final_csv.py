# -*- coding: utf-8 -*-
import json
import csv

with open("matrix_final.json", encoding="utf-8") as f:
    rows = json.load(f)

columns = [
    "ID", "Requirement", "Applicable", "Status Before", "Evidence Before",
    "Gap", "Fix Needed", "Status After", "Evidence After", "Files Changed", "Notes",
]

out_path = r"D:\Final Version\GWS_COMPLIANCE_MATRIX.csv"
with open(out_path, "w", encoding="utf-8-sig", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=columns)
    writer.writeheader()
    for r in rows:
        writer.writerow({c: r.get(c, "") for c in columns})

print("Wrote", out_path, "with", len(rows), "data rows")

# Sanity: re-read and confirm round-trip integrity
with open(out_path, encoding="utf-8-sig") as f:
    reader = csv.DictReader(f)
    read_rows = list(reader)
print("Re-read row count:", len(read_rows))
assert len(read_rows) == len(rows) == 300
ids = {r["ID"] for r in read_rows}
assert len(ids) == 300, f"duplicate or missing IDs: {len(ids)}"
print("All 300 unique IDs confirmed present in the CSV.")
