# Integration into KinJo main.py

Add these lines to `D:\Final Version\main.py` to mount the heatmap router:

```python
# At top of main.py, with other imports:
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from heatmap.backend.api.router import router as heatmap_router
from heatmap.backend.etl.pipeline import create_scheduler

# After app = FastAPI(...):
app.include_router(heatmap_router, prefix="/api/heatmap")

# Inside lifespan or startup event — start daily scheduler:
scheduler = create_scheduler(
    data_source="heatmap/data/test_data.csv",
    cron_hour=2,
    cron_minute=0,
)
scheduler.start()
```

## pip install extras

```bash
pip install apscheduler tenacity scipy
```

(numpy, pandas, scikit-learn already present in requirements.txt)

## Frontend quick start

```bash
cd heatmap/frontend
npm install
npm run dev
# Opens at http://localhost:5173
# Proxies /api → http://localhost:8000
```

## Seed test data

```bash
cd heatmap
python scripts/seed_test_data.py
```

## Docker

```bash
cd heatmap
docker compose up
# API: http://localhost:8000/api/heatmap
# UI:  http://localhost:5173
# Docs: http://localhost:8000/docs
```

## Replacing with real Jordan GeoJSON

Download official boundaries from GADM Level 1/2:
https://gadm.org/download_country.html?country=JOR

Replace `heatmap/data/jordan_admin.geojson` ensuring:
- `properties.admin_code` matches admin_ids in your payload (JO-AM, JO-IR, …)
- `properties.name` and `properties.name_ar` are present
- `properties.level` = "governorate" | "qada"
