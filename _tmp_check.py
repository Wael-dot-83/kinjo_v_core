from fastapi.testclient import TestClient
import main
client = TestClient(main.app)
r = client.post('/token', data={'username':'admin','password':'Admin123!'})
print('token', r.status_code, r.text[:200])
if r.status_code == 200:
    headers = {'Authorization': f"Bearer {r.json()['access_token']}"}
    r2 = client.get('/api/analytics/dashboard-data', params={'period_start':'2026-01-01','period_end':'2026-01-31'}, headers=headers)
    print('dash', r2.status_code)
    print(r2.text[:400])
else:
    print('no token')
