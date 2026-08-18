"""api/assistant_routes.py — Bilingual AI Assistant / FAQ Chatbot API for KinJo.

Provides intelligent responses, multi-role avatars, guided topic recommendations,
and direct platform action links for parents, supervisors, nursery managers, and general visitors,
as well as dedicated administrative intelligence for authenticated system administrators.
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

import models
from dependencies import get_current_user_optional


router = APIRouter(prefix="/api/assistant", tags=["AI Assistant"])


class ChatAction(BaseModel):
    label: str
    url: str
    icon: Optional[str] = None


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
        "keywords_ar": ["مؤشرات الاداء", "مؤشرات الأداء", "لوحة التحكم", "احصائيات النظام", "نظرة عامة", "kpi", "لوحة الادارة", "احصائيات المنصة", "معدل الاشغال", "الارقام العامة"],
        "keywords_en": ["kpi", "system metrics", "overview", "admin dashboard", "analytics summary", "executive dashboard", "occupancy rate", "platform stats", "general figures"],
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
            {"label_ar": "مستكشف التحليلات المتقدم", "label_en": "Analytics Explorer", "url": "/admin/kpi", "icon": "bi-bar-chart-line-fill"},
            {"label_ar": "الخريطة الحرارية للحضانات", "label_en": "Nurseries Heatmap", "url": "/admin/heatmap", "icon": "bi-map-fill"}
        ],
        "suggested_ar": ["كيف أستعرض تقرير مؤشرات الأداء الشهري؟", "كيف أراجع سجلات التدقيق الأمني؟", "كيف أدير صلاحيات المستخدمين؟"],
        "suggested_en": ["How to review monthly KPI report?", "How to audit security logs?", "How to manage user directory?"]
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
        "keywords_ar": ["تحليلات الحوادث", "سجل السلامة", "الحوادث", "إشعارات الطوارئ", "تقارير السلامة", "البلاغات", "بلاغ طارئ", "مستويات الخطورة"],
        "keywords_en": ["incident analytics", "safety reports", "incidents", "emergency alerts", "safety log", "incident logs", "emergency notifications", "severity levels"],
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
        "keywords_ar": ["إدارة الحضانات", "ادارة الحضانات", "تراخيص الحضانات", "اعتماد الروضات", "استيراد الحضانات", "خريطة الحضانات", "قائمة الحضانات", "تصنيف الحضانات"],
        "keywords_en": ["manage kindergartens", "nursery licensing", "accreditation", "import nurseries", "nursery map", "nursery directory", "kg classification"],
        "reply_ar": (
            "🏫 **إدارة وتصنيف الحضانات الوطنية:**\n\n"
            "1. **التراخيص والاعتماد:** مراجعة الوثائق الهندسية وتصاريح الدفاع المدني وشهادات وزارة التنمية لترخيص الحضانات أو تجديدها.\n"
            "2. **السعة والاستيعاب:** اعتماد السعة القصوى لكل حضانة بناءً على معيار 2 متر مربع لكل طفل في الفضاء الداخلي.\n"
            "3. **التصنيف المعياري:** تقييم جودة الخدمات، مؤهلات الكادر، وسجلات السلامة لمنح مراتب الجودة والاعتماد الوطني."
        ),
        "reply_en": (
            "🏫 **National Kindergarten Licensing & Accreditation:**\n\n"
            "1. **Licensing Dossiers:** Review building blueprints, Civil Defense clearances, and MoSD operational approvals.\n"
            "2. **Capacity Validation:** Calculate approved student capacity based on the statutory minimum of 2.0 sq.m indoor space per child.\n"
            "3. **Institutional Quality Ranking:** Benchmark nurseries based on staff qualifications, health compliance, and inspection scores."
        ),
        "actions": [
            {"label_ar": "سجل الحضانات الشامل", "label_en": "Kindergartens Directory", "url": "/admin/kindergartens", "icon": "bi-building-gear"},
            {"label_ar": "استيراد الحضانات", "label_en": "Import Kindergartens", "url": "/admin/import/kindergartens", "icon": "bi-cloud-arrow-up-fill"},
            {"label_ar": "التصنيف والمقارنات", "label_en": "Classification & Benchmarks", "url": "/admin/classification", "icon": "bi-award"}
        ],
        "suggested_ar": ["كيف أعتمد ترخيص حضانة جديدة؟", "كيف أستورد قائمة حضانات من ملف؟", "كيف أستعرض تصنيف الحضانات حسب المحافظة؟"],
        "suggested_en": ["How to approve a new nursery license?", "How to bulk import nurseries?", "How to view regional kindergarten rankings?"]
    },

    # -----------------------------------------------------------------------
    # 1. PARENT / GUARDIAN INTENTS
    # -----------------------------------------------------------------------
    {
        "intent": "enrollment",
        "target_role": "parent",
        "keywords_ar": ["تسجيل", "قبول", "تسجيل طفل", "طلب تسجيل", "كيف اسجل", "تسجيل روضة", "شروط القبول", "الأوراق المطلوبة", "المستندات المطلوبة", "وثائق التسجيل", "العمر المقبول", "سن القبول", "شروط التسجيل"],
        "keywords_en": ["enroll", "enrollment", "register", "admission", "apply", "register child", "documents required", "required papers", "accepted age", "age criteria", "admission requirements"],
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
            "   • **مرحلة رياض الأطفال (KG1/KG2):** من 3.8 سنوات حتى 5.8 سنوات.\n\n"
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
        "keywords_ar": ["تقرير يومي", "تقارير يومية", "التقارير اليومية", "التقرير اليومي", "متابعة الطفل", "وجبات", "حضور الطفل", "غياب", "نوم", "قيلولة", "نشاطات الطفل", "سلوك الطفل", "ملاحظات المعلمة"],
        "keywords_en": ["daily report", "daily reports", "child tracking", "meals", "child attendance", "nap time", "activities", "child behavior", "teacher notes"],
        "reply_ar": (
            "📋 **تفاصيل ومكونات التقرير اليومي المباشر لطفلك:**\n\n"
            "1. **سجل الحضور والانصراف الذكي:**\n"
            "   • توثيق وقت وصول الطفل ومغادرته مع تحديد هوية الشخص المستلم بدقة.\n\n"
            "2. **سجل التغذية والوجبات:**\n"
            "   • **الإفطار (8:30 - 9:30 ص):** المكونات والكمية المتناولة (كاملة / نصف / قليلة).\n"
            "   • **الغداء (12:00 - 1:00 م):** الوجبة الرئيسية وتفاصيل السوائل.\n"
            "   • **الوجبة الخفيفة (3:00 م):** فواكه طازجة أو سناكات صحية.\n\n"
            "3. **فترات النوم والقيلولة:** وقت البدء والاستيقاظ وجودة النوم (هادئ / متقطع).\n\n"
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
            "3. **Naps & Rest Time:** Sleep start/end timestamps and rest quality (Restful / Restless).\n\n"
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
        "keywords_ar": ["تطعيمات", "لقاحات", "صحة الطفل", "جدول التطعيمات", "حساسية طعام", "حساسية دواء", "طوارئ طبية", "ملف صحي", "وزارة الصحة", "طبيب الحضانة", "البرنامج الوطني للتطعيم"],
        "keywords_en": ["vaccine", "vaccination", "child health", "immunization schedule", "food allergy", "medical emergency", "health profile", "ministry of health", "national immunization"],
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
        "keywords_ar": ["رسوم", "اقساط", "دفع", "سعر الحضانة", "طرق الدفع", "فواتير", "دعم حكومي", "برنامج دعم الحضانات", "الضمان الاجتماعي", "برنامج رعاية"],
        "keywords_en": ["fees", "tuition", "payment", "nursery price", "payment methods", "invoices", "subsidies", "government support", "social security", "daman care"],
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

    # -----------------------------------------------------------------------
    # 3. SUPERVISOR & AUDITOR INTENTS
    # -----------------------------------------------------------------------
    {
        "intent": "supervisor_qa_audit",
        "target_role": "supervisor",
        "keywords_ar": ["إشراف تربوي", "مشرف", "تدقيق الحضور", "تفتيش", "زيارة تفتيشية", "مطابقة السجلات", "تقرير المشرف", "تقييم الجودة", "نسبة الأطفال للمربيات", "مخالفات", "تقارير الوزارة", "نموذج التفتيش"],
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

    # -----------------------------------------------------------------------
    # 4. GENERAL VISITOR, SECURITY & PLATFORM INTENTS
    # -----------------------------------------------------------------------
    {
        "intent": "kindergarten_search",
        "target_role": "general",
        "keywords_ar": ["بحث عن حضانة", "حضانات عمان", "حضانات اربد", "حضانات الزرقاء", "حضانات قريبة", "دليل الحضانات", "حضانة معتمدة", "موقع الحضانة", "روضات الأردن"],
        "keywords_en": ["find nursery", "nursery search", "nurseries in amman", "licensed nursery", "directory", "accredited", "locations in jordan", "kindergartens jordan"],
        "reply_ar": "تضم منصة KinJo دليلاً وطنياً شاملاً لجميع الحضانات المرخصة في المملكة الأردنية الهاشمية (عمان، إربد، الزرقاء، وكافة المحافظات). يمكنك البحث والفلترة حسب المحافظة، الفئة العمرية، والتقييمات الرسمية.",
        "reply_en": "KinJo hosts a comprehensive national directory of licensed and accredited kindergartens across Jordan (Amman, Irbid, Zarqa, and all governorates) with filtering by location, age group, curriculum, and ratings.",
        "actions": [
            {"label_ar": "دليل الحضانات الشامل", "label_en": "Nursery Directory", "url": "/kindergartens", "icon": "bi-geo-alt-fill"},
            {"label_ar": "البحث على الخريطة", "label_en": "Map Search", "url": "/kindergartens", "icon": "bi-map-fill"}
        ],
        "suggested_ar": ["كيف أتحقق من ترخيص الحضانة؟", "ما هي الأوراق المطلوبة للتسجيل؟", "ما هي رسوم الحضانات؟"],
        "suggested_en": ["How to verify a nursery license?", "Required enrollment documents?", "What are the fees?"]
    },
    {
        "intent": "security_and_privacy",
        "target_role": "general",
        "keywords_ar": ["أمان", "خصوصية", "تشفير", "حماية البيانات", "بيانات الطفل", "الحوكمة الإلكترونية", "وزارة الاقتصاد الرقمي", "سري"],
        "keywords_en": ["security", "privacy", "encryption", "data protection", "child data", "e-government", "ministry of digital economy", "confidential"],
        "reply_ar": "تلتزم KinJo بأعلى معايير الأمن السيبراني وحماية البيانات الوطنية في الأردن:\n\n• تشفير كامل لكافة السجلات الشخصية والطبية أثناء النقل والتخزين.\n• صلاحيات وصول محكمة وفق الدور (ولي أمر، مشرف، مدير حضانة).\n• الامتثال لقانون حماية البيانات الشخصية الأردني ومعايير الحوكمة الإلكترونية الرسمية.",
        "reply_en": "KinJo is engineered to strict national cybersecurity and privacy standards in Jordan:\n\n• End-to-end encryption for all personal and medical records in transit and at rest.\n• Granular role-based access control (Parent, Supervisor, Manager, Auditor).\n• Compliance with Jordan's Personal Data Protection Law and official e-government guidelines.",
        "actions": [
            {"label_ar": "سياسة الخصوصية وحماية البيانات", "label_en": "Privacy Policy", "url": "/privacy", "icon": "bi-shield-lock-fill"},
            {"label_ar": "شروط الخدمة والحوكمة", "label_en": "Terms of Service", "url": "/terms", "icon": "bi-file-text"}
        ],
        "suggested_ar": ["من يملك حق الاطلاع على سجلات طفلي؟", "كيف أطلب حذف حسابي؟", "كيف أغير كلمة المرور؟"],
        "suggested_en": ["Who can view my child's data?", "How to request account deletion?", "How to reset my password?"]
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

        score = 0
        keywords = item["keywords_ar"] if lang == "ar" else item["keywords_en"]
        
        # Boost if query aligns with user role
        if role and role.lower() == target_role:
            score += 2

        for kw in keywords:
            normalized_kw = _normalize_text(kw)
            # Direct phrase match in query
            if normalized_kw in normalized_query:
                score += 6
            else:
                kw_tokens = set(normalized_kw.split())
                common = query_tokens.intersection(kw_tokens)
                if common:
                    score += len(common) * 2

        if score > max_score and score >= 4:
            max_score = score
            best_match = item

    return best_match


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
    # Guardrail Check: Block admin queries for non-admins
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

        return ChatResponse(
            reply=refusal_reply,
            actions=actions,
            suggested_queries=suggested,
            intent="admin_security_restricted",
            target_role="general",
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
        return ChatResponse(
            reply=reply,
            actions=actions,
            suggested_queries=suggested,
            intent=match["intent"],
            target_role=match.get("target_role", role),
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
                "• إدارة دليل المستخدمين والصلاحيات والدخول المقيّد (Impersonation)\n"
                "• تدقيق سجلات النشاط والأمان (Audit Logs) وتقارير الحوكمة\n"
                "• متابعة بلاغات الحوادث وتحليلات السلامة المركزية\n"
                "• إدارة وتدقيق تراخيص واعتماد الحضانات"
            )
            actions = [
                ChatAction(label="لوحة المؤشرات الإدارية", url="/admin/dashboard", icon="bi-speedometer2"),
                ChatAction(label="دليل المستخدمين والصلاحيات", url="/admin/users", icon="bi-people-fill"),
                ChatAction(label="سجلات التدقيق الأمني", url="/admin/audit-logs", icon="bi-shield-check"),
                ChatAction(label="تقارير الحوكمة والوزارة", url="/admin/governance-reports", icon="bi-file-earmark-bar-graph")
            ]
            suggested = [
                "كيف أستعرض مؤشرات الأداء الحالية (KPIs)؟",
                "كيف أدير صلاحيات المستخدمين؟",
                "كيف أراجع سجلات التدقيق الأمني؟",
                "كيف أتابع بلاغات الحوادث والسلامة؟"
            ]
        else:
            reply = (
                "Welcome System Administrator! 🛡️\n\n"
                "I am your KinJo Executive Admin AI Assistant, ready to assist with:\n"
                "• Executive KPIs & National Occupancy Metrics\n"
                "• User Directory, Granular Permissions & Controlled Access (Impersonation)\n"
                "• Cryptographic Audit Trails & Official Governance Filings\n"
                "• Incident Log Monitoring & Safety Analytics\n"
                "• Kindergarten Licensing, Inspections & Accreditation"
            )
            actions = [
                ChatAction(label="Admin KPI Dashboard", url="/admin/dashboard", icon="bi-speedometer2"),
                ChatAction(label="User Directory", url="/admin/users", icon="bi-people-fill"),
                ChatAction(label="Security Audit Logs", url="/admin/audit-logs", icon="bi-shield-check"),
                ChatAction(label="Governance Reports", url="/admin/governance-reports", icon="bi-file-earmark-bar-graph")
            ]
            suggested = [
                "How to review system KPIs?",
                "How to manage user directory and roles?",
                "How to audit security logs?",
                "How to monitor safety incident reports?"
            ]
    elif role == "parent":
        if lang == "ar":
            reply = (
                "أهلاً بك يا ولي الأمر في منصة KinJo! 👋\n\n"
                "يمكنني مساعدتك في: تسجيل طفلك، متابعة التقارير اليومية، الاطلاع على مواعيد التطعيمات، "
                "أو التواصل المباشر مع الحضانة. ما الذي تود الاستفسار عنه؟"
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
                "ما هو جدول التطعيمات المعتمد؟"
            ]
        else:
            reply = (
                "Welcome Parent! 👋\n\n"
                "I can help you with: Child enrollment, daily care reports, vaccination schedules, "
                "or messaging educators. What would you like to know?"
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
                "What is the vaccination schedule?"
            ]
    elif role == "supervisor":
        if lang == "ar":
            reply = (
                "أهلاً بك حضرة المشرف التربوي! 📋\n\n"
                "يمكنني مساعدتك في: تدقيق سجلات الحضور والانصراف، مراجعة نسب المربيات للأطفال، "
                "استكمال قوائم التفتيش الميداني، وإصدار التقارير الإحصائية لوزارة التنمية الاجتماعية."
            )
            actions = [
                ChatAction(label="بوابة المشرفين والمدققين", url="/services#supervisors", icon="bi-clipboard2-check-fill"),
                ChatAction(label="تصدير التقارير الإحصائية", url="/dashboard", icon="bi-file-earmark-bar-graph"),
                ChatAction(label="دليل معايير الجودة والتفتيش", url="/services", icon="bi-shield-check")
            ]
            suggested = [
                "ما هي النسب القانونية المعتمدة للأطفال؟",
                "كيف أدقق سجل الحضور اليومي للحضانة؟",
                "كيف أوثق زيارة تفتيشية رسمية؟"
            ]
        else:
            reply = (
                "Welcome Supervisor / Auditor! 📋\n\n"
                "I can assist you with: Attendance auditing, legal ratio verification, "
                "digital inspection checklists, and official MoSD compliance exports."
            )
            actions = [
                ChatAction(label="Supervisor QA Portal", url="/services#supervisors", icon="bi-clipboard2-check-fill"),
                ChatAction(label="Export Official Reports", url="/dashboard", icon="bi-file-earmark-bar-graph"),
                ChatAction(label="Quality & Inspection Standards", url="/services", icon="bi-shield-check")
            ]
            suggested = [
                "What are statutory child-to-staff ratios?",
                "How to audit live nursery attendance?",
                "How to record an official inspection visit?"
            ]
    elif role == "manager":
        if lang == "ar":
            reply = (
                "أهلاً بك إدارة الحضانة! 🏢\n\n"
                "يمكنني مساعدتك في: إدارة مسار التسجيل وقبول الطلاب، تنظيم الشعب وتوزيع الكادر، "
                "متابعة السعة الاستيعابية، وتصدير التقارير المعتمدة للوزارة."
            )
            actions = [
                ChatAction(label="لوحة تحكم إدارة الحضانة", url="/dashboard", icon="bi-kanban-fill"),
                ChatAction(label="إدارة طلبات القبول والتسجيل", url="/kindergartens", icon="bi-people-fill"),
                ChatAction(label="دليل الامتثال وتجديد الترخيص", url="/services#managers", icon="bi-shield-check")
            ]
            suggested = [
                "كيف أعتمد طلب تسجيل طفل جديد؟",
                "كيف أصدر تقرير الحضور الشهري للوزارة؟",
                "ما هي شروط تجديد ترخيص الحضانة؟"
            ]
        else:
            reply = (
                "Welcome Kindergarten Management! 🏢\n\n"
                "I can assist you with: Admissions pipeline, section and staff allocations, "
                "capacity limits, and official ministry reporting exports."
            )
            actions = [
                ChatAction(label="Operations Dashboard", url="/dashboard", icon="bi-kanban-fill"),
                ChatAction(label="Manage Admissions", url="/kindergartens", icon="bi-people-fill"),
                ChatAction(label="Licensing & Compliance Guide", url="/services#managers", icon="bi-shield-check")
            ]
            suggested = [
                "How to accept an enrollment application?",
                "How to export monthly attendance report?",
                "Requirements for nursery license renewal?"
            ]
    else:
        # General / Visitor
        if lang == "ar":
            reply = (
                "أهلاً بك في منصة KinJo الوطنية للحضانات في الأردن! 🇯🇴\n\n"
                "أنا المساعد الذكي المعتمد، اختر دورك أو اسألني مباشرة عن: البحث عن الحضانات المرخصة، "
                "إجراءات التسجيل، التقارير اليومية، معايير الرقابة والتفتيش، أو الدعم الفني."
            )
            actions = [
                ChatAction(label="دليل الحضانات المرخصة", url="/kindergartens", icon="bi-building"),
                ChatAction(label="تقديم طلب تسجيل طفل", url="/enrollment/apply", icon="bi-person-plus-fill"),
                ChatAction(label="دليل الخدمات الشامل", url="/services", icon="bi-info-circle-fill")
            ]
            suggested = [
                "كيف أسجل طفلي في الحضانة؟",
                "ابحث عن حضانات معتمدة في عمان",
                "ما هي مميزات التقارير اليومية؟",
                "كيف تعمل منظومة الإشراف التربوي؟"
            ]
        else:
            reply = (
                "Welcome to KinJo — Jordan's National Kindergarten Portal! 🇯🇴\n\n"
                "I am your official AI Assistant. Select your role or ask me about: Finding licensed nurseries, "
                "enrollment steps, daily care reports, supervision & QA tools, or technical support."
            )
            actions = [
                ChatAction(label="Licensed Nurseries", url="/kindergartens", icon="bi-building"),
                ChatAction(label="Apply for Enrollment", url="/enrollment/apply", icon="bi-person-plus-fill"),
                ChatAction(label="Services Guide", url="/services", icon="bi-info-circle-fill")
            ]
            suggested = [
                "How do I enroll my child?",
                "Find accredited nurseries in Amman",
                "What features are in daily reports?",
                "How does supervision & audit work?"
            ]

    return ChatResponse(
        reply=reply,
        actions=actions,
        suggested_queries=suggested,
        intent="general_help" if role != "admin" else "admin_overview",
        target_role=role,
    )

