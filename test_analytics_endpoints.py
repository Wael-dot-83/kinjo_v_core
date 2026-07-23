import sys
import asyncio
from fastapi.testclient import TestClient

try:
    from main import app
except Exception as e:
    print(f"Error importing app: {e}")
    sys.exit(1)

client = TestClient(app)

def run_tests():
    print("Testing what-if endpoint...")
    res = client.get("/api/analytics/what-if?metric=attendance&adjustment_percent=10&horizon_days=30&period_start=2026-01-01&period_end=2026-06-30")
    if res.status_code == 200:
        data = res.json()
        print("What-If Metadata:", data.get('metadata'))
        print("What-If Summary:", data.get('summary'))
    else:
        print("What-If Error:", res.status_code, res.text)
        
    print("\nTesting risk-heatmap endpoint...")
    res = client.get("/api/analytics/risk-heatmap?period_start=2026-01-01&period_end=2026-06-30&level=national")
    if res.status_code == 200:
        data = res.json()
        print(f"Risk Heatmap returned {len(data.get('items', []))} items.")
        if data.get('items'):
            print("First item:", data['items'][0])
    else:
        print("Risk-Heatmap Error:", res.status_code, res.text)

if __name__ == "__main__":
    run_tests()
