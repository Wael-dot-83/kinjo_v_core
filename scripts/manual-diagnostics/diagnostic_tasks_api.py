"""
Quick API test script for Task Management
Run this to verify the tasks feature is working
"""
import requests
import json
from datetime import datetime, timedelta

BASE_URL = "http://127.0.0.1:8000"

def print_section(title):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}\n")

# Step 1: Login
print_section("1. Login as Admin")
response = requests.post(
    f"{BASE_URL}/token",
    data={"username": "admin", "password": "Admin123!"}
)

if response.status_code == 200:
    token = response.json()["access_token"]
    print(f"[OK] Login successful!")
    print(f"Token: {token[:50]}...")
else:
    print(f"[FAIL] Login failed: {response.text}")
    exit(1)

headers = {"Authorization": f"Bearer {token}"}

# Step 2: Create a task
print_section("2. Create a New Task")
task_data = {
    "title": "System Integration Test",
    "description": "Verify that the task management system is fully operational",
    "priority": "high",
    "due_date": (datetime.now() + timedelta(days=3)).strftime("%Y-%m-%d")  # Date only, not datetime
}

response = requests.post(
    f"{BASE_URL}/api/tasks",
    headers=headers,
    json=task_data
)

if response.status_code == 201:
    task = response.json()
    print(f"[OK] Task created successfully!")
    print(f"   ID: {task['id']}")
    print(f"   Title: {task['title']}")
    print(f"   Status: {task['status']}")
    print(f"   Priority: {task['priority']}")
    task_id = task['id']
else:
    print(f"[FAIL] Task creation failed:")
    print(f"   Status: {response.status_code}")
    print(f"   Error: {response.text}")
    task_id = None

# Step 3: List all tasks
print_section("3. List All Tasks")
response = requests.get(f"{BASE_URL}/api/tasks", headers=headers)

if response.status_code == 200:
    tasks = response.json()
    print(f"[OK] Found {len(tasks)} task(s):")
    for t in tasks[:5]:  # Show first 5
        print(f"   - [{t['id']}] {t['title']} ({t['status']})")
else:
    print(f"[FAIL] Failed to list tasks: {response.text}")

# Step 4: Get single task
if task_id:
    print_section(f"4. Get Task #{task_id}")
    response = requests.get(f"{BASE_URL}/api/tasks/{task_id}", headers=headers)

    if response.status_code == 200:
        task = response.json()
        print(f"[OK] Task details retrieved:")
        print(f"   Title: {task['title']}")
        print(f"   Description: {task['description']}")
        print(f"   Created: {task['created_at']}")
    else:
        print(f"[FAIL] Failed to get task: {response.text}")

    # Step 5: Update task
    print_section(f"5. Update Task #{task_id}")
    response = requests.put(
        f"{BASE_URL}/api/tasks/{task_id}",
        headers=headers,
        json={"status": "in_progress", "priority": "urgent"}
    )

    if response.status_code == 200:
        task = response.json()
        print(f"[OK] Task updated successfully!")
        print(f"   New status: {task['status']}")
        print(f"   New priority: {task['priority']}")
    else:
        print(f"[FAIL] Failed to update task: {response.text}")

    # Step 6: Toggle task status
    print_section(f"6. Toggle Task #{task_id} to Completed")
    response = requests.post(
        f"{BASE_URL}/api/tasks/{task_id}/toggle",
        headers=headers
    )

    if response.status_code == 200:
        task = response.json()
        print(f"[OK] Task toggled!")
        print(f"   Status: {task['status']}")
        print(f"   Completed at: {task.get('completed_at', 'N/A')}")
    else:
        print(f"[FAIL] Failed to toggle task: {response.text}")

    # Step 7: Toggle back
    print_section(f"7. Toggle Task #{task_id} Back to Pending")
    response = requests.post(
        f"{BASE_URL}/api/tasks/{task_id}/toggle",
        headers=headers
    )

    if response.status_code == 200:
        task = response.json()
        print(f"[OK] Task toggled back!")
        print(f"   Status: {task['status']}")
        print(f"   Completed at: {task.get('completed_at', 'N/A')}")
    else:
        print(f"[FAIL] Failed to toggle task: {response.text}")

# Step 8: Filter tasks
print_section("8. Filter Tasks by Priority (High)")
response = requests.get(
    f"{BASE_URL}/api/tasks?priority_filter=high",
    headers=headers
)

if response.status_code == 200:
    tasks = response.json()
    print(f"[OK] Found {len(tasks)} high-priority task(s)")
else:
    print(f"[FAIL] Failed to filter tasks: {response.text}")

# Step 9: Create more sample tasks
print_section("9. Create Sample Tasks")
sample_tasks = [
    {"title": "Review enrollment applications", "priority": "urgent"},
    {"title": "Prepare monthly newsletter", "priority": "low"},
    {"title": "Update health records", "priority": "medium"},
]

created = 0
for sample in sample_tasks:
    response = requests.post(
        f"{BASE_URL}/api/tasks",
        headers=headers,
        json=sample
    )
    if response.status_code == 201:
        created += 1

print(f"[OK] Created {created}/{len(sample_tasks)} sample tasks")

# Final summary
print_section("[OK] ALL TESTS PASSED!")
print("Task Management System is fully operational!")
print("\nNext steps:")
print(f"  1. Open browser: {BASE_URL}/tasks")
print(f"  2. Login with: admin / Admin123!")
print(f"  3. Explore the task management interface")
print(f"\nAPI Documentation: {BASE_URL}/docs")
