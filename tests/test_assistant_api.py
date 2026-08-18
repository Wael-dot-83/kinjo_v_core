"""tests/test_assistant_api.py — Unit and integration tests for KinJo AI Assistant & Multi-Role Chatbot API.
"""

import pytest
from fastapi.testclient import TestClient
from main import app


@pytest.fixture
def client():
    return TestClient(app)


def test_assistant_chat_arabic_enrollment(client):
    response = client.post(
        "/api/assistant/chat",
        json={"message": "كيف يمكنني تسجيل طفلي في الروضة؟", "lang": "ar", "role": "parent"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "reply" in data
    assert "تسجيل" in data["reply"] or "KinJo" in data["reply"]
    assert data["intent"] == "enrollment"
    assert len(data["actions"]) >= 1
    assert any(a["url"] == "/enrollment/apply" for a in data["actions"])
    assert len(data["suggested_queries"]) >= 1


def test_assistant_chat_arabic_kindergarten_search(client):
    response = client.post(
        "/api/assistant/chat",
        json={"message": "ابحث عن حضانة مرخصة في عمان", "lang": "ar"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["intent"] == "kindergarten_search"
    assert any("/kindergartens" in a["url"] for a in data["actions"])


def test_assistant_chat_arabic_daily_reports(client):
    response = client.post(
        "/api/assistant/chat",
        json={"message": "أين أجد التقارير اليومية لطفلي؟", "lang": "ar", "role": "parent"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["intent"] == "daily_reports"
    assert any("/parent/dashboard" in a["url"] for a in data["actions"])


def test_assistant_chat_supervisor_qa(client):
    response = client.post(
        "/api/assistant/chat",
        json={"message": "كيف أدقق سجل الحضور والنسب القانونية للأطفال؟", "lang": "ar", "role": "supervisor"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["intent"] == "supervisor_qa_audit"
    assert any("supervisor" in a["url"].lower() for a in data["actions"])


def test_assistant_chat_manager_operations(client):
    response = client.post(
        "/api/assistant/chat",
        json={"message": "كيف أدير طلبات التسجيل والسعة الاستيعابية في الحضانة؟", "lang": "ar", "role": "manager"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["intent"] == "manager_operations"
    assert any("dashboard" in a["url"] or "kindergartens" in a["url"] for a in data["actions"])


def test_assistant_chat_english_enrollment(client):
    response = client.post(
        "/api/assistant/chat",
        json={"message": "How do I register or apply for enrollment?", "lang": "en", "role": "parent"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["intent"] == "enrollment"
    assert "KinJo" in data["reply"] or "enroll" in data["reply"].lower()
    assert any(a["url"] == "/enrollment/apply" for a in data["actions"])


def test_assistant_chat_english_support(client):
    response = client.post(
        "/api/assistant/chat",
        json={"message": "I need customer support and contact details", "lang": "en"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["intent"] == "support_and_contact"
    assert any(a["url"] == "/contact" for a in data["actions"])


def test_assistant_chat_general_fallback_arabic(client):
    response = client.post(
        "/api/assistant/chat",
        json={"message": "مرحبا، ما هي هذه المنصة؟", "lang": "ar"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["intent"] == "general_help"
    assert "KinJo" in data["reply"]


def test_assistant_chat_general_fallback_english(client):
    response = client.post(
        "/api/assistant/chat",
        json={"message": "Hello, tell me about this website", "lang": "en"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["intent"] == "general_help"
    assert "KinJo" in data["reply"]


def test_assistant_chat_empty_message(client):
    response = client.post(
        "/api/assistant/chat",
        json={"message": "", "lang": "ar"},
    )
    assert response.status_code in [400, 422]


def test_assistant_chat_oversized_message(client):
    response = client.post(
        "/api/assistant/chat",
        json={"message": "A" * 1001, "lang": "en"},
    )
    assert response.status_code == 422
