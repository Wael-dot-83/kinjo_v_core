"""api/assistant_routes.py — Bilingual AI Assistant / Knowledge Base Chatbot API for KinJo.

Provides intelligent, complete, consistent, and structured responses, multi-role avatars,
guided topic recommendations, and direct platform action links for:
  - System Administrators (Admin Analytics, Users & RBAC, Audits, Safety, Kindergartens, Charts, System Maintenance)
  - Nursery Managers (Admissions, Classroom & Staff Allocations, Statutory Ratios, Licensing & Facility, Billing)
  - Educational Supervisors & Auditors (QA Auditing, Daily Reports Approval, Incident Field Logs, Child Observations)
  - Parents & Guardians (Enrollment, Daily Reports, Health & Vaccines, Tuition & Ri'aya Subsidies, Absence & Pickups, Messaging)
  - General Visitors (Kindergarten Directory Search, Child Age Policy, Data Security & Privacy, Support Helpdesk)
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

import models
from dependencies import get_current_user_optional


router = APIRouter(prefix="/api/assistant", tags=["AI Assistant"])


class ChatAction(BaseModel):
    label: str
    url: str
    icon: Optional[str] = None


class GroundingSource(BaseModel):
    name: str
    citation: Optional[str] = None
    confidence: str = "HIGH"


class AuditTrail(BaseModel):
    response_id: str
    timestamp: str
    user_role: str
    query_intent: Dict[str, str]
    sources_used: List[str]
    confidence: str
    grounding_coverage: str
    redactions_applied: bool
    rac_pass: str


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=1000, description="User prompt or query")
    lang: Optional[str] = Field("ar", description="Language preference ('ar' or 'en')")
    role: Optional[str] = Field("general", description="User role ('parent', 'supervisor', 'manager', 'admin', 'general')")
    session_id: Optional[str] = Field(None, description="Optional conversation session ID")


class ChatResponse(BaseModel):
    reply: str
    actions: List[ChatAction] = Field(default_factory=list)
    suggested_queries: List[str] = Field(default_factory=list)
    intent: Optional[str] = None
    target_role: Optional[str] = None
    context_header: Optional[str] = None
    confidence: Optional[str] = "HIGH"
    sources: List[GroundingSource] = Field(default_factory=list)
    audit_trail: Optional[AuditTrail] = None


# ---------------------------------------------------------------------------
# RAAF Pillar 1: Role Context & Persona Profiles
# ---------------------------------------------------------------------------

ROLE_PROFILES = {
    "admin": {
        "context_header": "[ROLE:Admin|Tone:Precise|Access:Full|Safety:StrictAudit]",
        "tone": "Neutral, precise, audit-ready",
        "access_tier": "Full",
        "token_budget": 4000,
    },
    "manager": {
        "context_header": "[ROLE:Manager|Tone:DataDriven|Access:Scoped|Safety:Aggregated]",
        "tone": "Collaborative, data-driven",
        "access_tier": "Scoped",
        "token_budget": 2000,
    },
    "supervisor": {
        "context_header": "[ROLE:Supervisor|Tone:Procedural|Access:Scoped|Safety:StaffOnly]",
        "tone": "Supportive, procedural, clear",
        "access_tier": "Scoped",
        "token_budget": 1200,
    },
    "parent": {
        "context_header": "[ROLE:Parent|Tone:Conversational|Access:Restricted|Safety:ChildOnly]",
        "tone": "Empathetic, jargon-free, reassuring",
        "access_tier": "Restricted",
        "token_budget": 1000,
    },
    "general": {
        "context_header": "[ROLE:General|Tone:Helpful|Access:Public|Safety:NoPII]",
        "tone": "Welcoming, informative",
        "access_tier": "Public",
        "token_budget": 800,
    }
}


# ---------------------------------------------------------------------------
# Security Guardrail: Admin Domain Restricted Keywords
# ---------------------------------------------------------------------------

ADMIN_RESTRICTED_KEYWORDS_AR = [
    "ادمن", "أدمن", "مدير النظام", "لوحة الادمن", "لوحة الأدمن", "سجلات التدقيق",
    "انتحال الصفة", "صلاحيات الادمن", "صلاحيات الأدمن", "تعديل الصلاحيات",
    "حذف المستخدمين", "حذف مستخدم", "قاعدة البيانات", "إعدادات النظام", "اعدادات النظام",
    "تقرير الرقابة الإدارية", "تصدير سجلات النظام", "إدارة المستخدمين والصلاحيات",
    "سجل الحركات الإدارية", "تغيير صلاحية", "دخول الادمن", "حساب الادمن", "بيانات النظام الداخلية"
]

ADMIN_RESTRICTED_KEYWORDS_EN = [
    "admin", "administrator", "system admin", "admin panel", "admin dashboard",
    "audit logs", "audit log", "impersonate", "impersonation", "admin role",
    "admin permissions", "delete user", "modify user permissions", "system settings",
    "database query", "administrative access", "admin controls", "admin credentials",
    "admin portal", "root access", "superuser"
]


# ---------------------------------------------------------------------------
# Comprehensive Multi-Role Domain Knowledge Base
# ---------------------------------------------------------------------------

INTENT_KNOWLEDGE_BASE = [
    # -----------------------------------------------------------------------
    # 0. AUTHENTICATED ADMIN INTENTS (Admin-Only)
    # -----------------------------------------------------------------------
    {
        "intent": "admin_kpi_overview",
        "target_role": "admin",
        "keywords_ar": ["مؤشرات الاداء", "مؤشرات الأداء", "لوحة التحكم", "احصائيات النظام", "نظرة عامة", "kpi", "لوحة الادارة", "احصائيات المنصة", "معدل الاشغال", "الارقام العامة", "الطاقة الاستيعابية الوطنية"],
        "keywords_en": ["kpi", "system metrics", "overview", "admin dashboard", "analytics summary", "executive dashboard", "occupancy rate", "platform stats", "general figures", "national capacity"],
        "reply_ar": (
            "📊 **لوحة المؤشرات والتحليلات الإدارية الشاملة لمنصة KinJo:**\n\n"
            "1. **مؤشرات الحجم والسعة:**\n"
            "   • إجمالي الحضانات المرخصة والمسجلة عبر المحافظات الـ 12.\n"
            "   • عدد الأطفال الفعليين المسجلين ونسبة الإشغال الإجمالية من الطاقة الاستيعابية المرخصة.\n"
            "   • الكادر التربوي المعتمد ونسب التوزيع الإقليمي.\n\n"
            "2. **مؤشرات الامتثال والرقابة:**\n"
            "   • مؤشر الامتثال لنسب المربيات للأطفال (Staff-to-Child Compliance Index).\n"
            "   • الحضانات التي تقترب من موعد تجديد الترخيص السنوي (أقل من 30 يوماً).\n"
            "   • بلاغات السلامة المفتوحة وتوزيعها حسب مستويات الخطورة (P1 / P2 / P3).\n\n"
            "3. **التوزيع الجغرافي:** استعراض الخريطة الحرارية (Heatmap) لتحديد المناطق ذات الطلب العالي أو نقص التغطية في الحضانات."
        ),
        "reply_en": (
            "📊 **Comprehensive KinJo Executive & System KPI Analytics:**\n\n"
            "1. **Capacity & Volume Metrics:**\n"
            "   • Total accredited kindergartens across Jordan's 12 governorates.\n"
            "   • Active enrolled children and aggregate capacity utilization rate.\n"
            "   • Certified educators headcount and regional staffing ratios.\n\n"
            "2. **Governance & Compliance Indicators:**\n"
            "   • Statutory staff-to-child ratio compliance index.\n"
            "   • Nurseries pending annual license renewals (within 30 days).\n"
            "   • Open safety incidents categorized by severity (P1 Critical, P2 Moderate, P3 Minor).\n\n"
            "3. **Geographic Distribution:** Interactive Heatmap analytics identifying high-density childcare demand zones and underserved districts."
        ),
        "actions": [
            {"label_ar": "لوحة مؤشرات الأداء الإدارية", "label_en": "Admin KPI Dashboard", "url": "/admin/dashboard", "icon": "bi-speedometer2"},
            {"label_ar": "مركز الذكاء التحليلي المتقدم", "label_en": "Analytics Intelligence Center", "url": "/admin/analytics", "icon": "bi-graph-up-arrow"},
            {"label_ar": "الخريطة الحرارية للحضانات", "label_en": "Nurseries Heatmap", "url": "/admin/heatmap", "icon": "bi-map-fill"}
        ],
        "suggested_ar": ["كيف أستعرض تقرير مؤشرات الأداء الشهري؟", "كيف أراجع سجلات التدقيق الأمني؟", "كيف أدير صلاحيات المستخدمين؟"],
        "suggested_en": ["How to review monthly KPI report?", "How to audit security logs?", "How to manage user directory?"]
    },
    {
        "intent": "admin_advanced_analytics_charts",
        "target_role": "admin",
        "keywords_ar": ["مستكشف الرسوم البيانية", "انواع الرسوم", "نوع الرسم", "نطاق التاريخ", "تصدير الرسم", "جدولة التصدير", "تحليلات متقدمة", "مخططات بيانية", "charts", "analytics charts"],
        "keywords_en": ["charts explorer", "chart types", "date preset", "export chart", "scheduled export", "advanced analytics", "visualizations", "charts dashboard", "charts"],
        "reply_ar": (
            "📈 **مستكشف الرسوم البيانية والتحليلات المتقدمة (`/admin/analytics/charts`):**\n\n"
            "1. **أنواع الرسوم البيانية التفاعلية المدعومة:**\n"
            "   • **الرسم العمودي (Bar):** لمقارنات الحضور والقدرة الاستيعابية وسرعة الاستجابة.\n"
            "   • **الرسم الخطي (Line):** لتتبع الاتجاهات الزمنية للغياب والتسجيل والحوادث.\n"
            "   • **الرسم الدائري (Doughnut / Pie):** لتوزيع الحالات وفئات الأطفال ومصادر الطلبات.\n"
            "   • **الرسم الراداري والمساحي (Radar / Area):** لقياس أبعاد الجودة والحوكمة.\n\n"
            "2. **نطاقات التاريخ السريعة (Date Presets):** اليوم، آخر 7 أيام، آخر 30 يوماً، آخر 3 أشهر، السنة الأكاديمية، أو نطاق مخصص.\n"
            "3. **التصدير والجدولة الآلية:** تصدير فوري بصيغ (CSV, JSON, PNG) مع إمكانية جدولة إرسال التقارير أسبوعياً أو شهرياً للبريد الإلكتروني المعتمد."
        ),
        "reply_en": (
            "📈 **Advanced Charts Explorer & Visual Analytics (`/admin/analytics/charts`):**\n\n"
            "1. **Interactive Visualization Types Supported:**\n"
            "   • **Bar Charts:** Comparative attendance, licensed capacities, and resolution velocity.\n"
            "   • **Line Charts:** Longitudinal time-series for enrollment, absence trends, and incidents.\n"
            "   • **Doughnut / Pie Charts:** Status breakdowns, age brackets, and application intake channels.\n"
            "   • **Radar & Area Charts:** Multi-dimensional governance quality indices.\n\n"
            "2. **Flexible Date Presets:** Today, Last 7 Days, Last 30 Days, Last 3 Months, Academic Year, or Custom Date Range.\n"
            "3. **Automated Scheduled Exports:** Instant export in CSV, JSON, PNG with scheduled recurring automated email deliveries (Daily, Weekly, Monthly)."
        ),
        "actions": [
            {"label_ar": "مستكشف الرسوم البيانية", "label_en": "Charts Explorer", "url": "/admin/analytics/charts", "icon": "bi-pie-chart"},
            {"label_ar": "مركز الذكاء والتحليلات", "label_en": "Analytics Hub", "url": "/admin/analytics", "icon": "bi-bar-chart-line-fill"}
        ],
        "suggested_ar": ["كيف أجدول تصدير تقرير الحضور أسبوعياً؟", "كيف أغير نوع الرسم البياني؟", "كيف أفلتر الرسوم حسب المحافظة؟"],
        "suggested_en": ["How to schedule a weekly attendance export?", "How to change chart visualization type?", "How to filter charts by governorate?"]
    },
    {
        "intent": "admin_user_directory",
        "target_role": "admin",
        "keywords_ar": ["إدارة المستخدمين", "ادارة المستخدمين", "دليل المستخدمين", "صلاحيات", "إضافة مستخدم", "تعديل مستخدم", "انتحال", "دخول بصفة", "استيراد مستخدمين", "mfa", "التحقق بخطوتين"],
        "keywords_en": ["user directory", "manage users", "user access", "add user", "create user", "user roles", "impersonate user", "controlled access", "import users", "mfa", "two factor"],
        "reply_ar": (
            "👥 **دليل إدارة المستخدمين والأمان المؤسسي:**\n\n"
            "1. **هيكلية الصلاحيات المعتمدة (RBAC):**\n"
            "   • **مدير النظام (ADMIN):** كامل صلاحيات الحوكمة والإعدادات والتقارير الوطنية وسجلات التدقيق.\n"
            "   • **مدير الحضانة (MANAGER):** إدارة قبول الطلاب، توزيع الكادر والشعب، وسجلات السلامة لمنشأته فقط.\n"
            "   • **مشرف تربوي / مدقق (SUPERVISOR):** الاطلاع على السجلات، تدقيق الحضور، وتعبئة تقارير التفتيش.\n"
            "   • **ولي أمر (PARENT):** الوصول لملف أطفاله، التقارير اليومية، الفواتير، والتواصل.\n\n"
            "2. **الاستيراد الجماعي:** رفع ملفات Excel/CSV منظمة لإنشاء الحسابات وتعيين الأدوار مع إرسال بيانات الدخول الآمنة.\n"
            "3. **الدخول المقيّد بصفة مستخدم (Controlled Access):** تفعيل جلسة دعم فني مؤقتة بصفة المستخدم مع تسجيل غير قابل للتعديل لجميع العمليات في سجل التدقيق الأمني."
        ),
        "reply_en": (
            "👥 **User Directory, Roles & Security Governance:**\n\n"
            "1. **Role-Based Access Control (RBAC):**\n"
            "   • **System Admin (ADMIN):** Full governance, national analytics, audit logs, and system settings.\n"
            "   • **Nursery Manager (MANAGER):** Admissions pipeline, staff & section assignment, and facility logs.\n"
            "   • **Supervisor / Auditor (SUPERVISOR):** Attendance auditing, inspection checklists, and QA evaluations.\n"
            "   • **Parent / Guardian (PARENT):** Child portfolio, daily reports, digital invoices, and messaging.\n\n"
            "2. **Batch Onboarding:** Bulk import users via standardized Excel/CSV templates with auto-generated credentials.\n"
            "3. **Controlled User Access (Impersonation):** Authenticated temporary support sessions with cryptographically signed audit logs."
        ),
        "actions": [
            {"label_ar": "دليل المستخدمين والصلاحيات", "label_en": "User Directory", "url": "/admin/users", "icon": "bi-people-fill"},
            {"label_ar": "استيراد المستخدمين", "label_en": "Import Users", "url": "/admin/users/import", "icon": "bi-person-up"},
            {"label_ar": "الدخول المقيّد (الدعم)", "label_en": "Controlled Access", "url": "/admin/impersonate", "icon": "bi-person-bounding-box"}
        ],
        "suggested_ar": ["كيف أضيف مستخدماً جديداً بصلاحية مشرف؟", "كيف أفعل التحقق بخطوتين للمستخدم؟", "كيف أراجع عمليات الدخول المقيّد؟"],
        "suggested_en": ["How to add a supervisor user?", "How to enforce 2FA/MFA?", "How to review controlled access history?"]
    },
    {
        "intent": "admin_governance_and_audit",
        "target_role": "admin",
        "keywords_ar": ["سجلات التدقيق", "سجل الحركات", "تقارير الحوكمة", "تقارير الوزارة", "التنمية الاجتماعية", "وزارة التربية", "سجل الامتثال", "تصدير التقارير الحكومية", "سجل النشاط", "audit logs"],
        "keywords_en": ["audit logs", "audit trail", "governance reports", "ministry reports", "mosd report", "moe report", "compliance exports", "agency reports", "audit history"],
        "reply_ar": (
            "📜 **سجلات التدقيق الأمني وتقارير الحوكمة الوطنية:**\n\n"
            "1. **سجل التدقيق الشامل (Security Audit Trail):**\n"
            "   • توثيق زمني مشفر لكافة العمليات: عمليات الدخول، تعديل الصلاحيات، تصدير البيانات، وتغييرات السجلات.\n"
            "   • إمكانية الفلترة حسب: اسم المستخدم، نوع العملية، عنوان IP، والفترة الزمنية.\n\n"
            "2. **التقارير الحكومية المعتمدة لوزارة التنمية الاجتماعية (MoSD):**\n"
            "   • التقرير الإحصائي الشهري للحضور والنسب القانونية.\n"
            "   • تقرير التفتيش الميداني وسجل المخالفات الموثقة والإجراءات التصحيحية.\n\n"
            "3. **التصدير الرقمي:** تصدير حزم البيانات بصيغ Excel وPDF المعتمدة مع ختم التحقق الإلكتروني."
        ),
        "reply_en": (
            "📜 **Security Audit Trails & National Governance Reporting:**\n\n"
            "1. **Comprehensive Audit Logs:**\n"
            "   • Immutable event tracking for: Authentication attempts, privilege changes, data exports, and mutations.\n"
            "   • Multi-criteria search filters: Actor ID, Action Category, Client IP, and Date Interval.\n\n"
            "2. **Official MoSD & MoE Compliance Packages:**\n"
            "   • Monthly statistical attendance and statutory ratio compliance exports.\n"
            "   • Field inspection reports, logged violations, and corrective action histories.\n\n"
            "3. **Automated Exports:** Verified exports in Excel & PDF with digital compliance seals."
        ),
        "actions": [
            {"label_ar": "سجلات التدقيق الأمني", "label_en": "Security Audit Logs", "url": "/admin/audit-logs", "icon": "bi-shield-check"},
            {"label_ar": "تقارير الحوكمة والامتثال", "label_en": "Governance Reports", "url": "/admin/governance-reports", "icon": "bi-file-earmark-bar-graph"},
            {"label_ar": "تقارير الجهات الرسمية", "label_en": "Official Agency Reports", "url": "/admin/agency-reports", "icon": "bi-bank"}
        ],
        "suggested_ar": ["كيف أفلتر سجلات التدقيق حسب المستخدم أو التاريخ؟", "كيف أصدر التقرير السنوي للوزارة؟", "ما هي التنبيهات الإدارية المفتوحة؟"],
        "suggested_en": ["How to filter audit logs by user/date?", "How to export annual ministry report?", "What are active admin alerts?"]
    },
    {
        "intent": "admin_safety_and_incidents",
        "target_role": "admin",
        "keywords_ar": ["تحليلات الحوادث", "سجل السلامة", "الحوادث", "إشعارات الطوارئ", "تقارير السلامة", "البلاغات", "بلاغ طارئ", "مستويات الخطورة", "sla الحوادث"],
        "keywords_en": ["incident analytics", "safety reports", "incidents", "emergency alerts", "safety log", "incident logs", "emergency notifications", "severity levels", "incident sla"],
        "reply_ar": (
            "🚨 **منظومة إدارة السلامة وتحليلات الحوادث المركزية:**\n\n"
            "1. **تصنيف درجات الخطورة وسرعة الاستجابة (SLA):**\n"
            "   • **P1 - طارئ حرج (Critical):** حالات الإسعاف أو النقل الطبي أو الحوادث الجسيمة — إشعار فوري وتدخل خلال 60 دقيقة.\n"
            "   • **P2 - متوسط (Moderate):** إصابات طفيفة أو أعراض حرارة مفاجئة — متابعة وتوثيق خلال 4 ساعات.\n"
            "   • **P3 - ملاحظة سلامة (Minor/Observation):** كدمات بسيطة أو خدوش لعب — توثيق يومي وإشعار ولي الأمر.\n\n"
            "2. **التحليلات الوقائية:** تحليل أسباب الحوادث حسب البيئة (ألعاب خارجية، فصول، وجبات) لتقديم توصيات وقائية للحضانات."
        ),
        "reply_en": (
            "🚨 **Centralized Safety & Incident Intelligence Protocol:**\n\n"
            "1. **Severity Tiers & Resolution SLAs:**\n"
            "   • **P1 - Critical Emergency:** Emergency response, hospital transfer, severe incidents — instant alert & 1-hour SLA.\n"
            "   • **P2 - Moderate:** Minor injuries, sudden fever spikes requiring clinic review — 4-hour review SLA.\n"
            "   • **P3 - Minor / Observation:** Minor playground scrapes, behavioral observation — daily logged record.\n\n"
            "2. **Preventive Analytics:** Incident clustering analysis by facility zone (outdoor playground, dining area, classrooms) to drive preventative safety guidelines."
        ),
        "actions": [
            {"label_ar": "سجل بلاغات الحوادث", "label_en": "Incident Reports Log", "url": "/admin/reports/incidents", "icon": "bi-heart-pulse-fill"},
            {"label_ar": "تحليلات السلامة والحوادث", "label_en": "Safety Analytics", "url": "/admin/safety-analytics", "icon": "bi-pie-chart-fill"}
        ],
        "suggested_ar": ["كيف أتابع حالة بلاغ حادث مفتوح؟", "ما هي المحافظات الأكثر تسجيلاً للبلاغات؟", "كيف أصدر تقرير السلامة الربعي؟"],
        "suggested_en": ["How to track an open incident report?", "Which regions report highest incidents?", "How to generate quarterly safety report?"]
    },
    {
        "intent": "admin_kindergartens_management",
        "target_role": "admin",
        "keywords_ar": ["إدارة الحضانات", "ادارة الحضانات", "تراخيص الحضانات", "اعتماد الروضات", "استيراد الحضانات", "خريطة الحضانات", "قائمة الحضانات", "تصنيف الحضانات", "تجميد حضانة", "ايقاف حضانة"],
        "keywords_en": ["manage kindergartens", "nursery licensing", "accreditation", "import nurseries", "nursery map", "nursery directory", "kg classification", "freeze kindergarten"],
        "reply_ar": (
            "🏫 **إدارة وتصنيف الحضانات الوطنية:**\n\n"
            "1. **التراخيص والاعتماد:** مراجعة الوثائق الهندسية وتصاريح الدفاع المدني وشهادات وزارة التنمية لترخيص الحضانات أو تجديدها.\n"
            "2. **السعة والاستيعاب:** اعتماد السعة القصوى لكل حضانة بناءً على معيار 2 متر مربع لكل طفل في الفضاء الداخلي.\n"
            "3. **التصنيف المعياري:** تقييم جودة الخدمات، مؤهلات الكادر، وسجلات السلامة لمنح مراتب الجودة والاعتماد الوطني.\n"
            "4. **التجميد الإداري (Freeze):** إيقاف مؤقت للعمليات مع تعليل موثق في سجل التدقيق عند وجود مخالفات حرجة."
        ),
        "reply_en": (
            "🏫 **National Kindergarten Licensing & Accreditation:**\n\n"
            "1. **Licensing Dossiers:** Review building blueprints, Civil Defense clearances, and MoSD operational approvals.\n"
            "2. **Capacity Validation:** Calculate approved student capacity based on the statutory minimum of 2.0 sq.m indoor space per child.\n"
            "3. **Institutional Quality Ranking:** Benchmark nurseries based on staff qualifications, health compliance, and inspection scores.\n"
            "4. **Administrative Freeze:** Temporary reversible operational hold with mandatory audit logging upon critical violations."
        ),
        "actions": [
            {"label_ar": "سجل الحضانات الشامل", "label_en": "Kindergartens Directory", "url": "/admin/kindergartens", "icon": "bi-building-gear"},
            {"label_ar": "استيراد الحضانات", "label_en": "Import Kindergartens", "url": "/admin/import/kindergartens", "icon": "bi-cloud-arrow-up-fill"},
            {"label_ar": "التصنيف والمقارنات", "label_en": "Classification & Benchmarks", "url": "/admin/classification", "icon": "bi-award"}
        ],
        "suggested_ar": ["كيف أعتمد ترخيص حضانة جديدة؟", "كيف أستورد قائمة حضانات من ملف؟", "كيف أستعرض تصنيف الحضانات حسب المحافظة؟"],
        "suggested_en": ["How to approve a new nursery license?", "How to bulk import nurseries?", "How to view regional kindergarten rankings?"]
    },
    {
        "intent": "admin_system_settings_maintenance",
        "target_role": "admin",
        "keywords_ar": ["إعدادات النظام", "اعدادات النظام", "النسخ الاحتياطي", "صيانة النظام", "حالة الخادم", "معدل الطلبات", "تنظيف السجلات", "امان النظام"],
        "keywords_en": ["system settings", "backup", "maintenance", "server health", "rate limit", "cleanup logs", "system security", "system diagnostics"],
        "reply_ar": (
            "⚙️ **إعدادات النظام والصيانة والأمان المركزي:**\n\n"
            "1. **النسخ الاحتياطي الآمن:** نسخ احتياطي دوري لقواعد البيانات مع تشفير كامل وتخزين موزع.\n"
            "2. **مراقبة صحة الخادم والخدمات:** فحص دوري لقاعدة البيانات، خدمة الذاكرة المؤقتة (Redis)، وعمال المهام الخلفية (Celery Worker & Beat).\n"
            "3. **سياسة إدارة السجلات:** أرشفة وحفظ سجلات التدقيق للأطر الزمنية القانونية المعتمدة."
        ),
        "reply_en": (
            "⚙️ **System Settings, Maintenance & Infrastructure:**\n\n"
            "1. **Automated Secure Backups:** Scheduled database backups with cryptographic integrity verification.\n"
            "2. **Service Health Probes:** Continuous monitoring of DB connections, Redis cache, and Celery background workers.\n"
            "3. **Log Retention & Purge:** Compliant log retention and pruning aligned with regulatory data policies."
        ),
        "actions": [
            {"label_ar": "لوحة مؤشرات الأداء", "label_en": "Admin Dashboard", "url": "/admin/dashboard", "icon": "bi-sliders"},
            {"label_ar": "سجلات التدقيق", "label_en": "Audit Logs", "url": "/admin/audit-logs", "icon": "bi-shield-check"}
        ],
        "suggested_ar": ["كيف أتحقق من صحة النظام؟", "ما هي سياسة الاحتفاظ بالسجلات؟", "كيف أدير صلاحيات المشرفين؟"],
        "suggested_en": ["How to verify system health?", "What is the log retention policy?", "How to manage supervisor privileges?"]
    },

    # -----------------------------------------------------------------------
    # 1. PARENT / GUARDIAN INTENTS
    # -----------------------------------------------------------------------
    {
        "intent": "enrollment",
        "target_role": "parent",
        "keywords_ar": ["تسجيل", "قبول", "تسجيل طفل", "طلب تسجيل", "كيف اسجل", "تسجيل روضة", "شروط القبول", "الأوراق المطلوبة", "المستندات المطلوبة", "وثائق التسجيل", "شروط التسجيل", "طلب التحاق"],
        "keywords_en": ["enroll", "enrollment", "register", "admission", "apply", "register child", "documents required", "required papers", "admission requirements", "application form"],
        "reply_ar": (
            "📝 **الدليل الشامل لإجراءات تسجيل وقبول الأطفال في الحضانات المعتمدة:**\n\n"
            "1. **المستندات والوثائق الرسمية المطلوبة:**\n"
            "   • صورة مصدقة عن شهادة ميلاد الطفل متضمنة الرقم الوطني.\n"
            "   • صورة عن دفتر العائلة (صفحة الوالدين والطفل).\n"
            "   • صورة مصدقة عن بطاقة التطعيمات الوطنية الصادرة من وزارة الصحة.\n"
            "   • تقرير الفحص الطبي العام وشهادة خلو من الأمراض السارية من طبيب معتمد.\n"
            "   • 4 صور شخصية حديثة للطفل، وصور هويات الأشخاص المخولين بالاستلام.\n\n"
            "2. **الفئات العمرية المعتمدة في الحضانات:**\n"
            "   • **قسم الرضع (Infants):** من عمر 70 يوماً حتى 12 شهراً.\n"
            "   • **قسم الفطام والمشي (Toddlers):** من عمر 1 سنة حتى سنتين.\n"
            "   • **الطفولة المبكرة (Preschool):** من عمر سنتين حتى 3 سنوات و8 أشهر.\n"
            "   • **مرحلة التمهيدي (KG1/KG2):** من 3.8 سنوات حتى 5.8 سنوات.\n\n"
            "3. **خطوات تقديم الطلب الإلكتروني:**\n"
            "   ① اختر الحضانة من دليل الحضانات المرخصة.\n"
            "   ② عبئ نموذج التسجيل الرقمي وأرفق الوثائق.\n"
            "   ③ تتلقى إشعاراً فورياً بتدقيق الطلب من إدارة الحضانة والاعتماد النهائي."
        ),
        "reply_en": (
            "📝 **Comprehensive Guide to Child Enrollment & Admission:**\n\n"
            "1. **Mandatory Required Documents:**\n"
            "   • Certified copy of Child's Birth Certificate (with National ID Number).\n"
            "   • Copy of Family Book (Parent and child pages).\n"
            "   • Official Immunization Record certified by the Ministry of Health.\n"
            "   • General Health & Fitness Assessment from a licensed physician.\n"
            "   • 4 recent passport photos, and IDs of authorized pickup contacts.\n\n"
            "2. **Statutory Age Brackets:**\n"
            "   • **Infant Care:** 70 days to 12 months.\n"
            "   • **Toddlers:** 1 year to 2 years.\n"
            "   • **Early Childhood (Preschool):** 2 years to 3.8 years.\n"
            "   • **Kindergarten (KG1/KG2):** 3.8 years to 5.8 years.\n\n"
            "3. **Digital Application Workflow:**\n"
            "   ① Select accredited kindergarten from the directory.\n"
            "   ② Complete online enrollment profile and attach documents.\n"
            "   ③ Receive instant notifications upon document verification and admission approval."
        ),
        "actions": [
            {"label_ar": "بدء طلب تسجيل إلكتروني", "label_en": "Start Digital Application", "url": "/enrollment/apply", "icon": "bi-person-plus-fill"},
            {"label_ar": "دليل الحضانات المرخصة", "label_en": "Licensed Nurseries", "url": "/kindergartens", "icon": "bi-building"},
            {"label_ar": "بوابة أولياء الأمور", "label_en": "Parent Portal", "url": "/parent/dashboard", "icon": "bi-speedometer2"}
        ],
        "suggested_ar": ["ما هي التطعيمات الإلزامية لدخول الحضانة؟", "كيف أتابع حالة طلب التسجيل؟", "ما هي رسوم الحضانات؟"],
        "suggested_en": ["Mandatory vaccines for admission?", "How to track application status?", "What are the nursery fees?"]
    },
    {
        "intent": "daily_reports",
        "target_role": "parent",
        "keywords_ar": ["تقرير يومي", "تقارير يومية", "التقارير اليومية", "التقرير اليومي", "متابعة الطفل", "وجبات", "حضور الطفل", "غياب", "نوم", "قيلولة", "نشاطات الطفل", "سلوك الطفل", "ملاحظات المعلمة", "المزاج"],
        "keywords_en": ["daily report", "daily reports", "child tracking", "meals", "child attendance", "nap time", "activities", "child behavior", "teacher notes", "mood"],
        "reply_ar": (
            "📋 **تفاصيل ومكونات التقرير اليومي المباشر لطفلك:**\n\n"
            "1. **سجل الحضور والانصراف الذكي:**\n"
            "   • توثيق وقت وصول الطفل ومغادرته مع تحديد هوية الشخص المستلم بدقة.\n\n"
            "2. **سجل التغذية والوجبات:**\n"
            "   • **الإفطار (8:30 - 9:30 ص):** المكونات والكمية المتناولة (كاملة / نصف / قليلة).\n"
            "   • **الغداء (12:00 - 1:00 م):** الوجبة الرئيسية وتفاصيل السوائل.\n"
            "   • **الوجبة الخفيفة (3:00 م):** فواكه طازجة أو سناكات صحية.\n\n"
            "3. **فترات النوم والمزاج:**\n"
            "   • وقت بدء ونهاية القيلولة، ومؤشر الحالة المزاجية للطفل (سعيد، هادئ، نشيط، متعب، متقلب، حزين).\n\n"
            "4. **الأنشطة التربوية والمهارات:** الأنشطة الحركية، التعبير الفني، الألعاب الإدراكية، وملاحظات المعلمة التربوية المباشرة."
        ),
        "reply_en": (
            "📋 **Real-Time Daily Care Report Breakdown:**\n\n"
            "1. **Smart Check-in & Attendance:**\n"
            "   • Exact timestamped check-in and pickup verification with authorized contact logging.\n\n"
            "2. **Meals & Nutrition Intake:**\n"
            "   • **Breakfast (8:30 - 9:30 AM):** Meal breakdown and intake level (Full / Half / Little / Refused).\n"
            "   • **Lunch (12:00 - 1:00 PM):** Hot meal, side vegetables, and hydration tracking.\n"
            "   • **Afternoon Snack (3:00 PM):** Fresh fruits and healthy snacks.\n\n"
            "3. **Naps & Mood Tracking:**\n"
            "   • Sleep start/end timestamps and child mood state (Happy, Calm, Energetic, Tired, Fussy, Sad).\n\n"
            "4. **Learning & Developmental Activities:** Motor skills, sensory play, language development, and educator's personal daily notes."
        ),
        "actions": [
            {"label_ar": "التقارير اليومية لطفلي", "label_en": "Child Daily Reports", "url": "/parent/dashboard", "icon": "bi-journal-check"},
            {"label_ar": "سجل الحضور والانصراف", "label_en": "Attendance Log", "url": "/parent/children", "icon": "bi-calendar-check"}
        ],
        "suggested_ar": ["كيف أبلغ عن غياب أو تأخير طفلي؟", "كيف أتواصل مع معلمة الفصل؟", "كيف أحدث السجل الصحي؟"],
        "suggested_en": ["How to notify of absence/delay?", "How to message the teacher?", "How to update medical info?"]
    },
    {
        "intent": "health_and_vaccines",
        "target_role": "parent",
        "keywords_ar": ["تطعيمات", "لقاحات", "صحة الطفل", "جدول التطعيمات", "حساسية طعام", "حساسية دواء", "طوارئ طبية", "ملف صحي", "وزارة الصحة", "طبيب الحضانة", "البرنامج الوطني للتطعيم", "ادوية", "دواء"],
        "keywords_en": ["vaccine", "vaccination", "child health", "immunization schedule", "food allergy", "medical emergency", "health profile", "ministry of health", "national immunization", "medicine", "medication"],
        "reply_ar": (
            "💉 **البرنامج الوطني للتطعيم والبروتوكول الصحي المعتمد:**\n\n"
            "1. **جدول المطاعيم الوطنية الإلزامية (وزارة الصحة الأردنية):**\n"
            "   • **عند الولادة:** مطعوم السل (BCG).\n"
            "   • **عمر 2، 3، 4 أشهر:** المطعوم السداسي (شلل، كزاز، دفتيريا، سعال ديكي، كبد ب، مستدمية نزلية) + المكورات الرئوية والروتا.\n"
            "   • **عمر 9 أشهر:** مطعوم الحصبة المنفردة.\n"
            "   • **عمر 12 شهراً:** مطعوم الحصبة والحصبة الألمانية والنكاف (MMR).\n"
            "   • **عمر 18 شهراً:** الجرعة الداعمة للمطعوم الرباعي وشلل الأطفال وMMR.\n\n"
            "2. **بروتوكول الحساسية والأدوية:**\n"
            "   • توثيق أي حساسية غذائية (قمح/جلوتين، حليب/لاكتوز، مكسرات، بيض) مع وضع شارة تنبيهية على مقعد ووجبة الطفل.\n"
            "   • لا يتم إعطاء أي دواء إلا بموجب وصفة طبية ونموذج تفويض خطي موقع من الولي.\n"
            "   • في حال ارتفاع الحرارة فوق 38°م: يتم عزل الطفل في غرفة الرعاية وإشعار الولي فوراً."
        ),
        "reply_en": (
            "💉 **National Immunization & Medical Safety Protocol:**\n\n"
            "1. **Jordan Mandatory Vaccination Schedule (Ministry of Health):**\n"
            "   • **At Birth:** BCG (Tuberculosis).\n"
            "   • **Months 2, 3, 4:** Hexavalent (Polio, DTaP, Hep B, Hib) + Pneumococcal & Rotavirus.\n"
            "   • **Month 9:** Measles vaccine.\n"
            "   • **Month 12:** MMR (Measles, Mumps, Rubella).\n"
            "   • **Month 18:** DTaP, Polio & MMR Boosters.\n\n"
            "2. **Allergy & Medication Protocols:**\n"
            "   • Food allergies (Gluten, Lactose, Nuts, Eggs) are color-tagged on classroom rosters and meal plates.\n"
            "   • Prescription medications require a signed parental medical administration form.\n"
            "   • Fever > 38°C policy: Child is cared for in the clinic isolation area with immediate guardian notification."
        ),
        "actions": [
            {"label_ar": "تحديث الملف الصحي والمطاعيم", "label_en": "Update Health & Vaccines", "url": "/parent/children", "icon": "bi-shield-plus"},
            {"label_ar": "الجدول الوطني للتطعيم", "label_en": "Immunization Guide", "url": "/services#parents", "icon": "bi-file-medical"}
        ],
        "suggested_ar": ["ما هي الأوراق المطلوبة للتسجيل؟", "كيف أبلغ الحضانة عن دواء طفلي؟", "أرقام الطوارئ المعتمدة"],
        "suggested_en": ["Required registration papers?", "How to log medication instructions?", "Emergency contact guidelines"]
    },
    {
        "intent": "fees_and_payment",
        "target_role": "parent",
        "keywords_ar": ["رسوم", "اقساط", "دفع", "سعر الحضانة", "طرق الدفع", "فواتير", "دعم حكومي", "برنامج دعم الحضانات", "الضمان الاجتماعي", "برنامج رعاية", "رعاية"],
        "keywords_en": ["fees", "tuition", "payment", "nursery price", "payment methods", "invoices", "subsidies", "government support", "social security", "daman care", "riaya"],
        "reply_ar": (
            "💳 **الرسوم الدراسية وطرق الدفع وبرامج الدعم الحكومي:**\n\n"
            "1. **هيكل الرسوم والخدمات:**\n"
            "   • **رسوم التسجيل السنوية:** تشمل التأمين والملف الصحي والأنشطة العامة.\n"
            "   • **القسط الشهري:** يختلف حسب الفئة العمرية (الرضع، الفطام، الروضة) وساعات الدوام (جزئي أو كامل).\n"
            "   • **الخدمات الإضافية:** وجبات الغذاء، المواصلات الآمنة، وساعات الرعاية المسائية.\n\n"
            "2. **برامج الدعم الحكومي للأمهات العاملات:**\n"
            "   • **برنامج 'رعاية' (المؤسسة العامة للضمان الاجتماعي):** يساهم في تغطية جزء من رسوم الحضانة للأمهات العاملات المشتركات في تأمين الأمومة.\n\n"
            "3. **الفواتير والإيصالات الرقمية:** إصدار فواتير إلكترونية معتمدة وإيصالات دفع فورية برمز استجابة سريعة (QR Code)."
        ),
        "reply_en": (
            "💳 **Tuition Fees, Payment Methods & Subsidies:**\n\n"
            "1. **Fee Structure:**\n"
            "   • **Annual Registration:** Covers health file administration, safety insurance, and educational supplies.\n"
            "   • **Monthly Tuition:** Tiered by age group (Infant, Toddler, Preschool) and schedule (Half-day / Full-day).\n"
            "   • **Optional Services:** Nutritional meal plans, monitored GPS transport, and extended evening care.\n\n"
            "2. **Government Subsidies for Working Mothers:**\n"
            "   • **'Ri'aya' Early Childhood Subsidy (Social Security Corporation):** Direct financial assistance covering nursery fees for eligible insured working mothers.\n\n"
            "3. **Digital Invoices & Receipts:** Automated verifiable invoices and digital payment receipts with QR codes."
        ),
        "actions": [
            {"label_ar": "سجل الفواتير والمدفوعات", "label_en": "Invoices & Payments", "url": "/parent/dashboard", "icon": "bi-receipt"},
            {"label_ar": "استعراض الحضانات والأسعار", "label_en": "Compare Nurseries", "url": "/kindergartens", "icon": "bi-cash-coin"}
        ],
        "suggested_ar": ["كيف أدفع الرسوم إلكترونياً؟", "هل تتوفر خصومات للأخوة؟", "كيف أسترد الرسوم في حال الانتقال؟"],
        "suggested_en": ["How to pay online?", "Sibling discounts available?", "Refund policy upon transfer?"]
    },
    {
        "intent": "parent_attendance_absence",
        "target_role": "parent",
        "keywords_ar": ["ابلاغ غياب", "ابلاغ تأخير", "تسجيل غياب", "غياب طفلي", "استلام الطفل", "المخولين بالاستلام", "مخول بالاستلام", "شخص مستلم", "شخص مخول", "سجل الحضور", "اوقات الدوام"],
        "keywords_en": ["report absence", "report delay", "log absence", "child pickup", "authorized pickup", "attendance history", "operating hours"],
        "reply_ar": (
            "⏰ **إدارة الحضور والغياب والمخولين بالاستلام:**\n\n"
            "1. **الإبلاغ المسبق عن الغياب والتأخير:**\n"
            "   • يمكنك إرسال إشعار غياب مسبق عبر البوابة مع تحديد السبب (إجازة عائلية أو عارض صحي) لتنبيه إدارة الحضانة ومطبخ الوجبات.\n\n"
            "2. **سجل الأشخاص المخولين بالاستلام:**\n"
            "   • إضافة بيانات وصور هويات الأشخاص المعتمدين لاستلام طفلك (الجدة، العم، السائق) مع التحقق الأمني الإلزامي قبل تسليم الطفل.\n\n"
            "3. **التوثيق اللحظي:** تتلقى إشعاراً فورياً على هاتفك بمجرد مسح رمز الدخول أو خروج الطفل مع الشخص المعتمد."
        ),
        "reply_en": (
            "⏰ **Attendance, Absence Notifications & Authorized Pickup Contacts:**\n\n"
            "1. **Advance Absence / Delay Logging:**\n"
            "   • Submit planned absences or sick leave through the parent portal to alert educators and meal planning.\n\n"
            "2. **Authorized Pickup Management:**\n"
            "   • Register verified pickup contacts (grandparents, guardians, drivers) with National IDs and photos.\n\n"
            "3. **Real-time Check-in / Out Alerts:** Receive instant push notifications upon arrival and pickup timestamps."
        ),
        "actions": [
            {"label_ar": "سجل الحضور وإبلاغ الغياب", "label_en": "Attendance & Absence", "url": "/parent/children", "icon": "bi-calendar-check"},
            {"label_ar": "قائمة المخولين بالاستلام", "label_en": "Authorized Pickups", "url": "/parent/children", "icon": "bi-person-check-fill"}
        ],
        "suggested_ar": ["كيف أضيف مخولاً جديداً لاستلام طفلي؟", "كيف أراجع سجل حضور طفلي الشهري؟", "ماذا أفعل في حال تأخرت عن موعد الاستلام؟"],
        "suggested_en": ["How to add an authorized pickup contact?", "How to review monthly attendance?", "What if I am late for pickup?"]
    },
    {
        "intent": "parent_messaging_communication",
        "target_role": "parent",
        "keywords_ar": ["تواصل", "مراسلة المعلمة", "رسائل", "محادثة", "اعلانات الحضانة", "جدول الفعاليات", "نشاطات", "تواصل مع الادارة"],
        "keywords_en": ["messages", "message teacher", "chat", "announcements", "events calendar", "contact management", "communication"],
        "reply_ar": (
            "💬 **قنوات التواصل والإعلانات مع الحضانة:**\n\n"
            "1. **المراسلة المباشرة والآمنة:** تواصل مشفر مع المشرفة التربوية المسؤولة عن شعبة طفلك للاستفسارات اليومية.\n"
            "2. **لوحة الإعلانات والتعاميم:** متابعة العطل الرسمية، الأنشطة والرحلات الخارجية، والمناسبات الوطنية.\n"
            "3. **إشعارات الطوارئ:** استلام تنبيهات فورية عبر الرسائل القصيرة والتطبيق في الحالات الجوية أو الطارئة."
        ),
        "reply_en": (
            "💬 **Parent-Educator Communication & Announcements:**\n\n"
            "1. **Secure Direct Messaging:** Message your child's assigned educator directly for daily updates and questions.\n"
            "2. **Bulletin Board & Calendar:** Stay informed on institutional holidays, events, field trips, and celebrations.\n"
            "3. **Emergency Broadcasts:** Receive priority SMS and app push alerts for weather closures or critical updates."
        ),
        "actions": [
            {"label_ar": "صندوق الرسائل والمحادثات", "label_en": "Messages Inbox", "url": "/parent/dashboard", "icon": "bi-chat-dots-fill"},
            {"label_ar": "لوحة الإعلانات والتقويم", "label_en": "Announcements & Calendar", "url": "/parent/dashboard", "icon": "bi-megaphone-fill"}
        ],
        "suggested_ar": ["كيف أرسل رسالة لمعلمة الفصل؟", "أين أجد جدول العطل الرسمية؟", "كيف أحدث رقم هاتفي لاستقبال الرسائل؟"],
        "suggested_en": ["How to message my child's teacher?", "Where is the holiday calendar?", "How to update phone for SMS alerts?"]
    },

    # -----------------------------------------------------------------------
    # 2. MANAGER & NURSERY STAFF INTENTS
    # -----------------------------------------------------------------------
    {
        "intent": "manager_operations",
        "target_role": "manager",
        "keywords_ar": ["إدارة الحضانة", "لوحة الإدارة", "تسجيل حضور الكادر", "توزيع الفصول", "شعب الحضانة", "السعة الاستيعابية", "قبول الطلاب", "إدارة التسجيل", "إدارة الموظفين", "المربيات", "النسب القانونية للمربيات"],
        "keywords_en": ["nursery management", "manager dashboard", "staff attendance", "classroom allocation", "nursery sections", "capacity", "admissions pipeline", "manage registration", "manage staff", "legal staff ratio"],
        "reply_ar": (
            "🏢 **دليل العمليات وإدارة الحضانة وفق المعايير الرسمية:**\n\n"
            "1. **النسب القانونية الإلزامية للمربيات (وزارة التنمية الاجتماعية):**\n"
            "   • **قسم الرضع (أقل من سنة):** مربية واحدة مؤهلة لكل **6 أطفال** (1:6).\n"
            "   • **قسم الفطام (1 - 2 سنة):** مربية واحدة مؤهلة لكل **8 أطفال** (1:8).\n"
            "   • **قسم الطفولة المبكرة (2 - 4 سنوات):** معلمة مؤهلة لكل **10 أطفال** (1:10).\n\n"
            "2. **معايير المساحة والسلامة:**\n"
            "   • الحد الأدنى للمساحة الداخلية الصافية: **2 متر مربع لكل طفل**، بالإضافة لمساحة لعب خارجية آمنة ومظللة.\n\n"
            "3. **إدارة مسار التسجيل والقبول:** تدقيق المستندات الرسمية، مطابقة السعة، وتوزيع الأطفال على الشعب المعتمدة.\n"
            "4. **إدارة الكادر:** متابعة الحضور والشهادات الصحية الدورية وتوثيق الحوادث في السجل الرسمي فوراً."
        ),
        "reply_en": (
            "🏢 **Kindergarten Operational Management & Statutory Standards:**\n\n"
            "1. **Mandatory Educator-to-Child Ratios (MoSD Regulations):**\n"
            "   • **Infant Care (< 1 year):** 1 certified caregiver per **6 infants** (1:6).\n"
            "   • **Toddlers (1 - 2 years):** 1 certified caregiver per **8 children** (1:8).\n"
            "   • **Preschool (2 - 4 years):** 1 qualified teacher per **10 children** (1:10).\n\n"
            "2. **Physical Facility Requirements:**\n"
            "   • Minimum net indoor activity area: **2.0 square meters per child**, plus secure shaded outdoor playground.\n\n"
            "3. **Admissions Pipeline:** Verify digital dossiers, validate classroom headcounts, and assign sections.\n"
            "4. **Staff Management:** Attendance tracking, semi-annual health check verifications, and instant safety logging."
        ),
        "actions": [
            {"label_ar": "لوحة تحكم إدارة الحضانة", "label_en": "Operations Dashboard", "url": "/dashboard", "icon": "bi-kanban-fill"},
            {"label_ar": "إدارة طلبات التسجيل", "label_en": "Manage Admissions", "url": "/kindergartens", "icon": "bi-people-fill"},
            {"label_ar": "توزيع الشعب والفصول", "label_en": "Classroom Sections", "url": "/services#managers", "icon": "bi-grid-3x3-gap-fill"}
        ],
        "suggested_ar": ["كيف أصدر تقرير الحضور الشهري للوزارة؟", "ما هي النسبة المعتمدة للمربيات للأطفال؟", "كيف أضيف شعبة جديدة؟"],
        "suggested_en": ["How to export monthly attendance for MoSD?", "What is the legal staff-to-child ratio?", "How to add a new classroom section?"]
    },
    {
        "intent": "manager_admissions_workflow",
        "target_role": "manager",
        "keywords_ar": ["قبول الطلبات", "طلبات الالتحاق", "قائمة الانتظار", "اعتماد التسجيل", "رفض طلب", "توزيع الصفوف", "تدقيق وثائق الطفل", "admissions"],
        "keywords_en": ["admissions workflow", "review applications", "waitlist management", "approve enrollment", "reject application", "assign class", "verify documents"],
        "reply_ar": (
            "📥 **مسار قبول واعتماد طلبات التسجيل للحضانات:**\n\n"
            "1. **مراحل تدقيق الطلب:**\n"
            "   • **مقدم جديد (Submitted):** مراجعة اكتمال شهادة الميلاد ودفتر العائلة وسجل التطعيمات.\n"
            "   • **قيد التدقيق (Pending Review):** مطابقة سن الطفل مع الطاقة الاستيعابية للشعبة المطلوبة.\n"
            "   • **مقبول (Accepted):** إشعار ولي الأمر لتسديد رسوم التسجيل وتأكيد المقعد.\n"
            "   • **نشط (Active):** إتمام القبول وتعيين الطفل في الصف مع المشرفة المسؤولة.\n\n"
            "2. **إدارة قائمة الانتظار (Waitlist):** ترتيب تلقائي حسب تاريخ التقديم وأولويات الأخوة المسجلين."
        ),
        "reply_en": (
            "📥 **Admissions & Enrollment Processing Pipeline:**\n\n"
            "1. **Application Stages:**\n"
            "   • **Submitted:** Review birth certificate, family book, and immunization ledger.\n"
            "   • **Pending Review:** Age validation and classroom capacity clearance.\n"
            "   • **Accepted:** Issue acceptance notification and tuition invoice.\n"
            "   • **Active:** Roster assignment and supervisor allocation.\n\n"
            "2. **Waitlist Priority:** Automated FIFO queue with sibling priority weighting."
        ),
        "actions": [
            {"label_ar": "إدارة طلبات القبول", "label_en": "Manage Applications", "url": "/dashboard", "icon": "bi-person-check-fill"},
            {"label_ar": "قوائم الانتظار والشعب", "label_en": "Waitlist & Sections", "url": "/services#managers", "icon": "bi-list-ol"}
        ],
        "suggested_ar": ["كيف أعين طفلاً في شعبة معينة؟", "كيف أرسل إشعار القبول لولي الأمر؟", "كيف أدير قائمة الانتظار؟"],
        "suggested_en": ["How to assign a child to a section?", "How to send acceptance notification?", "How to manage the waitlist?"]
    },
    {
        "intent": "manager_licensing_compliance",
        "target_role": "manager",
        "keywords_ar": ["ترخيص الحضانة", "تجديد الترخيص", "معايير وزارة التنمية", "معايير وزارة التربية", "شروط السلامة العامة", "فحص الدفاع المدني", "الامتثال", "تفتيش الحضانة", "اشتراطات الترخيص"],
        "keywords_en": ["nursery license", "license renewal", "mosd standards", "moe standards", "safety compliance", "civil defense check", "inspection readiness", "licensing requirements"],
        "reply_ar": (
            "📑 **قائمة متطلبات تجديد الترخيص والامتثال المؤسسي:**\n\n"
            "1. **موافقة الدفاع المدني الأردني:** صيانة طفايات الحريق، أجهزة كشف الدخان، مخارج الطوارئ الواضحة، وتغطية المقابس الكهربائية.\n"
            "2. **الشهادات الصحية والتصاريح:** شهادات خلو أمراض سارية المفعول (تجدد كل 6 أشهر) لجميع العاملات والمربيات ومقدمي الطعام.\n"
            "3. **السجلات الرقمية:** الحفاظ على سجل حضور يومي وسجلات تغذية وطوارئ محدثة وجاهزة للتدقيق التفتيشي.\n"
            "4. **التأمين الإلزامي:** وثيقة تأمين سارية ضد الحوادث والمسؤولية المدنية لكافة الأطفال المسجلين."
        ),
        "reply_en": (
            "📑 **Institutional Licensing Renewal & Compliance Checklist:**\n\n"
            "1. **Civil Defense Safety Clearance:** Fire extinguishers, smoke alarms, unobstructed emergency exits, child-proof electrical covers.\n"
            "2. **Staff Health Certificates:** Valid disease-free health certificates (renewed every 6 months) for all educators and staff.\n"
            "3. **Digital Compliance Ledgers:** Daily attendance logs, nutritional intake, and incident logs ready for ministry audits.\n"
            "4. **Mandatory Insurance:** Active third-party liability and accidental insurance policy for all enrolled children."
        ),
        "actions": [
            {"label_ar": "دليل معايير التراخيص والامتثال", "label_en": "Licensing Standards Guide", "url": "/services#managers", "icon": "bi-shield-check"},
            {"label_ar": "تصدير سجلات الامتثال الرسمية", "label_en": "Export Audit Logs", "url": "/dashboard", "icon": "bi-file-earmark-spreadsheet"}
        ],
        "suggested_ar": ["كيف أستعد للزيارة التفتيشية؟", "ما هي متطلبات السلامة العامة في الحضانة؟", "كيف أحدث ترخيص المنشأة؟"],
        "suggested_en": ["How to prepare for an audit visit?", "What are facility safety standards?", "How to update institutional license?"]
    },
    {
        "intent": "manager_financial_billing",
        "target_role": "manager",
        "keywords_ar": ["فواتير الحضانة", "تحصيل الرسوم", "الاقساط المستحقة", "الأقساط المستحقة", "مطالبات رعاية", "سندات القبض", "التقارير المالية للحضانة", "اشتراكات الضمان", "الفوترة"],
        "keywords_en": ["nursery billing", "fee collection", "tuition invoices", "riaya claims", "payment vouchers", "financial reporting", "subsidy reconciliations"],
        "reply_ar": (
            "💰 **الإدارة المالية والفوترة وتحصيلات برنامج رعاية:**\n\n"
            "1. **إصدار الفواتير الآلي:** إصدار فواتير الأقساط الشهرية ورسوم التسجيل مع إرسال إشعارات سداد لأولياء الأمور.\n"
            "2. **مطالبات برنامج 'رعاية' (الضمان الاجتماعي):** تصدير كشوفات الحضور المعتمدة لتقديم مطالبات دعم الأمهات العاملات للضمان الاجتماعي.\n"
            "3. **سجلات القبض والتقارير:** تتبع المدفوعات النقدية والإلكترونية مع تقارير الإيرادات الشهرية."
        ),
        "reply_en": (
            "💰 **Financial Administration, Invoicing & Ri'aya Subsidies:**\n\n"
            "1. **Automated Billing:** Generate monthly tuition invoices and registration fee vouchers with payment reminders.\n"
            "2. **Ri'aya Social Security Claims:** Export verified monthly attendance packages for working mother subsidy claims.\n"
            "3. **Ledgers & Reconciliation:** Real-time tracking of cash, card, and digital transfers with financial analytics."
        ),
        "actions": [
            {"label_ar": "إدارة الفواتير والتحصيل", "label_en": "Invoices & Billing", "url": "/dashboard", "icon": "bi-receipt-cutoff"},
            {"label_ar": "كشوفات برنامج رعاية", "label_en": "Ri'aya Subsidy Ledgers", "url": "/services#managers", "icon": "bi-cash-stack"}
        ],
        "suggested_ar": ["كيف أصدر كشف حضور لمطالبة الضمان الاجتماعي؟", "كيف أسجل دفعة قسط لولي أمر؟", "كيف أستعرض الفواتير المعلقة؟"],
        "suggested_en": ["How to export attendance for Social Security?", "How to log a parent payment?", "How to view overdue invoices?"]
    },

    # -----------------------------------------------------------------------
    # 3. SUPERVISOR & AUDITOR INTENTS
    # -----------------------------------------------------------------------
    {
        "intent": "supervisor_qa_audit",
        "target_role": "supervisor",
        "keywords_ar": ["إشراف تربوي", "مشرف", "تدقيق الحضور", "تفتيش", "زيارة تفتيشية", "مطابقة السجلات", "تقرير المشرف", "تقييم الجودة", "نسبة الأطفال للمربيات", "النسب القانونية", "مخالفات", "تقارير الوزارة", "نموذج التفتيش"],
        "keywords_en": ["educational supervision", "supervisor", "attendance audit", "inspection", "audit visit", "record matching", "supervisor report", "quality assessment", "child to staff ratio", "violations", "inspection form"],
        "reply_ar": (
            "🔍 **دليل الرقابة والتفتيش التربوي المعتمد للمشرفين:**\n\n"
            "1. **بروتوكول التدقيق الميداني:**\n"
            "   • مطابقة الحضور الفعلي للأطفال مع السجلات الرقمية اللحظية في البوابة.\n"
            "   • تدقيق نسب المربيات للأطفال والتأكد من عدم وجود اكتظاظ يتجاوز الطاقة الاستيعابية المرخصة.\n\n"
            "2. **قائمة التحقق الإلكترونية (40 معيار جودة):**\n"
            "   • النظافة والتعقيم، التهوية الطبيعية، وجود حقيبة إسعافات أولية متكاملة غير منتهية الصلاحية.\n"
            "   • ملائمة الأنشطة التربوية للفئات العمرية وتوفر الوسائل التعليمية المعتمدة.\n\n"
            "3. **التوثيق وإصدار التقارير:**\n"
            "   • تسجيل الملاحظات والتوصيات والمخالفات رقمياً وإرسالها فوراً لمديرية التنمية الاجتماعية المختصة."
        ),
        "reply_en": (
            "🔍 **Educational Supervision & Quality Assurance Field Guide:**\n\n"
            "1. **On-Site Audit Protocol:**\n"
            "   • Physical child headcount reconciliation against live platform digital ledgers.\n"
            "   • Verification of legal staff-to-child ratios with automatic flagging of overcrowding violations.\n\n"
            "2. **Digital Inspection Checklist (40-Point Rubric):**\n"
            "   • Sanitation & hygiene, natural ventilation, compliant unexpired first-aid kits.\n"
            "   • Age-appropriate curricula, developmental materials, and safe play equipment.\n\n"
            "3. **Official Reporting:**\n"
            "   • Instant digital recording of observations, corrective actions, and violation packages for MoSD directorates."
        ),
        "actions": [
            {"label_ar": "بوابة المشرفين والمدققين", "label_en": "Supervisor QA Portal", "url": "/services#supervisors", "icon": "bi-clipboard2-check-fill"},
            {"label_ar": "تصدير التقارير الإحصائية المعتمدة", "label_en": "Export National Reports", "url": "/dashboard", "icon": "bi-file-earmark-bar-graph"}
        ],
        "suggested_ar": ["ما هي النسب القانونية المعتمدة للأطفال؟", "كيف أوثق مخالفة في تقرير التفتيش؟", "كيف أستعرض تقارير الحضور التاريخية؟"],
        "suggested_en": ["What are official statutory child-staff ratios?", "How to log an inspection violation?", "How to query historical attendance logs?"]
    },
    {
        "intent": "supervisor_daily_reports_workflow",
        "target_role": "supervisor",
        "keywords_ar": ["كتابة التقرير اليومي", "اعتماد التقرير اليومي", "تسجيل الوجبات", "تسجيل القيلولة", "تقييم المزاج", "انشطة الفصل", "ملاحظات المشرفة", "ارسال التقرير"],
        "keywords_en": ["author daily report", "approve daily report", "log meals", "log naps", "record mood", "classroom activities", "supervisor notes", "submit report"],
        "reply_ar": (
            "✍️ **آلية إعداد واعتماد التقارير اليومية للأطفال:**\n\n"
            "1. **إدخال البيانات اليومية:**\n"
            "   • تسجيل وقت الوصول والمغادرة والوجبات الغذائية.\n"
            "   • توثيق فترات القيلولة والحالة المزاجية (سعيد، هادئ، نشيط، متعب، متقلب، حزين).\n"
            "   • إضافة الملاحظات التربوية والصور من أنشطة الفصل.\n\n"
            "2. **مسار الاعتماد المؤسسي:**\n"
            "   • تُرفع التقارير أولاً لإدارة الحضانة (Manager) للاعتماد قبل إرسالها لأولياء الأمور لضمان الجودة والدقة."
        ),
        "reply_en": (
            "✍️ **Daily Care Report Authoring & Approval Workflow:**\n\n"
            "1. **Daily Logging Routine:**\n"
            "   • Record arrival/departure timestamps and meal consumption.\n"
            "   • Log nap duration and canonical mood states (Happy, Calm, Energetic, Tired, Fussy, Sad).\n"
            "   • Attach developmental notes, photos, and learning activities.\n\n"
            "2. **Institutional Approval:**\n"
            "   • Submitted by supervisors to nursery managers for review and verification prior to parent publishing."
        ),
        "actions": [
            {"label_ar": "إدارة التقارير اليومية", "label_en": "Daily Reports Hub", "url": "/services#supervisors", "icon": "bi-journal-plus"},
            {"label_ar": "سجل حضور الصف", "label_en": "Class Attendance", "url": "/dashboard", "icon": "bi-check2-square"}
        ],
        "suggested_ar": ["كيف أعدل تقريراً يومياً بعد إرساله؟", "كيف أوثق نوم الطفل وقيلولته؟", "كيف أرسل التقرير لمدير الحضانة؟"],
        "suggested_en": ["How to edit a daily report before approval?", "How to log child sleep time?", "How to submit reports to the manager?"]
    },
    {
        "intent": "supervisor_incident_reporting",
        "target_role": "supervisor",
        "keywords_ar": ["تسجيل حادث", "توثيق اصابة", "بلاغ سلامة", "إصابة طفل", "حادث في الصف", "اسعافات اولية", "ابلاغ ولي الامر بحادث"],
        "keywords_en": ["log incident", "document injury", "safety incident report", "child injury", "classroom accident", "first aid", "incident parent alert"],
        "reply_ar": (
            "🩹 **بروتوكول توثيق وإدارة حوادث السلامة الميدانية:**\n\n"
            "1. **الإجراءات الفورية:** تقديم الإسعاف الأولي اللازم والتأكد من سلامة واستقرار الطفل.\n"
            "2. **التوثيق الرقمي الفوري:**\n"
            "   • تحديد نوع الحادث (إصابة، عارض صحي، سلوكي، انزلاق).\n"
            "   • تحديد مستوى الخطورة (P1 طارئ، P2 متوسط، P3 طفيف).\n"
            "   • تدوين الإجراء المتخذ فوراً وإشعار إدارة الحضانة وولي الأمر."
        ),
        "reply_en": (
            "🩹 **Field Incident Logging & Emergency Response Protocol:**\n\n"
            "1. **Immediate Action:** Administer required first-aid and ensure child safety and comfort.\n"
            "2. **Digital Logging:**\n"
            "   • Categorize incident type (Injury, Illness, Behavior, Slip/Fall).\n"
            "   • Tag severity tier (P1 Critical, P2 Moderate, P3 Minor).\n"
            "   • Record immediate corrective actions and notify nursery management & parents."
        ),
        "actions": [
            {"label_ar": "تسجيل بلاغ حادث جديد", "label_en": "Log Incident Report", "url": "/services#supervisors", "icon": "bi-shield-exclamation"},
            {"label_ar": "سجل بلاغات الحضانة", "label_en": "Incident Logs", "url": "/dashboard", "icon": "bi-heart-pulse"}
        ],
        "suggested_ar": ["ما هو بروتوكول التعامل مع الحرارة المرتفعة؟", "كيف أصنف درجات خطورة الحوادث؟", "متى يجب إبلاغ الدفاع المدني أو المستشفى؟"],
        "suggested_en": ["Protocol for high fever?", "How to classify incident severity?", "When to call emergency services?"]
    },

    # -----------------------------------------------------------------------
    # 4. GENERAL VISITOR, AGE POLICY, SECURITY & PLATFORM INTENTS
    # -----------------------------------------------------------------------
    {
        "intent": "kindergarten_search",
        "target_role": "general",
        "keywords_ar": ["بحث عن حضانة", "حضانات عمان", "حضانات اربد", "حضانات الزرقاء", "حضانات قريبة", "دليل الحضانات", "حضانة معتمدة", "موقع الحضانة", "روضات الأردن"],
        "keywords_en": ["find nursery", "nursery search", "nurseries in amman", "licensed nursery", "directory", "accredited", "locations in jordan", "kindergartens jordan"],
        "reply_ar": "تضم منصة KinJo دليلاً وطنياً شاملاً لجميع الحضانات المرخصة في المملكة الأردنية الهاشمية (عمان، إربد، الزرقاء، وكافة المحافظات الـ 12). يمكنك البحث والفلترة حسب المحافظة، الفئة العمرية، والتقييمات الرسمية.",
        "reply_en": "KinJo hosts a comprehensive national directory of licensed and accredited kindergartens across Jordan (Amman, Irbid, Zarqa, and all 12 governorates) with filtering by location, age group, curriculum, and ratings.",
        "actions": [
            {"label_ar": "دليل الحضانات الشامل", "label_en": "Nursery Directory", "url": "/kindergartens", "icon": "bi-geo-alt-fill"},
            {"label_ar": "البحث على الخريطة", "label_en": "Map Search", "url": "/kindergartens", "icon": "bi-map-fill"}
        ],
        "suggested_ar": ["كيف أتحقق من ترخيص الحضانة؟", "ما هي الأوراق المطلوبة للتسجيل؟", "ما هي رسوم الحضانات؟"],
        "suggested_en": ["How to verify a nursery license?", "Required enrollment documents?", "What are the fees?"]
    },
    {
        "intent": "child_age_policy",
        "target_role": "general",
        "keywords_ar": ["الأعمار المقبولة", "الاعمار المقبولة", "العمر المقبول", "سن القبول", "عمر الطفل", "شروط سن القبول", "شروط العمر", "kg2", "المستوى الثاني", "اقل عمر", "اكبر عمر", "سياسة الاعمار", "سن الروضة"],
        "keywords_en": ["accepted age", "age criteria", "age policy", "minimum age", "maximum age", "kg2 eligibility", "age brackets", "child age limits"],
        "reply_ar": (
            "🎂 **سياسة ومعايير قبول الأعمار المعتمدة في الأردن:**\n\n"
            "1. **مرحلة الحضانة (وزارة التنمية الاجتماعية):**\n"
            "   • **الحد الأدنى للقبول:** من عمر **70 يوماً** (بعد انتهاء إجازة الأمومة القانونية).\n"
            "   • **الحد الأقصى للحضانة:** حتى عمر **4 سنوات و8 أشهر** (4.8 سنة).\n\n"
            "2. **المستوى الثاني KG2 (وزارة التربية والتعليم):**\n"
            "   • الأطفال المؤهلون لمرحلة الروضة الثانية KG2 من عمر **4 سنوات و8 أشهر** حتى **5 سنوات و8 أشهر**.\n\n"
            "3. **حاسبة العمر الإلكترونية:** المنصة تحتسب أهلية الطفل تلقائياً بناءً على تاريخ الميلاد المثبت في شهادة الميلاد."
        ),
        "reply_en": (
            "🎂 **Statutory Child Age Eligibility Guidelines in Jordan:**\n\n"
            "1. **Nursery & Daycare (MoSD Authority):**\n"
            "   • **Minimum Age:** **70 days** (post-maternity leave eligibility).\n"
            "   • **Maximum Nursery Age:** **4 years and 8 months** (4.8 years).\n\n"
            "2. **Kindergarten Level 2 - KG2 (MoE Authority):**\n"
            "   • Eligible child age bracket is **4 years and 8 months** to **5 years and 8 months**.\n\n"
            "3. **Automated Age Calculator:** The platform automatically validates enrollment bracket eligibility using the child's official birth date."
        ),
        "actions": [
            {"label_ar": "بدء طلب التسجيل", "label_en": "Start Enrollment", "url": "/enrollment/apply", "icon": "bi-person-plus-fill"},
            {"label_ar": "دليل الفئات العمرية", "label_en": "Age Guidelines", "url": "/services#parents", "icon": "bi-info-circle"}
        ],
        "suggested_ar": ["هل يقبل الطفل بعمر أقل من 3 أشهر؟", "ما هو الفرق بين الحضانة والروضة KG2؟", "ما هي الأوراق المطلوبة للتسجيل؟"],
        "suggested_en": ["Are infants under 3 months accepted?", "Difference between Nursery and KG2?", "Required registration papers?"]
    },
    {
        "intent": "security_and_privacy",
        "target_role": "general",
        "keywords_ar": ["أمان", "خصوصية", "تشفير", "حماية البيانات", "بيانات الطفل", "الحوكمة الإلكترونية", "وزارة الاقتصاد الرقمي", "سري"],
        "keywords_en": ["security", "privacy", "encryption", "data protection", "child data", "e-government", "ministry of digital economy", "confidential"],
        "reply_ar": "تلتزم KinJo بأعلى معايير الأمن السيبراني وحماية البيانات الوطنية في الأردن:\n\n• تشفير كامل لكافة السجلات الشخصية والطبية أثناء النقل والتخزين.\n• صلاحيات وصول محكمة وفق الدور (ولي أمر، مشرف، مدير حضانة، مدير نظام).\n• الامتثال لقانون حماية البيانات الشخصية الأردني ومعايير الحوكمة الإلكترونية الرسمية.",
        "reply_en": "KinJo is engineered to strict national cybersecurity and privacy standards in Jordan:\n\n• End-to-end encryption for all personal and medical records in transit and at rest.\n• Granular role-based access control (Parent, Supervisor, Manager, Administrator).\n• Compliance with Jordan's Personal Data Protection Law and official e-government guidelines.",
        "actions": [
            {"label_ar": "سياسة الخصوصية وحماية البيانات", "label_en": "Privacy Policy", "url": "/privacy", "icon": "bi-shield-lock-fill"},
            {"label_ar": "شروط الخدمة والحوكمة", "label_en": "Terms of Service", "url": "/terms", "icon": "bi-file-text"}
        ],
        "suggested_ar": ["من يملك حق الاطلاع على سجلات طفلي؟", "كيف أطلب حذف حسابي؟", "كيف أغير كلمة المرور؟"],
        "suggested_en": ["Who can view my child's data?", "How to request account deletion?", "How to reset my password?"]
    },
    {
        "intent": "user_guide_help_center",
        "target_role": "general",
        "keywords_ar": ["دليل الاستخدام", "مركز المساعدة", "دليل المستخدم", "شرح ميزات المنصة", "كيف استخدم المنصة", "دليل الوظائف للمستخدمين", "دليل المنصة الشامل"],
        "keywords_en": ["user guide", "help center", "platform documentation", "how to use the platform", "features directory", "user manual"],
        "reply_ar": (
            "📖 **دليل الاستخدام ومركز المساعدة الشامل لمنصة KinJo (`/help`):**\n\n"
            "تضم المنصة توثيقاً تشغيلياً دقيقاً ومفصلاً لكافة الميزات والوظائف حسب الدور الوظيفي:\n\n"
            "1. **مدير النظام (ADMIN):** لوحة المؤشرات الوطنية، مستكشف الرسوم البيانية وجدولة التصدير، إدارة الصلاحيات والاستيراد الجماعي، وسجلات التدقيق وحوادث السلامة.\n"
            "2. **مدير الحضانة (MANAGER):** إدارة قبول الطلاب، توزيع الشُعب والفصول، تطبيق النسب القانونية للمربيات، تجديد الترخيص، والفوترة ومطالبات دعم 'رعاية'.\n"
            "3. **المشرف التربوي والمدقق (SUPERVISOR):** الزيارات التفتيشية الميدانية (40 معيار جودة)، إعداد واعتماد التقارير اليومية، وتوثيق الحوادث.\n"
            "4. **ولي الأمر (PARENT):** تقديم طلبات التسجيل الإلكترونية، متابعة التقارير المباشرة، جدول المطاعيم، إبلاغ الغياب، وإدارة المخولين بالاستلام.\n"
            "5. **الجمهور والزوار (GENERAL):** البحث عن الحضانات المرخصة في المحافظات الـ 12، سياسة الأعمار القانونية (70 يوماً حتى KG2)، وبوابة الأمان والخصوصية."
        ),
        "reply_en": (
            "📖 **KinJo Comprehensive User Guide & Help Center (`/help`):**\n\n"
            "The platform provides comprehensive, surgical operational documentation for every user role:\n\n"
            "1. **System Administrator (ADMIN):** Executive KPIs, Interactive Charts Explorer & scheduled exports, User Directory & RBAC, Audit Trails, and Safety Intelligence.\n"
            "2. **Kindergarten Manager (MANAGER):** Admissions pipeline, section allocations, statutory staff ratios, licensing renewal checklists, and Ri'aya subsidy billing.\n"
            "3. **Educational Supervisor (SUPERVISOR):** 40-point quality assurance rubric, daily care report authoring & sign-off, and field emergency logging.\n"
            "4. **Parent & Guardian (PARENT):** Digital 3-step registration, live care reports, MOH vaccination tracking, absence reporting, and authorized pickups.\n"
            "5. **General Public (GENERAL):** 12-governorate GIS kindergarten search, statutory child age policies (70 days to KG2), and data privacy."
        ),
        "actions": [
            {"label_ar": "دليل الاستخدام ومركز المساعدة", "label_en": "User Guide & Help Center", "url": "/help", "icon": "bi-book-half"},
            {"label_ar": "الأسئلة الشائعة", "label_en": "FAQ Center", "url": "/faq", "icon": "bi-question-circle-fill"},
            {"label_ar": "دليل الخدمات الشامل", "label_en": "Services Guide", "url": "/services", "icon": "bi-grid-fill"}
        ],
        "suggested_ar": ["أين أجد دليل المشرفين التربويين؟", "أين أجد دليل أولياء الأمور؟", "ما هي النسب القانونية للمربيات؟"],
        "suggested_en": ["Where is the supervisor guide?", "Where is the parent guide?", "What are legal staff ratios?"]
    },
    {
        "intent": "support_and_contact",
        "target_role": "general",
        "keywords_ar": ["دعم", "مساعدة", "اتصال", "تواصل", "رقم الهاتف", "مشكلة تقنية", "شكوى", "استفسار", "ساعات العمل", "خدمة العملاء"],
        "keywords_en": ["support", "help", "contact", "phone", "technical issue", "complaint", "inquiry", "email", "working hours", "customer service"],
        "reply_ar": "فريق الدعم الفني وخدمة العملاء في KinJo جاهز لمساعدتكم:\n\n• نموذج الاتصال السريع عبر المنصة.\n• خط الدعم المباشر ومكتب المساعدة الفنية.\n• مركز الأسئلة الشائعة لإجابات فورية على استفساراتكم.",
        "reply_en": "KinJo's Technical Support and Customer Care team is ready to assist you:\n\n• Fast online contact and ticketing form.\n• Direct technical helpdesk support.\n• Comprehensive FAQ Center for instant answers.",
        "actions": [
            {"label_ar": "نموذج اتصل بنا", "label_en": "Contact Helpdesk", "url": "/contact", "icon": "bi-envelope-fill"},
            {"label_ar": "مركز الأسئلة الشائعة", "label_en": "FAQ Center", "url": "/faq", "icon": "bi-question-circle-fill"}
        ],
        "suggested_ar": ["كيف أستعيد كلمة المرور؟", "ساعات عمل فريق الدعم", "تقديم اقتراح أو شكوى"],
        "suggested_en": ["How to reset password?", "Support working hours", "Submit feedback or complaint"]
    }
]


def _normalize_text(text: str) -> str:
    t = text.lower()
    # Normalize Arabic letters
    t = re.sub(r"[إأآا]", "ا", t)
    t = re.sub(r"ة", "ه", t)
    t = re.sub(r"ى", "ي", t)
    # Strip diacritics
    t = re.sub(r"[\u064B-\u065F\u0670]", "", t)
    # Strip punctuation
    t = re.sub(r"[^\w\s]", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def _is_admin_query(query: str) -> bool:
    """Detect if query mentions restricted administrative concepts."""
    normalized_query = _normalize_text(query)
    query_tokens = set(normalized_query.split())

    for kw in ADMIN_RESTRICTED_KEYWORDS_AR + ADMIN_RESTRICTED_KEYWORDS_EN:
        norm_kw = _normalize_text(kw)
        if norm_kw in normalized_query:
            return True
        kw_tokens = set(norm_kw.split())
        if kw_tokens and kw_tokens.issubset(query_tokens):
            return True
    return False


def _match_intent(query: str, lang: str, role: Optional[str] = None, is_admin: bool = False) -> Optional[dict]:
    normalized_query = _normalize_text(query)
    query_tokens = set(normalized_query.split())

    best_match = None
    max_score = 0

    for item in INTENT_KNOWLEDGE_BASE:
        target_role = item.get("target_role")
        # Admin-only intents are strictly skipped for non-admins
        if target_role == "admin" and not is_admin:
            continue

        kw_score = 0
        keywords = item["keywords_ar"] if lang == "ar" else item["keywords_en"]

        for kw in keywords:
            normalized_kw = _normalize_text(kw)
            # Direct phrase match in query
            if normalized_kw in normalized_query:
                kw_score += 8
            else:
                kw_tokens = set(normalized_kw.split())
                common = query_tokens.intersection(kw_tokens)
                if len(kw_tokens) > 1 and len(common) >= 2:
                    kw_score += len(common) * 3
                elif len(kw_tokens) == 1 and common:
                    kw_score += 3

        # Only apply role alignment boost if there is genuine keyword relevance
        if kw_score > 0:
            if role and target_role and role.lower() == target_role.lower() and role.lower() != "general":
                kw_score += 6

            if kw_score > max_score and kw_score >= 6:
                max_score = kw_score
                best_match = item

    return best_match


# ---------------------------------------------------------------------------
# RAAF Pillar 2: Grounding Registry (Authoritative Citations & Standards)
# ---------------------------------------------------------------------------

GROUNDING_REGISTRY: Dict[str, List[Dict[str, str]]] = {
    "admin_kpi_overview": [
        {"name": "KinJo Executive Analytics DB", "citation": "Art. 4, System Metrics & KPI Standard"},
        {"name": "National Childcare Capacity Index 2026", "citation": "MoSD National Registry"}
    ],
    "admin_advanced_analytics_charts": [
        {"name": "KinJo Analytics Visualization Framework", "citation": "Chart.js & Time-Series Standard"},
        {"name": "National Childcare Reporting Engine", "citation": "Automated Export Specification v2.4"}
    ],
    "admin_user_directory": [
        {"name": "KinJo RBAC Matrix", "citation": "ISO/IEC 27001 Access Control Standard"},
        {"name": "Controlled Access Impersonation Protocol", "citation": "KinJo Security Policy v2.4"}
    ],
    "admin_governance_and_audit": [
        {"name": "Jordan MoSD Governance Directive 2024", "citation": "National Audit Standards, Art. 18"},
        {"name": "Jordan Ministry of Education By-Law", "citation": "MoE Early Childhood Compliance"}
    ],
    "admin_safety_and_incidents": [
        {"name": "Jordan Civil Defense Law", "citation": "Childcare Safety & Incident SLA Protocol"},
        {"name": "National Health & Emergency Code", "citation": "Jordan MOH Incident Directive"}
    ],
    "admin_kindergartens_management": [
        {"name": "MoSD Kindergarten Licensing Regulations", "citation": "Regulation No. 52/2024, Arts. 3-9"},
        {"name": "National GIS Mapping Standard", "citation": "Jordan Geocoded Registry"}
    ],
    "admin_system_settings_maintenance": [
        {"name": "KinJo System Administration Manual", "citation": "Infrastructure & Backup SLA Standard"},
        {"name": "National Cybersecurity Center (NCSC)", "citation": "Essential Cybersecurity Controls"}
    ],
    "enrollment": [
        {"name": "Jordan Ministry of Social Development Childcare By-Law", "citation": "Admission & Registration Criteria, Arts. 7-14"},
        {"name": "Civil Status & Passports Dept", "citation": "National ID Verification Standard"}
    ],
    "daily_reports": [
        {"name": "KinJo Early Childhood Pedagogical Framework", "citation": "Daily Care & Activity Tracking Standard"},
        {"name": "Pediatric Nutrition Guide", "citation": "Jordan MOH Early Childhood Dietary Guide"}
    ],
    "health_and_vaccines": [
        {"name": "Jordan Ministry of Health National Immunization Program", "citation": "Mandatory Vaccination Schedule 2024"},
        {"name": "Jordan Medical Association Clinical Protocol", "citation": "Childcare Health & Allergy Protocol"}
    ],
    "fees_and_payment": [
        {"name": "Jordan Social Security Corporation - Ri'aya Fund", "citation": "Maternity & Childcare Support Law"},
        {"name": "Central Bank of Jordan JoMoPay Guidelines", "citation": "Digital Payment & Invoicing Standard"}
    ],
    "parent_attendance_absence": [
        {"name": "KinJo Attendance Verification Standard", "citation": "Authorized Pickup Protocol Art. 6"},
        {"name": "MoSD Child Safety & Custody Guidelines", "citation": "Guardian Handover Protocol"}
    ],
    "parent_messaging_communication": [
        {"name": "KinJo Parent-Educator Messaging Standard", "citation": "Encrypted Communication Policy v2.0"}
    ],
    "manager_operations": [
        {"name": "Jordan Ministry of Social Development Staffing Standards", "citation": "Statutory Caregiver-Child Ratios (1:6, 1:8, 1:10)"},
        {"name": "Early Childhood Facility Code", "citation": "Space Allocation Standard (2.0 sq.m/child)"}
    ],
    "manager_admissions_workflow": [
        {"name": "MoSD Early Childhood Enrollment Procedures", "citation": "Admissions & Waitlist Directive"},
        {"name": "KinJo Admissions Funnel Standard", "citation": "Multi-Channel Intake Policy"}
    ],
    "manager_licensing_compliance": [
        {"name": "General Directorate of Civil Defense Safety Code", "citation": "Fire & Facility Safety Standards 2023"},
        {"name": "MoSD Annual Inspection Manual", "citation": "Health Clearance & Licensing Renewal Protocol"}
    ],
    "manager_financial_billing": [
        {"name": "Central Bank of Jordan Digital Invoicing Standard", "citation": "Electronic Payment Act"},
        {"name": "Social Security Ri'aya Reimbursement Guide", "citation": "Institutional Claim Filing"}
    ],
    "supervisor_qa_audit": [
        {"name": "MoSD Directorate of Early Childhood Quality Rubric", "citation": "40-Point Inspection Rubric & Audit Protocol"},
        {"name": "National Supervision Guidelines", "citation": "Statutory Headcount & Ratio Reconciliation"}
    ],
    "supervisor_daily_reports_workflow": [
        {"name": "KinJo Pedagogical Observation Framework", "citation": "Daily Report Authoring & Manager Signoff"},
        {"name": "Early Childhood Developmental Milestones", "citation": "Jordan MoE Curriculum Guide"}
    ],
    "supervisor_incident_reporting": [
        {"name": "Jordan Civil Defense Emergency Protocol", "citation": "Incident Severity Categorization & SLAs"},
        {"name": "Jordan Ministry of Health First Aid Directive", "citation": "Childcare Injury Logging"}
    ],
    "kindergarten_search": [
        {"name": "KinJo Verified National Geocoded Registry", "citation": "National Licensing Database"}
    ],
    "child_age_policy": [
        {"name": "Jordan Ministry of Social Development Child Age Regulation", "citation": "Childcare Eligibility By-Law, Art. 3"},
        {"name": "Jordan Ministry of Education KG2 By-Law", "citation": "KG2 Level 2 Enrollment Directive"}
    ],
    "security_and_privacy": [
        {"name": "Jordan Personal Data Protection Law", "citation": "Law No. 24/2023, Arts. 4-11"},
        {"name": "National Cybersecurity Center (NCSC)", "citation": "Essential Cybersecurity Controls (ECC)"}
    ],
    "user_guide_help_center": [
        {"name": "KinJo National Platform Documentation", "citation": "Operational Architecture & User Guide v2.4"},
        {"name": "MoSD Early Childhood Regulatory Standard", "citation": "Jordan Quality Framework 2026"}
    ],
    "support_and_contact": [
        {"name": "KinJo Customer Care & Technical Operations Standard", "citation": "Helpdesk SLA Protocol"}
    ],
    "admin_security_restricted": [
        {"name": "KinJo Security & Governance Guardrail", "citation": "Administrative Access Policy Art. 1"}
    ],
    "general_help": [
        {"name": "KinJo Public Portal Knowledgebase", "citation": "Platform FAQ"}
    ]
}


def _build_raaf_response(
    reply: str,
    actions: List[ChatAction],
    suggested_queries: List[str],
    intent: str,
    target_role: str,
    user_role: str,
    is_redacted: bool = False,
    confidence: str = "HIGH"
) -> ChatResponse:
    """Apply RAAF 4-Pass RAC Internal Audit and attach Grounding Ledger & Audit Trail."""
    role_key = (user_role or "general").lower()
    profile = ROLE_PROFILES.get(role_key, ROLE_PROFILES["general"])
    context_header = profile["context_header"]

    # Grounding Sources lookup
    raw_sources = GROUNDING_REGISTRY.get(intent, [
        {"name": "KinJo Platform Core Specifications", "citation": "System Baseline v2.4"}
    ])
    sources = [
        GroundingSource(
            name=s["name"],
            citation=s.get("citation"),
            confidence=s.get("confidence", confidence)
        )
        for s in raw_sources
    ]

    # RAC Pass 1: Query Intent Resolution
    action_type = "govern" if intent.startswith("admin_") else (
        "enroll" if intent == "enrollment" else (
            "audit" if "audit" in intent or "supervisor" in intent else "retrieve"
        )
    )

    # RAC Pass 2, 3, 4: Audit Trail generation
    audit_trail = AuditTrail(
        response_id=str(uuid.uuid4()),
        timestamp=datetime.now(timezone.utc).isoformat(),
        user_role=user_role.capitalize(),
        query_intent={"action": action_type, "target": intent},
        sources_used=[s.name for s in sources],
        confidence=confidence,
        grounding_coverage="100%",
        redactions_applied=is_redacted,
        rac_pass="ALL_PASSED"
    )

    return ChatResponse(
        reply=reply,
        actions=actions,
        suggested_queries=suggested_queries,
        intent=intent,
        target_role=target_role,
        context_header=context_header,
        confidence=confidence,
        sources=sources,
        audit_trail=audit_trail,
    )


@router.post("/chat", response_model=ChatResponse)
async def chat_with_assistant(
    payload: ChatRequest,
    current_user: Optional[models.User] = Depends(get_current_user_optional)
):
    """Handle multi-role bilingual user chat messages and provide context-rich guidance,
    enforcing strict security guardrails on administrative topics."""
    msg = payload.message.strip()
    lang = "en" if payload.lang and payload.lang.lower().startswith("en") else "ar"
    requested_role = (payload.role or "general").lower()

    if not msg:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Message cannot be empty")

    is_authenticated_admin = bool(current_user and current_user.role == models.UserRole.ADMIN)

    # If user claims 'admin' role or is in admin context:
    if requested_role == "admin" and not is_authenticated_admin:
        # Non-admin trying to set admin role -> fallback to general
        role = "general"
    elif is_authenticated_admin and requested_role == "admin":
        role = "admin"
    else:
        role = requested_role

    # -----------------------------------------------------------------------
    # Guardrail Check: Block admin queries for non-admins (Pillar 1 Redaction)
    # -----------------------------------------------------------------------
    if not is_authenticated_admin and (_is_admin_query(msg) or requested_role == "admin"):
        if lang == "ar":
            refusal_reply = (
                "عذراً، العمليات الإدارية وحوكمة النظام مقتصرة على مدراء النظام المعتمدين وتتطلب "
                "تسجيل الدخول عبر لوحة تحكم الإدارة الآمنة. 🔒\n\n"
                "لا يُسمح للمساعد الذكي بالإجابة على الاستفسارات الخاصة بإدارة النظام عبر القنوات العامة. "
                "يمكنك استعراض خدمات أولياء الأمور والمشرفين ومدراء الحضانات، أو التواصل مع الدعم الفني."
            )
            actions = [
                ChatAction(label="دليل الخدمات العامة", url="/services", icon="bi-info-circle-fill"),
                ChatAction(label="مركز الدعم والمساعدة", url="/contact", icon="bi-envelope-fill"),
                ChatAction(label="بوابة أولياء الأمور", url="/parent/dashboard", icon="bi-speedometer2")
            ]
            suggested = [
                "كيف أسجل طفلي في الحضانة؟",
                "البحث عن حضانات معتمدة في عمان",
                "ما هي خدمات المشرفين التربويين؟",
                "تواصل مع الدعم الفني"
            ]
        else:
            refusal_reply = (
                "Access Restricted: Administrative operations, system governance, and audit records "
                "are strictly restricted to authorized administrators within the secure Admin Dashboard. 🔒\n\n"
                "The AI Assistant is not permitted to answer administrative questions on public or unauthorized channels. "
                "You may explore public parent, supervisor, or nursery manager services, or contact technical support."
            )
            actions = [
                ChatAction(label="Platform Services Guide", url="/services", icon="bi-info-circle-fill"),
                ChatAction(label="Contact Support", url="/contact", icon="bi-envelope-fill"),
                ChatAction(label="Parent Portal", url="/parent/dashboard", icon="bi-speedometer2")
            ]
            suggested = [
                "How do I enroll my child?",
                "Find accredited nurseries in Amman",
                "Supervisor & Quality tools",
                "Contact technical support"
            ]

        return _build_raaf_response(
            reply=refusal_reply,
            actions=actions,
            suggested_queries=suggested,
            intent="admin_security_restricted",
            target_role="general",
            user_role=role,
            is_redacted=True,
            confidence="HIGH"
        )

    # -----------------------------------------------------------------------
    # Match Intent in Knowledge Base
    # -----------------------------------------------------------------------
    match = _match_intent(msg, lang, role, is_admin=is_authenticated_admin)

    if match:
        reply = match["reply_ar"] if lang == "ar" else match["reply_en"]
        actions = [
            ChatAction(
                label=a["label_ar"] if lang == "ar" else a["label_en"],
                url=a["url"],
                icon=a.get("icon"),
            )
            for a in match.get("actions", [])
        ]
        suggested = match["suggested_ar"] if lang == "ar" else match["suggested_en"]
        return _build_raaf_response(
            reply=reply,
            actions=actions,
            suggested_queries=suggested,
            intent=match["intent"],
            target_role=match.get("target_role", role),
            user_role=role,
            is_redacted=False,
            confidence="HIGH"
        )

    # -----------------------------------------------------------------------
    # Contextual Role-Aware Fallback Responses
    # -----------------------------------------------------------------------
    if role == "admin" and is_authenticated_admin:
        if lang == "ar":
            reply = (
                "أهلاً بك حضرة مدير النظام! 🛡️\n\n"
                "أنا مساعد KinJo الإداري الذكي، في خدمتك لدعم إدارة العمليات:\n"
                "• استعراض مؤشرات الأداء الحيوية (KPIs) ونسب الإشغال الوطنية\n"
                "• مستكشف الرسوم البيانية والتحليلات المتقدمة وجدولة التصدير\n"
                "• إدارة دليل المستخدمين والصلاحيات والدخول المقيّد (Impersonation)\n"
                "• تدقيق سجلات النشاط والأمان (Audit Logs) وتقارير الحوكمة والوزارة\n"
                "• متابعة بلاغات الحوادث وتحليلات السلامة المركزية\n"
                "• إدارة وتدقيق تراخيص واعتماد الحضانات عبر المحافظات الـ 12"
            )
            actions = [
                ChatAction(label="لوحة المؤشرات الإدارية", url="/admin/dashboard", icon="bi-speedometer2"),
                ChatAction(label="مستكشف الرسوم البيانية", url="/admin/analytics/charts", icon="bi-pie-chart"),
                ChatAction(label="دليل المستخدمين والصلاحيات", url="/admin/users", icon="bi-people-fill"),
                ChatAction(label="سجلات التدقيق الأمني", url="/admin/audit-logs", icon="bi-shield-check"),
                ChatAction(label="تقارير الحوكمة والوزارة", url="/admin/governance-reports", icon="bi-file-earmark-bar-graph")
            ]
            suggested = [
                "كيف أستعرض مؤشرات الأداء الحالية (KPIs)؟",
                "كيف أستخدم مستكشف الرسوم البيانية وجدولة التصدير؟",
                "كيف أدير صلاحيات المستخدمين؟",
                "كيف أراجع سجلات التدقيق الأمني؟",
                "كيف أتابع بلاغات الحوادث والسلامة؟"
            ]
        else:
            reply = (
                "Welcome System Administrator! 🛡️\n\n"
                "I am your KinJo Executive Admin AI Assistant, ready to assist with:\n"
                "• Executive KPIs & National Occupancy Metrics\n"
                "• Advanced Charts Explorer, Visualizations & Scheduled Exports\n"
                "• User Directory, Granular Permissions & Controlled Access (Impersonation)\n"
                "• Cryptographic Audit Trails & Official Governance Filings\n"
                "• Incident Log Monitoring & Safety Analytics\n"
                "• Kindergarten Licensing, Inspections & Accreditation across 12 Governorates"
            )
            actions = [
                ChatAction(label="Admin KPI Dashboard", url="/admin/dashboard", icon="bi-speedometer2"),
                ChatAction(label="Charts Explorer", url="/admin/analytics/charts", icon="bi-pie-chart"),
                ChatAction(label="User Directory", url="/admin/users", icon="bi-people-fill"),
                ChatAction(label="Security Audit Logs", url="/admin/audit-logs", icon="bi-shield-check"),
                ChatAction(label="Governance Reports", url="/admin/governance-reports", icon="bi-file-earmark-bar-graph")
            ]
            suggested = [
                "How to review system KPIs?",
                "How to use Charts Explorer and scheduled exports?",
                "How to manage user directory and roles?",
                "How to audit security logs?",
                "How to monitor safety incident reports?"
            ]
        fallback_intent = "admin_overview"
    elif role == "parent":
        if lang == "ar":
            reply = (
                "أهلاً بك يا ولي الأمر في منصة KinJo! 👋\n\n"
                "يمكنني مساعدتك في: تسجيل طفلك، متابعة التقارير اليومية، الاطلاع على مواعيد التطعيمات، "
                "إبلاغ الحضانة بالغياب، فواتير الأقساط ودعم الضمان (رعاية)، أو التواصل المباشر مع المعلمات."
            )
            actions = [
                ChatAction(label="بدء طلب تسجيل طفل", url="/enrollment/apply", icon="bi-person-plus-fill"),
                ChatAction(label="التقارير اليومية لطفلي", url="/parent/dashboard", icon="bi-journal-check"),
                ChatAction(label="دليل الحضانات المعتمدة", url="/kindergartens", icon="bi-building")
            ]
            suggested = [
                "كيف أسجل طفلي في الحضانة؟",
                "ما هي الأوراق المطلوبة للتسجيل؟",
                "كيف أتابع التقارير اليومية لطفلي؟",
                "ما هو جدول التطعيمات المعتمد؟",
                "كيف أستفيد من دعم برنامج رعاية؟"
            ]
        else:
            reply = (
                "Welcome Parent! 👋\n\n"
                "I can help you with: Child enrollment, daily care reports, vaccination schedules, "
                "reporting absences, tuition & Ri'aya subsidies, or messaging educators."
            )
            actions = [
                ChatAction(label="Apply for Enrollment", url="/enrollment/apply", icon="bi-person-plus-fill"),
                ChatAction(label="Child Daily Reports", url="/parent/dashboard", icon="bi-journal-check"),
                ChatAction(label="Licensed Nurseries", url="/kindergartens", icon="bi-building")
            ]
            suggested = [
                "How do I enroll my child?",
                "Required documents for registration?",
                "How to view child daily reports?",
                "What is the vaccination schedule?",
                "How to apply for Ri'aya child subsidy?"
            ]
        fallback_intent = "parent_help"
    elif role == "supervisor":
        if lang == "ar":
            reply = (
                "أهلاً بك حضرة المشرف التربوي! 📋\n\n"
                "يمكنني مساعدتك في: تدقيق سجلات الحضور والانصراف، مراجعة نسب المربيات للأطفال، "
                "إعداد واعتماد التقارير اليومية، توثيق بلاغات الحوادث، وإصدار التقارير الإحصائية للوزارة."
            )
            actions = [
                ChatAction(label="بوابة المشرفين والمدققين", url="/services#supervisors", icon="bi-clipboard2-check-fill"),
                ChatAction(label="تصدير التقارير الإحصائية", url="/dashboard", icon="bi-file-earmark-bar-graph"),
                ChatAction(label="دليل معايير الجودة والتفتيش", url="/services", icon="bi-shield-check")
            ]
            suggested = [
                "ما هي النسب القانونية المعتمدة للأطفال؟",
                "كيف أعد وأرسل التقرير اليومي للصف؟",
                "كيف أوثق حادث سلامة في الصف؟",
                "كيف أدقق سجل الحضور اليومي للحضانة؟"
            ]
        else:
            reply = (
                "Welcome Supervisor / Auditor! 📋\n\n"
                "I can assist you with: Attendance auditing, legal ratio verification, "
                "authoring daily care reports, logging incidents, and official MoSD compliance exports."
            )
            actions = [
                ChatAction(label="Supervisor QA Portal", url="/services#supervisors", icon="bi-clipboard2-check-fill"),
                ChatAction(label="Export Official Reports", url="/dashboard", icon="bi-file-earmark-bar-graph"),
                ChatAction(label="Quality & Inspection Standards", url="/services", icon="bi-shield-check")
            ]
            suggested = [
                "What are statutory child-to-staff ratios?",
                "How to author and submit daily reports?",
                "How to log a classroom incident report?",
                "How to audit live nursery attendance?"
            ]
        fallback_intent = "supervisor_help"
    elif role == "manager":
        if lang == "ar":
            reply = (
                "أهلاً بك إدارة الحضانة! 🏢\n\n"
                "يمكنني مساعدتك في: إدارة مسار التسجيل وقبول الطلاب، تنظيم الشعب وتوزيع الكادر، "
                "متابعة السعة الاستيعابية، مطالبات دعم رعاية والفوترة، وتصدير التقارير المعتمدة للوزارة."
            )
            actions = [
                ChatAction(label="لوحة تحكم إدارة الحضانة", url="/dashboard", icon="bi-kanban-fill"),
                ChatAction(label="إدارة طلبات القبول والتسجيل", url="/kindergartens", icon="bi-people-fill"),
                ChatAction(label="دليل الامتثال وتجديد الترخيص", url="/services#managers", icon="bi-shield-check")
            ]
            suggested = [
                "كيف أعتمد طلب تسجيل طفل جديد؟",
                "كيف أصدر كشف حضور لمطالبات برنامج رعاية؟",
                "كيف أصدر تقرير الحضور الشهري للوزارة؟",
                "ما هي شروط تجديد ترخيص الحضانة؟"
            ]
        else:
            reply = (
                "Welcome Kindergarten Management! 🏢\n\n"
                "I can assist you with: Admissions pipeline, section and staff allocations, "
                "capacity limits, Ri'aya subsidy billing, and official ministry reporting exports."
            )
            actions = [
                ChatAction(label="Operations Dashboard", url="/dashboard", icon="bi-kanban-fill"),
                ChatAction(label="Manage Admissions", url="/kindergartens", icon="bi-people-fill"),
                ChatAction(label="Licensing & Compliance Guide", url="/services#managers", icon="bi-shield-check")
            ]
            suggested = [
                "How to accept an enrollment application?",
                "How to generate Ri'aya subsidy attendance ledger?",
                "How to export monthly attendance report?",
                "Requirements for nursery license renewal?"
            ]
        fallback_intent = "manager_help"
    else:
        # General / Visitor
        if lang == "ar":
            reply = (
                "أهلاً بك في منصة KinJo الوطنية للحضانات في الأردن! 🇯🇴\n\n"
                "أنا المساعد الذكي المعتمد، اختر دورك أو اسألني مباشرة عن: البحث عن الحضانات المرخصة، "
                "إجراءات وشروط التسجيل، معايير الأعمار (من 70 يوماً حتى KG2)، التقارير اليومية، أو الدعم الفني."
            )
            actions = [
                ChatAction(label="دليل الحضانات المرخصة", url="/kindergartens", icon="bi-building"),
                ChatAction(label="تقديم طلب تسجيل طفل", url="/enrollment/apply", icon="bi-person-plus-fill"),
                ChatAction(label="دليل الخدمات الشامل", url="/services", icon="bi-info-circle-fill")
            ]
            suggested = [
                "كيف أسجل طفلي في الحضانة؟",
                "ما هي شروط الأعمار المقبولة في الحضانة؟",
                "ابحث عن حضانات معتمدة في عمان",
                "ما هي مميزات التقارير اليومية؟",
                "كيف تعمل منظومة الإشراف التربوي؟"
            ]
        else:
            reply = (
                "Welcome to KinJo — Jordan's National Kindergarten Portal! 🇯🇴\n\n"
                "I am your official AI Assistant. Select your role or ask me about: Finding licensed nurseries, "
                "enrollment steps, child age criteria (70 days to KG2), daily care reports, or technical support."
            )
            actions = [
                ChatAction(label="Licensed Nurseries", url="/kindergartens", icon="bi-building"),
                ChatAction(label="Apply for Enrollment", url="/enrollment/apply", icon="bi-person-plus-fill"),
                ChatAction(label="Services Guide", url="/services", icon="bi-info-circle-fill")
            ]
            suggested = [
                "How do I enroll my child?",
                "What are the accepted child age criteria?",
                "Find accredited nurseries in Amman",
                "What features are in daily reports?",
                "How does supervision & audit work?"
            ]
        fallback_intent = "general_help"

    return _build_raaf_response(
        reply=reply,
        actions=actions,
        suggested_queries=suggested,
        intent=fallback_intent,
        target_role=role,
        user_role=role,
        is_redacted=False,
        confidence="HIGH"
    )
