"""api/assistant_routes.py — Bilingual AI Assistant / FAQ Chatbot API for KinJo.

Provides intelligent responses, guided topic recommendations, and direct platform
action links for parents, supervisors, nursery managers, and general visitors.
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional
from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field


router = APIRouter(prefix="/api/assistant", tags=["AI Assistant"])


class ChatAction(BaseModel):
    label: str
    url: str
    icon: Optional[str] = None


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=1000, description="User prompt or query")
    lang: Optional[str] = Field("ar", description="Language preference ('ar' or 'en')")
    session_id: Optional[str] = Field(None, description="Optional conversation session ID")


class ChatResponse(BaseModel):
    reply: str
    actions: List[ChatAction] = Field(default_factory=list)
    suggested_queries: List[str] = Field(default_factory=list)
    intent: Optional[str] = None


# ---------------------------------------------------------------------------
# Bilingual Domain Knowledge & Intent Matcher
# ---------------------------------------------------------------------------

INTENT_KNOWLEDGE_BASE = [
    {
        "intent": "enrollment",
        "keywords_ar": ["تسجيل", "قبول", "تسجيل طفل", "طلب تسجيل", "كيف اسجل", "تسجيل روضة", "شروط القبول", "الأوراق المطلوبة"],
        "keywords_en": ["enroll", "enrollment", "register", "admission", "apply", "register child", "documents required"],
        "reply_ar": "يمكنك تسجيل طفلك في أي من الحضانات المعتمدة عبر منصة كينجو بسهولة: 1. اختر الحضانة المناسبة من دليل الحضانات. 2. اضغط على 'تقديم طلب تسجيل'. 3. املأ بيانات الطفل والولي وأرفق شهادة الميلاد ودفتر التطعيمات. سيصلك إشعار فوري عند مراجعة الطلب.",
        "reply_en": "You can enroll your child in any accredited nursery via KinJo: 1. Select a suitable kindergarten from the directory. 2. Click 'Apply for Enrollment'. 3. Fill in child and guardian details and upload the birth certificate and vaccination record. You will receive an instant notification once reviewed.",
        "actions": [
            {"label_ar": "بدء طلب تسجيل", "label_en": "Start Enrollment", "url": "/enrollment/apply", "icon": "bi-person-plus"},
            {"label_ar": "استعراض الحضانات", "label_en": "Browse Nurseries", "url": "/kindergartens", "icon": "bi-building"},
        ],
        "suggested_ar": ["ما هي الأعمار المقبولة في الحضانات؟", "كيف أتابع حالة طلب التسجيل؟", "ما هي رسوم التسجيل؟"],
        "suggested_en": ["What age groups are accepted?", "How to track application status?", "What are the fees?"],
    },
    {
        "intent": "kindergarten_search",
        "keywords_ar": ["بحث عن حضانة", "حضانات عمان", "حضانات قريبة", "دليل الحضانات", "حضانة معتمدة", "ترخيص", "موقع الحضانة", "روضات"],
        "keywords_en": ["find nursery", "nursery search", "kindergartens in amman", "licensed nursery", "directory", "accredited", "locations"],
        "reply_ar": "تضم منصة كينجو دليلاً شاملاً لجميع الحضانات المرخصة والمعتمدة من وزارة التنمية الاجتماعية في المملكة الأردنية الهاشمية (عمان، إربد، الزرقاء، وكافة المحافظات) مع إمكانية الفرز حسب الموقع، الفئة العمرية، والتقييم.",
        "reply_en": "KinJo hosts a comprehensive national directory of licensed and accredited kindergartens under the Ministry of Social Development in Jordan (Amman, Irbid, Zarqa, and all governorates) with filtering by location, age group, and rating.",
        "actions": [
            {"label_ar": "دليل الحضانات الشامل", "label_en": "Nursery Directory", "url": "/kindergartens", "icon": "bi-geo-alt"},
            {"label_ar": "خريطة الحضانات", "label_en": "Nursery Map", "url": "/kindergartens/map", "icon": "bi-map"},
        ],
        "suggested_ar": ["كيف أتحقق من ترخيص الحضانة؟", "ما هي أفضل الحضانات في عمان؟", "كيف أسجل طفلي؟"],
        "suggested_en": ["How to verify a nursery license?", "Best nurseries in Amman?", "How do I register?"],
    },
    {
        "intent": "daily_reports",
        "keywords_ar": ["تقرير يومي", "تقارير يومية", "التقارير اليومية", "التقرير اليومي", "تقارير", "تقرير", "التقارير", "متابعة الطفل", "وجبات", "حضور", "غياب", "نوم", "نشاطات", "سلوك"],
        "keywords_en": ["daily report", "daily reports", "child tracking", "meals", "attendance", "nap", "activities", "behavior"],
        "reply_ar": "يوفر كينجو نظام تقارير يومية ذكية للأهالي والمشرفين لمتابعة الحضور والانصراف، وجبات الطعام، فترات القيلولة، الحالة المزاجية، والأنشطة التعليمية بتقرير فوري وشامل في نهاية كل يوم عمل.",
        "reply_en": "KinJo provides smart daily reports for parents and supervisors covering check-in/out times, meals, naps, moods, and educational milestones with instant real-time summaries at the end of each day.",
        "actions": [
            {"label_ar": "لوحة تحكم ولي الأمر", "label_en": "Parent Dashboard", "url": "/parent/dashboard", "icon": "bi-journal-check"},
            {"label_ar": "دليل التقارير والمتابعة", "label_en": "Reporting Guide", "url": "/service-guide", "icon": "bi-info-circle"},
        ],
        "suggested_ar": ["متى تصدر التقارير اليومية؟", "كيف أبلغ عن غياب طفلي؟", "كيف أتواصل مع المعلمة؟"],
        "suggested_en": ["When are daily reports published?", "How to submit absence request?", "How to message supervisor?"],
    },
    {
        "intent": "health_and_vaccines",
        "keywords_ar": ["تطعيمات", "لقاحات", "صحة", "جدول التطعيمات", "حساسية", "طوارئ", "طبي", "وزارة الصحة"],
        "keywords_en": ["vaccine", "vaccination", "health", "immunization schedule", "allergy", "medical", "emergency"],
        "reply_ar": "تلتزم منصة كينجو بالبرنامج الوطني للتطعيم في المملكة الأردنية الهاشمية (وزارة الصحة). يمكنك متابعة مواعيد اللقاحات وتوثيق الحساسية الغذائية والسجل الصحي لطفلك لضمان بيئة آمنة تماماً.",
        "reply_en": "KinJo complies with Jordan's National Immunization Schedule (Ministry of Health). You can track vaccine deadlines, log food allergies, and maintain health records for a safe nursery environment.",
        "actions": [
            {"label_ar": "جدول التطعيمات الوطني", "label_en": "Immunization Schedule", "url": "/service-guide#vaccines", "icon": "bi-shield-plus"},
            {"label_ar": "تحديث السجل الصحي", "label_en": "Update Health Profile", "url": "/parent/children", "icon": "bi-heart-pulse"},
        ],
        "suggested_ar": ["ما هي التطعيمات الإلزامية لدخول الحضانة؟", "كيف أسجل حساسية طفلي الغذائية؟", "إجراءات الطوارئ الصحية"],
        "suggested_en": ["Mandatory vaccines for admission?", "How to record allergies?", "Emergency protocols"],
    },
    {
        "intent": "support_and_contact",
        "keywords_ar": ["دعم", "مساعدة", "اتصال", "تواصل", "رقم الهاتف", "مشكلة تقنية", "شكوى", "استفسار"],
        "keywords_en": ["support", "help", "contact", "phone", "technical issue", "complaint", "inquiry", "email"],
        "reply_ar": "فريق الدعم الفني وخدمة العملاء في كينجو جاهز لمساعدتكم على مدار الأسبوع. يمكنك التواصل معنا عبر نموذج الاتصال المباشر أو عبر البريد الإلكتروني والهاتف.",
        "reply_en": "The KinJo technical support and customer care team is ready to assist you. You can reach out directly via our contact form, email, or telephone hotline.",
        "actions": [
            {"label_ar": "تواصل معنا", "label_en": "Contact Us", "url": "/contact", "icon": "bi-envelope"},
            {"label_ar": "الأسئلة الشائعة", "label_en": "FAQ Center", "url": "/faq", "icon": "bi-question-circle"},
        ],
        "suggested_ar": ["كيف أستعيد كلمة المرور؟", "ساعات عمل فريق الدعم", "تقديم اقتراح أو شكوى"],
        "suggested_en": ["How to reset password?", "Support working hours", "Submit feedback or complaint"],
    },
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


def _match_intent(query: str, lang: str) -> Optional[dict]:
    normalized_query = _normalize_text(query)
    query_tokens = set(normalized_query.split())

    best_match = None
    max_score = 0

    for item in INTENT_KNOWLEDGE_BASE:
        score = 0
        keywords = item["keywords_ar"] if lang == "ar" else item["keywords_en"]
        for kw in keywords:
            normalized_kw = _normalize_text(kw)
            # Direct phrase match in query
            if normalized_kw in normalized_query:
                score += 5
            else:
                kw_tokens = set(normalized_kw.split())
                # Exact word intersection
                common = query_tokens.intersection(kw_tokens)
                if common:
                    score += len(common) * 2

        if score > max_score and score >= 4:
            max_score = score
            best_match = item

    return best_match


@router.post("/chat", response_model=ChatResponse)
def chat_with_assistant(payload: ChatRequest):
    """Handle bilingual user chat messages and provide context-rich guidance."""
    msg = payload.message.strip()
    lang = "en" if payload.lang and payload.lang.lower().startswith("en") else "ar"

    if not msg:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Message cannot be empty")

    match = _match_intent(msg, lang)

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
        )

    # General Fallback Response
    if lang == "ar":
        reply = (
            f"أهلاً بك في منصة كينجو لرعاية الأطفال وإدارة الروضات في الأردن! "
            f"أنا مساعدك الذكي، يمكنني مساعدتك في البحث عن الحضانات المرخصة، تسجيل طفلك، "
            f"الاطلاع على التقارير اليومية ومواعيد التطعيمات، أو الإجابة عن أي استفسار."
        )
        actions = [
            ChatAction(label="دليل الحضانات", url="/kindergartens", icon="bi-building"),
            ChatAction(label="طلب تسجيل طفل", url="/enrollment/apply", icon="bi-person-plus"),
            ChatAction(label="الأسئلة الشائعة", url="/faq", icon="bi-question-circle"),
        ]
        suggested = [
            "كيف أسجل طفلي في الحضانة؟",
            "ابحث عن حضانة معتمدة في عمان",
            "ما هي مميزات التقارير اليومية؟",
            "كيف أتواصل مع الدعم الفني؟",
        ]
    else:
        reply = (
            f"Welcome to KinJo — Jordan's National Child Care & Kindergarten Management Platform! "
            f"I am your AI assistant. I can help you discover accredited nurseries, apply for child enrollment, "
            f"track daily activity reports, check vaccination schedules, or answer any questions."
        )
        actions = [
            ChatAction(label="Browse Nurseries", url="/kindergartens", icon="bi-building"),
            ChatAction(label="Apply for Enrollment", url="/enrollment/apply", icon="bi-person-plus"),
            ChatAction(label="FAQ Center", url="/faq", icon="bi-question-circle"),
        ]
        suggested = [
            "How do I enroll my child?",
            "Find licensed nurseries in Amman",
            "What features are included in daily reports?",
            "How can I contact technical support?",
        ]

    return ChatResponse(
        reply=reply,
        actions=actions,
        suggested_queries=suggested,
        intent="general_help",
    )
