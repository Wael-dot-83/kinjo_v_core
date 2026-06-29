
import json
from fastapi.testclient import TestClient
from tests.test_admin_heatmap_endpoints import _APP, _DB
from heatmap.scripts.seed_snapshot_data import seed_governorates
from heatmap.backend import pipeline

client = TestClient(_APP)
r = client.post(
    '/api/admin/heat-map/alerts/999999/acknowledge',
    headers={'X-CSRF-Token': 'test'},
    cookies={'kinjo_csrf_token': 'test'}
)
print('STATUS:', r.status_code)
print('BODY:', r.text)

