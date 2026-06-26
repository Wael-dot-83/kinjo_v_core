import sys
import os
from fastapi.testclient import TestClient
from main import app
from dependencies import get_current_user
import models

def override_get_current_user():
    user = models.User(id=1, username="admin", role=models.UserRole.ADMIN, full_name="Admin User")
    return user

app.dependency_overrides[get_current_user] = override_get_current_user

client = TestClient(app)

response = client.get("/api/analytics/drilldown/governorate/Amman?start_date=2023-01-01&end_date=2024-01-01")
print("Drilldown Response Code:", response.status_code)
print("Drilldown Response Body:", response.text[:500])

response_preview = client.post("/api/analytics/reports/preview", json={
    "report_type": "attendance",
    "period_start": "2023-01-01",
    "period_end": "2024-01-01",
    "filters": {}
})
print("Preview Response Code:", response_preview.status_code)
print("Preview Response Body:", response_preview.text[:500])
