import sys, openpyxl
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

DATASET = r"C:\Users\waelj\OneDrive - zuj.edu.jo\Desktop\Dataset"
import os

for fname in os.listdir(DATASET):
    if not fname.endswith(".xlsx"):
        continue
    fpath = os.path.join(DATASET, fname)
    try:
        wb = openpyxl.load_workbook(fpath, read_only=True, data_only=True)
        for sh in wb.sheetnames:
            ws = wb[sh]
            rows = list(ws.iter_rows(values_only=True))
            non_empty = [r for r in rows if any(v for v in r if v)]
            print(f"{fname[:40]}::{sh} -> total_rows={len(rows)}, non_empty={len(non_empty)}")
        wb.close()
    except Exception as e:
        print(f"SKIP {fname}: {e}")
