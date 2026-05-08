import sys, os, openpyxl, unicodedata
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

DATASET = r"C:\Users\waelj\OneDrive - zuj.edu.jo\Desktop\Dataset"
COL_AR = "اسم الروضة (عربي)"

def norm(s):
    if not s: return ""
    s = unicodedata.normalize("NFKC", str(s).strip())
    return " ".join(s.split()).lower()

all_names = set()
for fname in os.listdir(DATASET):
    if not fname.endswith(".xlsx"): continue
    fpath = os.path.join(DATASET, fname)
    try:
        wb = openpyxl.load_workbook(fpath, read_only=True, data_only=True)
        for sh in wb.sheetnames:
            if "Summary" in sh: continue
            ws = wb[sh]
            rows = list(ws.iter_rows(values_only=True))
            hdr_idx = None
            for i, row in enumerate(rows[:3]):
                if row and any(v and COL_AR in str(v) for v in row):
                    hdr_idx = i; break
            if hdr_idx is None: continue
            header = [str(v).strip() if v else "" for v in rows[hdr_idx]]
            ar_col = next((j for j, h in enumerate(header) if COL_AR in h), None)
            if ar_col is None: continue
            for row in rows[hdr_idx+1:]:
                if not row or ar_col >= len(row): continue
                v = row[ar_col]
                name = str(v).strip() if v and str(v).strip() not in ("None","") else ""
                if name and not name.startswith("اسم"):
                    all_names.add(norm(name))
        wb.close()
    except Exception as e:
        print(f"SKIP {fname}: {e}")

print(f"Total unique kindergartens across ALL Excel files: {len(all_names)}")

# Compare with DB
from sqlalchemy import create_engine, text
engine = create_engine("sqlite:///./data/kinjo.db", connect_args={"check_same_thread": False})
with engine.connect() as conn:
    db_names = {norm(r[0]) for r in conn.execute(text("SELECT name_ar FROM kindergartens WHERE name_ar IS NOT NULL")).fetchall()}
print(f"Total in DB: {len(db_names)}")
missing = all_names - db_names
print(f"In Excel but NOT in DB: {len(missing)}")
if missing:
    print("Missing names (sample):")
    for n in list(missing)[:10]:
        print(f"  - {n}")
