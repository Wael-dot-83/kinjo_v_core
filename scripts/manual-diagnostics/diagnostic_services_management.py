import requests
import json

BASE_URL = "http://127.0.0.1:8001"

print("TEST: Kindergarten Services CRUD")

# Login
login_data = {"username": "admin", "password": "admin123"}
resp = requests.post(f"{BASE_URL}/api/auth/login", data=login_data)
assert resp.status_code == 200, f"Login failed: {resp.text}"
token = resp.json()["access_token"]
headers = {"Authorization": f"Bearer {token}"}

# Get a kindergarten
resp = requests.get(f"{BASE_URL}/api/kindergartens", headers=headers)
assert resp.status_code == 200, f"Failed to get kindergartens: {resp.text}"
kindergartens = resp.json().get("kindergartens", []) if isinstance(resp.json(), dict) else resp.json()
assert kindergartens, "No kindergartens found"
kg_id = kindergartens[0]["id"]

# Ensure no duplicate service exists
service_name = "مسبح داخلي"
resp = requests.get(f"{BASE_URL}/api/kindergartens/{kg_id}/services", headers=headers)
assert resp.status_code == 200, f"List services failed: {resp.text}"
services_data = resp.json()
services = services_data["services"] if isinstance(services_data, dict) and "services" in services_data else services_data
for s in services:
    if s["service_name"] == service_name:
        del_resp = requests.delete(f"{BASE_URL}/api/kindergartens/{kg_id}/services/{s['id']}", headers=headers)
        print(f"Deleted pre-existing service: {s['service_name']} (status={del_resp.status_code})")

# Create a service
service_data = {
    "kindergarten_id": kg_id,
    "service_name": service_name,
    "description": "مسبح آمن للأطفال مع إشراف.",
    "enabled_flag": True
}

resp = requests.post(f"{BASE_URL}/api/kindergartens/{kg_id}/services", json=service_data, headers=headers)
print(f"DEBUG: Create service status={resp.status_code}, text={resp.text}")
assert resp.status_code in (200, 201), f"Create service failed: {resp.text}"
try:
    service = resp.json()
except Exception:
    service = None
if not service or not isinstance(service, dict) or not service.get("id"):
    # Fallback: fetch the service by name
    resp2 = requests.get(f"{BASE_URL}/api/kindergartens/{kg_id}/services", headers=headers)
    services_data = resp2.json()
    services = services_data["services"] if isinstance(services_data, dict) and "services" in services_data else services_data
    found = [s for s in services if s["service_name"] == service_name]
    assert found, "Service not found after creation"
    service = found[0]
service_id = service["id"]
print(f" Service created: {service['service_name']}")

# List services
resp = requests.get(f"{BASE_URL}/api/kindergartens/{kg_id}/services", headers=headers)
assert resp.status_code == 200, f"List services failed: {resp.text}"
services_data = resp.json()
services = services_data["services"] if isinstance(services_data, dict) and "services" in services_data else services_data
assert any(s["id"] == service_id for s in services), "Service not found in list"
print(f" Service listed: {len(services)} total")

# Update service
update_data = {"service_name": "مسبح داخلي محدث", "description": "تم تحديث الوصف.", "enabled_flag": False}
resp = requests.put(f"{BASE_URL}/api/kindergartens/{kg_id}/services/{service_id}", json=update_data, headers=headers)
assert resp.status_code == 200, f"Update service failed: {resp.text}"
print(" Service updated.")

# Delete service
resp = requests.delete(f"{BASE_URL}/api/kindergartens/{kg_id}/services/{service_id}", headers=headers)
assert resp.status_code == 204, f"Delete service failed: {resp.text}"
print(" Service deleted.")

print("All services CRUD tests passed!")
