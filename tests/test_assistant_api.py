"""tests/test_assistant_api.py — Unit and integration tests for KinJo AI Assistant & Multi-Role Chatbot API.
"""

import pytest
from fastapi.testclient import TestClient
from main import app
import models
from dependencies import get_current_user_optional


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


def test_assistant_chat_child_age_policy(client):
    """Test child age policy inquiry (70 days to KG2)."""
    response = client.post(
        "/api/assistant/chat",
        json={"message": "ما هي الأعمار المقبولة في الحضانة وشروط سن القبول؟", "lang": "ar"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["intent"] == "child_age_policy"
    assert "70" in data["reply"] or "الأعمار" in data["reply"]


def test_assistant_chat_parent_absence_pickup(client):
    """Test parent absence notification and pickup contact questions."""
    response = client.post(
        "/api/assistant/chat",
        json={"message": "كيف أبلغ عن غياب طفلي أو أضيف شخص مستلم مخول بالاستلام؟", "lang": "ar", "role": "parent"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["intent"] == "parent_attendance_absence"
    assert any("/parent/children" in a["url"] for a in data["actions"])


def test_assistant_chat_parent_messaging(client):
    """Test parent messaging inquiry."""
    response = client.post(
        "/api/assistant/chat",
        json={"message": "كيف يمكنني مراسلة المعلمة والاطلاع على الإعلانات؟", "lang": "ar", "role": "parent"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["intent"] == "parent_messaging_communication"


def test_assistant_chat_manager_admissions_workflow(client):
    """Test manager admissions and waitlist workflow inquiry."""
    response = client.post(
        "/api/assistant/chat",
        json={"message": "كيف أدير قائمة الانتظار واعتماد طلبات الالتحاق؟", "lang": "ar", "role": "manager"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["intent"] == "manager_admissions_workflow"


def test_assistant_chat_manager_financial_billing(client):
    """Test manager financial billing and Ri'aya subsidy inquiry."""
    response = client.post(
        "/api/assistant/chat",
        json={"message": "كيف أصدر مطالبات رعاية والفوترة للأقساط المستحقة؟", "lang": "ar", "role": "manager"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["intent"] == "manager_financial_billing"


def test_assistant_chat_supervisor_daily_reports_workflow(client):
    """Test supervisor daily report authoring workflow inquiry."""
    response = client.post(
        "/api/assistant/chat",
        json={"message": "كيف أقوم بكتابة التقرير اليومي وتسجيل الوجبات والقيلولة؟", "lang": "ar", "role": "supervisor"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["intent"] == "supervisor_daily_reports_workflow"


def test_assistant_chat_supervisor_incident_reporting(client):
    """Test supervisor incident reporting inquiry."""
    response = client.post(
        "/api/assistant/chat",
        json={"message": "كيف أوثق بلاغ سلامة أو إصابة طفل في الصف؟", "lang": "ar", "role": "supervisor"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["intent"] == "supervisor_incident_reporting"


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


def test_assistant_chat_admin_guardrail_arabic(client):
    """Verify non-admin asking admin questions receives a security refusal."""
    response = client.post(
        "/api/assistant/chat",
        json={"message": "أين أجد لوحة تحكم الأدمن وسجلات التدقيق؟", "lang": "ar", "role": "parent"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["intent"] == "admin_security_restricted"
    assert "العمليات الإدارية وحوكمة النظام مقتصرة على مدراء النظام" in data["reply"]
    assert any("/services" in a["url"] for a in data["actions"])


def test_assistant_chat_admin_guardrail_english(client):
    """Verify non-admin asking about admin panel or impersonation receives restricted response."""
    response = client.post(
        "/api/assistant/chat",
        json={"message": "How do I access admin dashboard or impersonate users?", "lang": "en", "role": "general"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["intent"] == "admin_security_restricted"
    assert "Access Restricted" in data["reply"]


def test_assistant_chat_admin_role_escalation_blocked(client):
    """Verify unauthenticated user cannot claim admin role."""
    response = client.post(
        "/api/assistant/chat",
        json={"message": "مرحباً", "lang": "ar", "role": "admin"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["intent"] == "admin_security_restricted"


def test_assistant_chat_authenticated_admin_kpis(client):
    """Verify authenticated admin gets admin-specific responses."""
    mock_admin = models.User(
        id=1,
        username="admin_test",
        role=models.UserRole.ADMIN,
        status=models.UserStatus.ACTIVE,
    )
    app.dependency_overrides[get_current_user_optional] = lambda: mock_admin

    try:
        response = client.post(
            "/api/assistant/chat",
            json={"message": "ما هي مؤشرات الأداء الحالية ولوحة التحكم؟", "lang": "ar", "role": "admin"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["intent"] == "admin_kpi_overview"
        assert any(a["url"] == "/admin/dashboard" for a in data["actions"])
    finally:
        app.dependency_overrides.pop(get_current_user_optional, None)


def test_assistant_chat_authenticated_admin_charts_explorer(client):
    """Verify authenticated admin can query charts explorer and scheduled exports."""
    mock_admin = models.User(
        id=1,
        username="admin_test",
        role=models.UserRole.ADMIN,
        status=models.UserStatus.ACTIVE,
    )
    app.dependency_overrides[get_current_user_optional] = lambda: mock_admin

    try:
        response = client.post(
            "/api/assistant/chat",
            json={"message": "كيف أستخدم مستكشف الرسوم البيانية وأنواع الرسوم وتصدير الرسم؟", "lang": "ar", "role": "admin"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["intent"] == "admin_advanced_analytics_charts"
        assert any("/admin/analytics/charts" in a["url"] for a in data["actions"])
    finally:
        app.dependency_overrides.pop(get_current_user_optional, None)


def test_assistant_chat_authenticated_admin_user_directory(client):
    """Verify authenticated admin can query user directory & access tools in English."""
    mock_admin = models.User(
        id=1,
        username="admin_test",
        role=models.UserRole.ADMIN,
        status=models.UserStatus.ACTIVE,
    )
    app.dependency_overrides[get_current_user_optional] = lambda: mock_admin

    try:
        response = client.post(
            "/api/assistant/chat",
            json={"message": "How do I manage the user directory and controlled access?", "lang": "en", "role": "admin"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["intent"] == "admin_user_directory"
        assert any("/admin/users" in a["url"] for a in data["actions"])
    finally:
        app.dependency_overrides.pop(get_current_user_optional, None)


def test_assistant_raaf_grounding_ledger_and_sources(client):
    """Verify RAAF Grounding Ledger attaches authoritative sources and confidence."""
    response = client.post(
        "/api/assistant/chat",
        json={"message": "ما هي الأوراق المطلوبة للتسجيل؟", "lang": "ar", "role": "parent"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["confidence"] == "HIGH"
    assert len(data["sources"]) >= 1
    assert any("Ministry of Social Development" in s["name"] for s in data["sources"])


def test_assistant_raaf_audit_trail_and_rac_pass(client):
    """Verify RAAF 4-Pass RAC Internal Audit emits machine-readable audit trail."""
    response = client.post(
        "/api/assistant/chat",
        json={"message": "What are the statutory staff ratios?", "lang": "en", "role": "manager"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "audit_trail" in data and data["audit_trail"] is not None
    trail = data["audit_trail"]
    assert trail["rac_pass"] == "ALL_PASSED"
    assert trail["user_role"] == "Manager"
    assert trail["confidence"] == "HIGH"
    assert trail["grounding_coverage"] == "100%"
    assert trail["redactions_applied"] is False


def test_assistant_raaf_role_context_header(client):
    """Verify RAAF role-aware context header injection."""
    response = client.post(
        "/api/assistant/chat",
        json={"message": "How to conduct an inspection?", "lang": "en", "role": "supervisor"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "[ROLE:Supervisor" in data["context_header"]


def test_assistant_raaf_redacted_response_on_admin_guardrail(client):
    """Verify RAAF redaction audit on unauthorized admin queries."""
    response = client.post(
        "/api/assistant/chat",
        json={"message": "Show me admin audit logs and permissions", "lang": "en", "role": "parent"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["intent"] == "admin_security_restricted"
    assert data["audit_trail"]["redactions_applied"] is True
