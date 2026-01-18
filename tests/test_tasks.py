"""
Comprehensive test suite for Task Management Feature
Tests CRUD operations, permissions, and business logic
Uses shared conftest fixtures for consistent test database
"""
import pytest
from datetime import date, datetime, timedelta


# ============================================================================
# Test Task Creation
# ============================================================================

def test_create_task_valid(client, admin_user, sample_kindergarten):
    """Create task with valid data -> task created successfully"""
    # Login as admin
    login_response = client.post("/token", data={
        "username": admin_user.username,
        "password": "Admin123!"
    })
    assert login_response.status_code == 200
    token = login_response.json()["access_token"]
    
    # Create task
    response = client.post(
        "/api/tasks",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "title": "Review daily reports",
            "description": "Review all pending daily reports",
            "priority": "high"
        }
    )
    
    assert response.status_code == 201
    data = response.json()
    assert data["title"] == "Review daily reports"
    assert data["priority"] == "HIGH"
    assert data["status"] == "PENDING"


def test_create_task_minimal(client, admin_user, sample_kindergarten):
    """Create task with minimal data (title only) -> succeeds with defaults"""
    # Login
    login_response = client.post("/token", data={
        "username": admin_user.username,
        "password": "Admin123!"
    })
    token = login_response.json()["access_token"]
    
    response = client.post(
        "/api/tasks",
        headers={"Authorization": f"Bearer {token}"},
        json={"title": "Simple task"}
    )
    
    assert response.status_code == 201
    data = response.json()
    assert data["title"] == "Simple task"
    assert data["priority"] == "MEDIUM"  # Default priority
    assert data["status"] == "PENDING"


def test_create_task_missing_title(client, admin_user, sample_kindergarten):
    """Create task without title -> validation error"""
    login_response = client.post("/token", data={
        "username": admin_user.username,
        "password": "Admin123!"
    })
    token = login_response.json()["access_token"]
    
    response = client.post(
        "/api/tasks",
        headers={"Authorization": f"Bearer {token}"},
        json={"description": "Task without title"}
    )
    
    assert response.status_code == 422  # Pydantic validation error


def test_create_task_invalid_priority(client, admin_user, sample_kindergarten):
    """Create task with invalid priority -> validation error"""
    login_response = client.post("/token", data={
        "username": admin_user.username,
        "password": "Admin123!"
    })
    token = login_response.json()["access_token"]
    
    response = client.post(
        "/api/tasks",
        headers={"Authorization": f"Bearer {token}"},
        json={"title": "Test task", "priority": "invalid_priority"}
    )
    
    assert response.status_code == 400


def test_create_task_without_auth(client):
    """Create task without authentication -> unauthorized error"""
    response = client.post(
        "/api/tasks",
        json={"title": "Unauthorized task"}
    )
    
    assert response.status_code == 401


# ============================================================================
# Test Task Retrieval
# ============================================================================

def test_get_tasks_empty(client, admin_user, sample_kindergarten):
    """Get tasks when none exist -> returns empty list"""
    login_response = client.post("/token", data={
        "username": admin_user.username,
        "password": "Admin123!"
    })
    token = login_response.json()["access_token"]
    
    response = client.get(
        "/api/tasks",
        headers={"Authorization": f"Bearer {token}"}
    )
    
    assert response.status_code == 200
    assert response.json() == []


def test_get_tasks_with_filters(client, admin_user, sample_kindergarten):
    """Get tasks with priority filter"""
    login_response = client.post("/token", data={
        "username": admin_user.username,
        "password": "Admin123!"
    })
    token = login_response.json()["access_token"]
    
    # Create a high priority task
    client.post(
        "/api/tasks",
        headers={"Authorization": f"Bearer {token}"},
        json={"title": "High priority task", "priority": "high"}
    )
    
    # Create a low priority task
    client.post(
        "/api/tasks",
        headers={"Authorization": f"Bearer {token}"},
        json={"title": "Low priority task", "priority": "low"}
    )
    
    # Get only high priority tasks
    response = client.get(
        "/api/tasks?priority_filter=high",
        headers={"Authorization": f"Bearer {token}"}
    )
    
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["priority"] == "HIGH"


def test_get_task_by_id(client, admin_user, sample_kindergarten):
    """Get a specific task by ID"""
    login_response = client.post("/token", data={
        "username": admin_user.username,
        "password": "Admin123!"
    })
    token = login_response.json()["access_token"]
    
    # Create a task
    create_response = client.post(
        "/api/tasks",
        headers={"Authorization": f"Bearer {token}"},
        json={"title": "Test task"}
    )
    task_id = create_response.json()["id"]
    
    # Get the task
    response = client.get(
        f"/api/tasks/{task_id}",
        headers={"Authorization": f"Bearer {token}"}
    )
    
    assert response.status_code == 200
    assert response.json()["title"] == "Test task"


def test_get_nonexistent_task(client, admin_user, sample_kindergarten):
    """Get non-existent task -> 404"""
    login_response = client.post("/token", data={
        "username": admin_user.username,
        "password": "Admin123!"
    })
    token = login_response.json()["access_token"]
    
    response = client.get(
        "/api/tasks/99999",
        headers={"Authorization": f"Bearer {token}"}
    )
    
    assert response.status_code == 404


# ============================================================================
# Test Task Update
# ============================================================================

def test_update_task_title(client, admin_user, sample_kindergarten):
    """Update task title"""
    login_response = client.post("/token", data={
        "username": admin_user.username,
        "password": "Admin123!"
    })
    token = login_response.json()["access_token"]
    
    # Create a task
    create_response = client.post(
        "/api/tasks",
        headers={"Authorization": f"Bearer {token}"},
        json={"title": "Original title"}
    )
    task_id = create_response.json()["id"]
    
    # Update the task
    response = client.put(
        f"/api/tasks/{task_id}",
        headers={"Authorization": f"Bearer {token}"},
        json={"title": "Updated title"}
    )
    
    assert response.status_code == 200
    assert response.json()["title"] == "Updated title"


def test_update_task_status_to_completed(client, admin_user, sample_kindergarten):
    """Update task status to completed"""
    login_response = client.post("/token", data={
        "username": admin_user.username,
        "password": "Admin123!"
    })
    token = login_response.json()["access_token"]
    
    # Create a task
    create_response = client.post(
        "/api/tasks",
        headers={"Authorization": f"Bearer {token}"},
        json={"title": "Task to complete"}
    )
    task_id = create_response.json()["id"]
    
    # Update status
    response = client.put(
        f"/api/tasks/{task_id}",
        headers={"Authorization": f"Bearer {token}"},
        json={"status": "COMPLETED"}
    )
    
    assert response.status_code == 200
    assert response.json()["status"] == "COMPLETED"
    assert response.json()["completed_at"] is not None


def test_update_task_priority(client, admin_user, sample_kindergarten):
    """Update task priority"""
    login_response = client.post("/token", data={
        "username": admin_user.username,
        "password": "Admin123!"
    })
    token = login_response.json()["access_token"]
    
    # Create a task
    create_response = client.post(
        "/api/tasks",
        headers={"Authorization": f"Bearer {token}"},
        json={"title": "Priority test", "priority": "low"}
    )
    task_id = create_response.json()["id"]
    
    # Update priority
    response = client.put(
        f"/api/tasks/{task_id}",
        headers={"Authorization": f"Bearer {token}"},
        json={"priority": "URGENT"}
    )
    
    assert response.status_code == 200
    assert response.json()["priority"] == "URGENT"


# ============================================================================
# Test Task Toggle
# ============================================================================

def test_toggle_task_pending_to_completed(client, admin_user, sample_kindergarten):
    """Toggle task from PENDING to COMPLETED"""
    login_response = client.post("/token", data={
        "username": admin_user.username,
        "password": "Admin123!"
    })
    token = login_response.json()["access_token"]
    
    # Create a task
    create_response = client.post(
        "/api/tasks",
        headers={"Authorization": f"Bearer {token}"},
        json={"title": "Toggle test"}
    )
    task_id = create_response.json()["id"]
    
    # Toggle to completed
    response = client.post(
        f"/api/tasks/{task_id}/toggle",
        headers={"Authorization": f"Bearer {token}"}
    )
    
    assert response.status_code == 200
    assert response.json()["status"] == "COMPLETED"


def test_toggle_task_completed_to_pending(client, admin_user, sample_kindergarten):
    """Toggle task from COMPLETED back to PENDING"""
    login_response = client.post("/token", data={
        "username": admin_user.username,
        "password": "Admin123!"
    })
    token = login_response.json()["access_token"]
    
    # Create and complete a task
    create_response = client.post(
        "/api/tasks",
        headers={"Authorization": f"Bearer {token}"},
        json={"title": "Toggle back test"}
    )
    task_id = create_response.json()["id"]
    
    # Complete first
    client.post(
        f"/api/tasks/{task_id}/toggle",
        headers={"Authorization": f"Bearer {token}"}
    )
    
    # Toggle back to pending
    response = client.post(
        f"/api/tasks/{task_id}/toggle",
        headers={"Authorization": f"Bearer {token}"}
    )
    
    assert response.status_code == 200
    assert response.json()["status"] == "PENDING"


# ============================================================================
# Test Task Deletion
# ============================================================================

def test_delete_task(client, admin_user, sample_kindergarten):
    """Delete a task"""
    login_response = client.post("/token", data={
        "username": admin_user.username,
        "password": "Admin123!"
    })
    token = login_response.json()["access_token"]
    
    # Create a task
    create_response = client.post(
        "/api/tasks",
        headers={"Authorization": f"Bearer {token}"},
        json={"title": "Task to delete"}
    )
    task_id = create_response.json()["id"]
    
    # Delete the task
    response = client.delete(
        f"/api/tasks/{task_id}",
        headers={"Authorization": f"Bearer {token}"}
    )
    
    assert response.status_code == 204
    
    # Verify it's deleted
    get_response = client.get(
        f"/api/tasks/{task_id}",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert get_response.status_code == 404


def test_delete_nonexistent_task(client, admin_user, sample_kindergarten):
    """Delete non-existent task -> 404"""
    login_response = client.post("/token", data={
        "username": admin_user.username,
        "password": "Admin123!"
    })
    token = login_response.json()["access_token"]
    
    response = client.delete(
        "/api/tasks/99999",
        headers={"Authorization": f"Bearer {token}"}
    )
    
    assert response.status_code == 404


# ============================================================================
# Test Role-Based Access
# ============================================================================

def test_manager_can_create_task(client, manager_user, sample_kindergarten):
    """Manager can create tasks for their kindergarten"""
    login_response = client.post("/token", data={
        "username": manager_user.username,
        "password": "Manager123!"
    })
    token = login_response.json()["access_token"]
    
    response = client.post(
        "/api/tasks",
        headers={"Authorization": f"Bearer {token}"},
        json={"title": "Manager's task", "priority": "medium"}
    )
    
    assert response.status_code == 201
    assert response.json()["title"] == "Manager's task"


def test_supervisor_can_create_task(client, supervisor_user, sample_kindergarten):
    """Supervisor can create tasks"""
    login_response = client.post("/token", data={
        "username": supervisor_user.username,
        "password": "Supervisor123!"
    })
    token = login_response.json()["access_token"]
    
    response = client.post(
        "/api/tasks",
        headers={"Authorization": f"Bearer {token}"},
        json={"title": "Supervisor's task"}
    )
    
    assert response.status_code == 201


# ============================================================================
# Test Edge Cases
# ============================================================================

def test_create_task_with_due_date(client, admin_user, sample_kindergarten):
    """Create task with due date"""
    login_response = client.post("/token", data={
        "username": admin_user.username,
        "password": "Admin123!"
    })
    token = login_response.json()["access_token"]
    
    due_date = (date.today() + timedelta(days=7)).isoformat()
    
    response = client.post(
        "/api/tasks",
        headers={"Authorization": f"Bearer {token}"},
        json={"title": "Task with due date", "due_date": due_date}
    )
    
    assert response.status_code == 201
    assert response.json()["due_date"] == due_date


def test_create_task_with_long_title(client, admin_user, sample_kindergarten):
    """Create task with maximum length title"""
    login_response = client.post("/token", data={
        "username": admin_user.username,
        "password": "Admin123!"
    })
    token = login_response.json()["access_token"]
    
    long_title = "A" * 255  # Maximum length
    
    response = client.post(
        "/api/tasks",
        headers={"Authorization": f"Bearer {token}"},
        json={"title": long_title}
    )
    
    assert response.status_code == 201


def test_create_task_with_empty_string_title(client, admin_user, sample_kindergarten):
    """Create task with empty title -> validation error"""
    login_response = client.post("/token", data={
        "username": admin_user.username,
        "password": "Admin123!"
    })
    token = login_response.json()["access_token"]
    
    response = client.post(
        "/api/tasks",
        headers={"Authorization": f"Bearer {token}"},
        json={"title": ""}
    )
    
    assert response.status_code == 422
