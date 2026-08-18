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
        "keywords_ar": ["مؤشرات الاداء", "مؤشرات الأداء", "لوحة التحكم", "احصائيات النظام", "نظرة عامة", "kpi", "لوحة الادارة", "احصائيات المنصة", "معدل الاشغال"],
        "keywords_en": ["kpi", "system metrics", "overview", "admin dashboard", "analytics summary", "executive dashboard", "occupancy rate", "platform stats"],
        "reply_ar": "لوحة المؤشرات والتحليلات الإدارية الشاملة لـ KinJo:\n\n• متابعة إجمالي الحضانات المرخصة، الأطفال المسجلين، والكادر التعليمي المعتمد.\n• مراقبة معدلات الإشغال ونسب الامتثال للمعايير الوطنية.\n• رصد مؤشرات الأداء الحيوية (KPIs) والتنبيهات الفورية عبر المحافظات.",
        "reply_en": "Comprehensive Executive & System KPI Analytics for KinJo:\n\n• Monitor total accredited nurseries, enrolled children, and certified staff.\n• Real-time occupancy tracking and national regulatory compliance scores.\n• High-level KPI breakdown with instant cross-governorate operational alerts.",
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
        "keywords_ar": ["إدارة المستخدمين", "ادارة المستخدمين", "دليل المستخدمين", "صلاحيات", "إضافة مستخدم", "تعديل مستخدم", "انتحال", "دخول بصفة", "استيراد مستخدمين", "mfa"],
        "keywords_en": ["user directory", "manage users", "user access", "add user", "create user", "user roles", "impersonate user", "controlled access", "import users", "mfa"],
        "reply_ar": "إدارة المستخدمين والصلاحيات المتقدمة في المنصة:\n\n1. دليل المستخدمين: استعراض وتعديل وتفعيل حسابات (أولياء الأمور، المشرفين، مدراء الحضانات).\n2. الاستيراد الجماعي: رفع وتعيين المستخدمين دفعة واحدة عبر ملفات منظمة.\n3. الدخول المقيّد بصفة مستخدم (Controlled User Access): لأغراض الدعم الفني والتدقيق مع توثيق مشفر في سجلات النظام.",
        "reply_en": "Advanced User Directory & Access Management:\n\n1. User Registry: View, configure, and activate accounts (Parents, Supervisors, Nursery Managers, Auditors).\n2. Bulk Import: Batch onboard and assign users through standardized templates.\n3. Controlled User Access (Impersonation): Assist users with cryptographically signed audit trails.",
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
        "keywords_ar": ["سجلات التدقيق", "سجل الحركات", "تقارير الحوكمة", "تقارير الوزارة", "التنمية الاجتماعية", "وزارة التربية", "سجل الامتثال", "تصدير التقارير الحكومية", "سجل النشاط"],
        "keywords_en": ["audit logs", "audit trail", "governance reports", "ministry reports", "mosd report", "moe report", "compliance exports", "agency reports", "audit history"],
        "reply_ar": "منظومة الحوكمة وسجلات التدقيق الأمني المعتمدة:\n\n• سجلات تدقيق غير قابلة للتعديل ترصد كافة العمليات الحساسة، الدخول، وتغييرات الصلاحيات.\n• تقارير الحوكمة الرسمية وتنبيهات الامتثال المعتمدة.\n• تصدير التقارير الإحصائية المعتمدة لوزارة التنمية الاجتماعية ووزارة التربية والتعليم.",
        "reply_en": "Certified Governance & Security Audit Trails:\n\n• Immutable audit logs tracking all administrative events, authentication logs, and mutations.\n• Official governance filings, compliance reminders, and regulatory audit reports.\n• Standardized compliance exports for the Ministry of Social Development and Ministry of Education.",
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
        "keywords_ar": ["تحليلات الحوادث", "سجل السلامة", "الحوادث", "إشعارات الطوارئ", "تقارير السلامة", "البلاغات", "بلاغ طارئ"],
        "keywords_en": ["incident analytics", "safety reports", "incidents", "emergency alerts", "safety log", "incident logs", "emergency notifications"],
        "reply_ar": "منظومة تحليلات السلامة وإدارة الحوادث المركزية:\n\n• الرصد اللحظي للبلاغات والحوادث المسجلة من كافة الحضانات عبر المملكة.\n• تصنيف درجات الخطورة ومتابعة الإجراءات التصحيحية المتخذة من الكوادر والمشرفين.\n• تحليلات السلامة المتقدمة لتقليل المخاطر ورفع جودة الرعاية.",
        "reply_en": "Centralized Safety Intelligence & Incident Management:\n\n• Real-time monitoring of all incidents and emergency notices logged by nurseries nationwide.\n• Severity classification and tracking of immediate corrective interventions.\n• Advanced safety analytics for proactive risk mitigation and quality assurance.",
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
        "reply_ar": "إدارة الحضانات والتراخيص والاعتماد الوطني:\n\n• مراجعة واعتماد ملفات الحضانات والتراخيص الرسمية وتحديث السعات الاستيعابية.\n• استيراد بيانات الحضانات ومطابقتها مع السجلات الجغرافية والرسمية.\n• تصنيف الحضانات وتقييم معايير الجودة والمقارنات المعيارية.",
        "reply_en": "National Nursery Licensing & Institutional Governance:\n\n• Review and verify kindergarten licensing dossiers, approvals, and capacity allocations.\n• Batch import and synchronize nursery GIS records and official registration numbers.\n• Nursery classification, quality benchmark comparisons, and inspection history.",
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
        "keywords_ar": ["تسجيل", "قبول", "تسجيل طفل", "طلب تسجيل", "كيف اسجل", "تسجيل روضة", "شروط القبول", "الأوراق المطلوبة", "المستندات المطلوبة", "وثائق التسجيل", "العمر المقبول", "سن القبول"],
        "keywords_en": ["enroll", "enrollment", "register", "admission", "apply", "register child", "documents required", "required papers", "accepted age", "age criteria"],
        "reply_ar": "لتقديم طلب تسجيل طفلك في أي حضانة معتمدة عبر KinJo:\n\n1. استعرض دليل الحضانات واختر الحضانة الأنسب لموقعك.\n2. اضغط 'تقديم طلب تسجيل' وأدخل بيانات الطفل والولي.\n3. أرفق الوثائق الرسمية: شهادة الميلاد، دفتر العائلة، بطاقة المطاعيم، وتقرير الفحص الطبي.\n\nتصلك إشعارات فورية بحالة تدقيق الطلب واعتماده من إدارة الحضانة.",
        "reply_en": "To apply for child enrollment in any accredited nursery via KinJo:\n\n1. Browse the nursery directory and choose the most suitable kindergarten.\n2. Click 'Apply for Enrollment' and enter the child and guardian details.\n3. Upload official documents: Birth certificate, Family book, Immunization record, and General health examination.\n\nYou will receive real-time notifications on application verification and admission.",
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
        "reply_ar": "تتيح لك منصة KinJo الاطلاع لحظياً على سجل يوم طفلك في الحضانة:\n\n• مواعيد تسجيل الحضور والانصراف بدقة.\n• تفاصيل وجبات الإفطار والغداء والكميات المتناولة.\n• فترات القيلولة والراحة وساعات النوم.\n• الأنشطة التعليمية والحركية والمهارات المكتسبة.\n• الملاحظات اليومية المباشرة من المربية أو المعلمة.",
        "reply_en": "KinJo enables you to monitor your child's daily nursery journey in real-time:\n\n• Accurate check-in and check-out timestamps.\n• Meals & nutrition intake breakdown (breakfast, lunch, snacks).\n• Nap times and rest duration.\n• Learning, sensory, and motor activities completed.\n• Direct daily observations and notes from educators.",
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
        "keywords_ar": ["تطعيمات", "لقاحات", "صحة الطفل", "جدول التطعيمات", "حساسية طعام", "حساسية دواء", "طوارئ طبية", "ملف صحي", "وزارة الصحة", "طبيب الحضانة"],
        "keywords_en": ["vaccine", "vaccination", "child health", "immunization schedule", "food allergy", "medical emergency", "health profile", "ministry of health"],
        "reply_ar": "تلتزم منصة KinJo بالبرنامج الوطني للتطعيم المعتمد من وزارة الصحة الأردنية:\n\n• يمكنك رفع وتحديث بطاقة التطعيمات لطفلك إلكترونياً.\n• توثيق أي حساسية غذائية (كالقمح، الحليب، المكسرات) أو حساسية دوائية لإشعار الكادر فوراً.\n• تفعيل بروتوكول الرعاية الطبية وإشعارات الطوارئ المسجلة للحضانة.",
        "reply_en": "KinJo complies with Jordan's National Immunization Program (Ministry of Health):\n\n• Upload and maintain your child's digital immunization card.\n• Record food allergies (e.g. dairy, gluten, nuts) or medication notes to alert staff instantly.\n• Enable emergency health protocols and authorized emergency contacts.",
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
        "keywords_ar": ["رسوم", "اقساط", "دفع", "سعر الحضانة", "طرق الدفع", "فواتير", "دعم حكومي", "برنامج دعم الحضانات"],
        "keywords_en": ["fees", "tuition", "payment", "nursery price", "payment methods", "invoices", "subsidies", "government support"],
        "reply_ar": "تتيح المنصة الشفافية الكاملة في الرسوم والأقساط:\n\n• الاطلاع على جدول الأقساط الشهرية ورسوم التسجيل المعتمدة لكل حضانة.\n• إصدار إيصالات الدفع الإلكترونية وسجل الفواتير المعتمد.\n• الاستعلام عن برامج دعم الأمهات العاملات ورعاية الطفولة المبكرة.",
        "reply_en": "The platform provides full financial transparency:\n\n• View approved monthly tuition and registration fee breakdowns for each nursery.\n• Digital payment receipts and accredited invoice history.\n• Inquire about working mother support programs and early childhood subsidies.",
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
        "keywords_ar": ["إدارة الحضانة", "لوحة الإدارة", "تسجيل حضور الكادر", "توزيع الفصول", "شعب الحضانة", "السعة الاستيعابية", "قبول الطلاب", "إدارة التسجيل", "إدارة الموظفين", "المربيات"],
        "keywords_en": ["nursery management", "manager dashboard", "staff attendance", "classroom allocation", "nursery sections", "capacity", "admissions pipeline", "manage registration", "manage staff"],
        "reply_ar": "توفر لوحة إدارة الحضانة في KinJo تحكماً شاملاً في العمليات اليومية:\n\n1. مسار التسجيل: تدقيق طلبات القبول واعتماد تسجيل الأطفال وإسنادهم للشعب المناسبة.\n2. إدارة الفصول: متابعة السعة الاستيعابية والنسبة القانونية لكل مربية وفق تعليمات الوزارة.\n3. الكادر التعليمي: متابعة حضور الموظفين، سجل المؤهلات والشهادات، وساعات العمل.\n4. الحوادث والسلامة: توثيق أي طارئ أو حادث في سجل السلامة الرسمي فوراً.",
        "reply_en": "The KinJo Kindergarten Operations Dashboard delivers complete control over daily facility workflows:\n\n1. Admissions Pipeline: Review incoming enrollments, accept students, and assign classrooms.\n2. Capacity & Ratios: Monitor real-time classroom capacity and legally mandated teacher-to-child ratios.\n3. Staff Management: Track staff attendance, qualification certifications, and working shifts.\n4. Health & Safety: Instantly document incidents or medical logs in the official safety log.",
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
        "keywords_ar": ["ترخيص الحضانة", "تجديد الترخيص", "معايير وزارة التنمية", "معايير وزارة التربية", "شروط السلامة العامة", "فحص الدفاع المدني", "الامتثال", "تفتيش الحضانة"],
        "keywords_en": ["nursery license", "license renewal", "mosd standards", "moe standards", "safety compliance", "civil defense check", "inspection readiness"],
        "reply_ar": "دليل الامتثال والتراخيص الرسمية للحضانات:\n\n• التحقق من استيفاء معايير المساحة (مترين مربعين لكل طفل على الأقل).\n• توفير شهادات خلو أمراض وتصاريح أمنية لكافة العاملات.\n• استيفاء متطلبات الدفاع المدني ومخارج الطوارئ والإسعافات الأولية.\n• حفظ السجلات اليومية والتقارير المالية والتربوية جاهزة للتدقيق الميداني.",
        "reply_en": "Official Nursery Licensing & Regulatory Compliance Guide:\n\n• Ensure required space allocations (minimum 2 sq.m per child indoors).\n• Maintain valid health certificates and background clearances for all staff.\n• Fulfill Civil Defense safety standards, emergency exits, and certified first aid.\n• Keep standardized digital attendance, health, and audit logs ready for ministry inspectors.",
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
        "keywords_ar": ["إشراف تربوي", "مشرف", "تدقيق الحضور", "تفتيش", "زيارة تفتيشية", "مطابقة السجلات", "تقرير المشرف", "تقييم الجودة", "نسبة الأطفال للمربيات", "مخالفات", "تقارير الوزارة"],
        "keywords_en": ["educational supervision", "supervisor", "attendance audit", "inspection", "audit visit", "record matching", "supervisor report", "quality assessment", "child to staff ratio", "violations"],
        "reply_ar": "أدوات منظومة الإشراف والتدقيق التربوي المعتمدة:\n\n1. التدقيق الفوري: مطابقة الحضور الفعلي المسجل في الحضانة مع السجلات الموثقة بالبوابة.\n2. مراجعة النسب القانونية: التأكد من عدم تجاوز السعة الاستيعابية المرخصة ونسب المربيات للأطفال.\n3. التفتيش الميداني: تعبئة قائمة التحقق الإلكترونية وتوثيق الملاحظات والتوصيات رقمياً.\n4. التصدير الحكومي: إصدار تقارير التفتيش والمؤشرات الإحصائية المعتمدة لوزارة التنمية الاجتماعية.",
        "reply_en": "Official Supervision & Quality Assurance Audit Toolkit:\n\n1. Real-Time Attendance Audit: Verify live recorded classroom attendance against the digital ledger.\n2. Ratio Compliance: Ensure capacity limits and legal staff-to-child ratios are strictly respected.\n3. Digital Inspection Checklist: Fill out standardized mobile audit forms and attach inspection observations.\n4. Ministry Reporting: Generate signed digital audit packages and compliance reports for MoSD/MoE.",
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

