/**
 * Unified dashboard client logic for ADMIN, MANAGER, SUPERVISOR, and PARENT.
 * It hydrates widgets defensively: if an element does not exist for a role,
 * the updater simply no-ops.
 */

const DASHBOARD_API = {
  supervisor: {
    dashboard: "/api/supervisor/dashboard",
  },
  manager: {
    classes: "/api/manager/classes",
    reports: "/api/manager/daily-reports",
    supervisors: "/api/users?role=SUPERVISOR&limit=100",
    parents: "/api/users?role=PARENT&limit=200",
    kpis: "/api/kpi/dashboard-data",
  },
  admin: {
    dashboard: "/api/admin/dashboard",
    kindergartens: "/api/kindergartens",
    kpis: "/api/kpi/dashboard-data",
  },
};

function dashboardCurrentLang() {
  if (window.AppI18n && window.AppI18n.currentLang) {
    return window.AppI18n.currentLang;
  }
  return document.documentElement.lang === "en" ? "en" : "ar";
}

function dashboardCurrentLocale() {
  return dashboardCurrentLang() === "en" ? "en-US" : "ar-JO";
}

function dashboardText(key, arText, enText) {
  if (window.AppI18n && typeof window.AppI18n.t === "function") {
    const translated = window.AppI18n.t(key);
    if (translated && translated !== key) {
      return translated;
    }
  }
  return dashboardCurrentLang() === "en" ? enText : arText;
}

const DASHBOARD_LITERAL_EN = {
  "لا توجد بيانات متاحة": "No data available",
  "مراسلة المشرف": "Message supervisor",
  "مراسلة ولي الأمر": "Message parent",
  "لا توجد فصول": "No classes",
  "لا توجد بيانات فصول لعرضها": "No class data to display",
  "نسبة إشغال الفصل": "Class occupancy rate",
  "نشط": "Active",
  "غير نشط": "Inactive",
  "عرض الفصل": "View class",
  "تعذر تحميل الفصول": "Unable to load classes",
  "تعذر تحميل ملخص الفصول": "Unable to load class summary",
  "لا توجد تقارير معلقة": "No pending reports",
  "تاريخ غير محدد": "Date not specified",
  "اليوم": "Today",
  "أمس": "Yesterday",
  "بانتظار المراجعة": "Pending review",
  "عرض التقرير": "View report",
  "تعذر تحميل التقارير": "Unable to load reports",
  "إجمالي المشرفين": "Total supervisors",
  "النطاق الإداري الحالي": "Current management scope",
  "المشرفون النشطون": "Active supervisors",
  "من إجمالي المشرفين": "of total supervisors",
  "معدل نشاط المشرفين": "Supervisor activity rate",
  "المشرفون غير النشطين": "Inactive supervisors",
  "معدل عدم النشاط": "Inactivity rate",
  "غير متاح حالياً": "Currently unavailable",
  "نسبة الحضور": "attendance rate",
  "لا توجد طلبات": "No requests",
  "إجراء فوري": "Immediate action",
  "تحتاج متابعة": "Needs follow-up",
  "مستقر": "Stable",
  "حرج": "Critical",
  "تحت المراقبة": "Under monitoring",
  "ممتاز": "Excellent",
  "جيد": "Good",
  "متوسط": "Average",
  "مهدد": "At risk",
  "لا توجد روضات": "No kindergartens",
  "ساري": "Valid",
  "قارب على الانتهاء": "Expiring soon",
  "منتهي": "Expired",
  "عرض الروضة": "View kindergarten",
  "لا توجد بيانات": "No data",
  "تنبيه": "Alert",
  "انتهاء الترخيص": "License expiry",
  "طلبات تسجيل معلقة": "Pending enrollments",
  "انخفاض الحضور": "Low attendance",
  "ارتفاع الحوادث": "High incidents",
  "طلبات التسجيل": "Enrollment requests",
  "السلامة": "Safety",
  "الترخيص": "License",
  "الامتثال": "Compliance",
  "لا توجد تفاصيل متاحة.": "No details available.",
  "لا توجد تنبيهات نشطة": "No active alerts",
  "فتح": "Open",
  "إجمالي الحالات": "Total cases",
  "الحضور": "Attendance",
  "لا توجد بيانات حضور ضمن الفترة المختارة":
    "No attendance data for selected range",
  "لا توجد حالات تسجيل متاحة": "No enrollment states available",
  "لا توجد بيانات مؤشرات حالياً": "No KPI data available currently",
  "الاتجاه": "Trend",
  "عرض الإجراءات": "View actions",
  "إجراءات": "Actions",
  "لا توجد شروحات متاحة للمؤشرات.": "No KPI explanations available.",
  "لا يوجد شرح متاح.": "No explanation available.",
  "خطة الإجراء": "Action plan",
  "لا توجد إجراءات مقترحة لهذا المؤشر.":
    "No suggested actions for this KPI.",
  "عالية": "High",
  "متوسطة": "Medium",
  "منخفضة": "Low",
  "إجراء": "Action",
  "تعذر تحميل بيانات الروضات": "Unable to load kindergarten data",
};

function dashboardLiteral(text) {
  if (dashboardCurrentLang() !== "en") {
    return text;
  }
  return DASHBOARD_LITERAL_EN[text] || text;
}

function dashboardTemplate(html) {
  if (dashboardCurrentLang() !== "en" || !html) {
    return html;
  }
  return Object.entries(DASHBOARD_LITERAL_EN).reduce(
    (acc, [ar, en]) => acc.split(ar).join(en),
    String(html)
  );
}

const KPI_DEFINITIONS = [
  {
    key: "overall_gcei",
    label: () =>
      dashboardText(
        "dashboard.kpi.overall_gcei",
        "مؤشر جودة الحوكمة الكلي",
        "Overall governance quality index"
      ),
    unit: "%",
  },
  {
    key: "attendance_rate",
    label: () =>
      dashboardText("dashboard.kpi.attendance_rate", "نسبة الحضور", "Attendance rate"),
    unit: "%",
  },
  {
    key: "ratio_compliance",
    label: () =>
      dashboardText(
        "dashboard.kpi.ratio_compliance",
        "امتثال نسبة الإشراف",
        "Supervisor ratio compliance"
      ),
    unit: "%",
  },
  {
    key: "training_completion_rate",
    label: () =>
      dashboardText(
        "dashboard.kpi.training_completion",
        "نسبة إكمال التدريب",
        "Training completion"
      ),
    unit: "%",
  },
  {
    key: "report_submission_rate",
    label: () =>
      dashboardText(
        "dashboard.kpi.report_submission",
        "الالتزام بتسليم التقارير",
        "Report submission"
      ),
    unit: "%",
  },
  {
    key: "incident_rate",
    label: () =>
      dashboardText("dashboard.kpi.incident_rate", "معدل الحوادث", "Incident rate"),
    unit: "/1,000",
  },
  {
    key: "serious_incident_rate",
    label: () =>
      dashboardText(
        "dashboard.kpi.serious_incident_rate",
        "معدل الحوادث الجسيمة",
        "Serious incident rate"
      ),
    unit: "/1,000",
  },
  {
    key: "incident_followup_sla",
    label: () =>
      dashboardText(
        "dashboard.kpi.incident_followup_sla",
        "الالتزام بمتابعة الحوادث",
        "Incident follow-up compliance"
      ),
    unit: "%",
  },
  {
    key: "chronic_absence_rate",
    label: () =>
      dashboardText(
        "dashboard.kpi.chronic_absence_rate",
        "الغياب المزمن",
        "Chronic absence rate"
      ),
    unit: "%",
  },
  {
    key: "capacity_utilization_rate",
    label: () =>
      dashboardText(
        "dashboard.kpi.capacity_utilization_rate",
        "استغلال السعة",
        "Capacity utilization"
      ),
    unit: "%",
  },
  {
    key: "active_enrollments",
    label: () =>
      dashboardText(
        "dashboard.kpi.active_enrollments",
        "التسجيلات النشطة",
        "Active enrollments"
      ),
    unit: "",
  },
  {
    key: "new_enrollments",
    label: () =>
      dashboardText(
        "dashboard.kpi.new_enrollments",
        "التسجيلات الجديدة",
        "New enrollments"
      ),
    unit: "",
  },
];

/* ── KPI Explanation Metadata ──────────────────────────────────────────── */
const KPI_EXPLAIN_META = {
  overall_gcei: {
    icon: "bi-speedometer2",
    iconBg: "rgba(31,94,71,.1)",
    iconColor: "#1F5E47",
    meaning: "مؤشر شامل يقيّم أداء الروضة من خلال دمج عاملين رئيسيين: الحوكمة والإدارة (60%) وتجربة الطفل (40%). كلما ارتفعت الدرجة دلّت على تميّز في جميع الجوانب.",
    formula: "GCEI = (درجة الحوكمة × 60%) + (درجة تجربة الطفل × 40%)",
    importance: "هو المرجع الأول لتقييم أي روضة دفعةً واحدة ومقارنة الروضات وتحديد الأولويات الإشرافية.",
    thresholds: [
      { cls: "tp-green", label: "ممتاز",         range: "≥ 80"       },
      { cls: "tp-amber", label: "يحتاج تحسين",   range: "60 – 79.9"  },
      { cls: "tp-red",   label: "حرج",            range: "< 60"       },
    ],
    criticalAction: "إجراء تدقيق شامل للعمليات الإدارية، وتحديد المؤشرات الفرعية المنخفضة (الحضور / التقارير / الحوادث) وإعداد خطة تصحيح فورية.",
    dataSource: "/api/kpi/dashboard-data → overall_gcei",
  },
  attendance_rate: {
    icon: "bi-calendar-check",
    iconBg: "rgba(25,135,84,.1)",
    iconColor: "#198754",
    meaning: "نسبة الأيام التي حضر فيها الأطفال المسجّلون نشطاً إلى مجموع أيام الحضور المتوقعة في الفترة الزمنية المحددة (مع مراعاة تاريخَي بداية ونهاية كل تسجيل).",
    formula: "(أيام الحضور الفعلية للأطفال ÷ أيام الحضور المتوقعة) × 100",
    importance: "يعكس جاذبية البرامج التعليمية وجودة الرعاية، ويساعد في تحديد الأطفال الذين يحتاجون متابعة خاصة.",
    thresholds: [
      { cls: "tp-green", label: "ممتاز",         range: "≥ 90%"      },
      { cls: "tp-amber", label: "يحتاج متابعة",  range: "70 – 89.9%" },
      { cls: "tp-red",   label: "حرج",            range: "< 70%"      },
    ],
    criticalAction: "التواصل مع أولياء الأمور لمعرفة أسباب الغياب، ومراجعة جدول الأنشطة لرفع مستوى الجاذبية.",
    dataSource: "/api/kpi/dashboard-data → attendance_rate",
  },
  ratio_compliance: {
    icon: "bi-people-fill",
    iconBg: "rgba(13,110,253,.1)",
    iconColor: "#0d6efd",
    meaning: "نسبة الدقائق التي التزمت فيها الروضة بالنسبة المعتمدة (معلم لكل 10 أطفال) إلى إجمالي دقائق التشغيل خلال الفترة.",
    formula: "(دقائق الامتثال ÷ دقائق التشغيل الكلية) × 100",
    importance: "يضمن سلامة الأطفال وجودة الرعاية الفردية؛ النسبة المنخفضة تُشير إلى نقص في الكوادر.",
    thresholds: [
      { cls: "tp-green", label: "ممتاز",   range: "≥ 95%"      },
      { cls: "tp-amber", label: "مقبول",    range: "80 – 94.9%" },
      { cls: "tp-red",   label: "خطر",      range: "< 80%"      },
    ],
    criticalAction: "تحسين جدولة الموظفين، وإعداد خطة طوارئ للكوادر الاحتياطية عند الغياب.",
    dataSource: "/api/kpi/dashboard-data → ratio_compliance",
  },
  training_completion_rate: {
    icon: "bi-mortarboard-fill",
    iconBg: "rgba(111,66,193,.1)",
    iconColor: "#6f42c1",
    meaning: "نسبة الموظفين الذين أكملوا التدريبات الإلزامية (السلامة، الإسعافات الأولية، الرعاية التعليمية) إلى إجمالي الموظفين النشطين.",
    formula: "(الموظفون الذين أكملوا التدريب ÷ إجمالي الموظفين) × 100",
    importance: "يعكس مستوى الالتزام بالمعايير المهنية ويؤثر مباشرة على جودة الرعاية المقدمة للأطفال.",
    thresholds: [
      { cls: "tp-green", label: "ممتاز",   range: "≥ 90%"      },
      { cls: "tp-amber", label: "مقبول",    range: "75 – 89.9%" },
      { cls: "tp-red",   label: "متدنٍّ",   range: "< 75%"      },
    ],
    criticalAction: "إعداد خطة تدريب سنوية شاملة وجدولة دورات فورية للموظفين المتأخرين، مع برنامج حوافز للمتميزين.",
    dataSource: "/api/kpi/dashboard-data → training_completion_rate",
  },
  report_submission_rate: {
    icon: "bi-file-earmark-text-fill",
    iconBg: "rgba(32,201,151,.1)",
    iconColor: "#20c997",
    meaning: "نسبة التقارير اليومية المُرسَلة إلى التقارير المتوقعة خلال الفترة. يقيس انتظام التواصل مع أولياء الأمور.",
    formula: "(التقارير المُرسَلة ÷ التقارير المتوقعة) × 100",
    importance: "يبني الثقة مع أولياء الأمور ويُمكّن المشرفين من متابعة تطور كل طفل بشكل يومي.",
    thresholds: [
      { cls: "tp-green", label: "ممتاز",   range: "≥ 95%"      },
      { cls: "tp-amber", label: "مقبول",    range: "85 – 94.9%" },
      { cls: "tp-red",   label: "ضعيف",     range: "< 85%"      },
    ],
    criticalAction: "تبسيط نموذج التقرير وإعداد تذكيرات تلقائية للمشرفين مع قوالب جاهزة للإرسال السريع.",
    dataSource: "/api/kpi/dashboard-data → report_submission_rate",
  },
  incident_rate: {
    icon: "bi-shield-exclamation",
    iconBg: "rgba(255,193,7,.12)",
    iconColor: "#d97706",
    meaning: "عدد الحوادث (من أي نوع) لكل 1,000 طفل-يوم حضور خلال الفترة. يُوحّد القياس بين الروضات بأحجام مختلفة.",
    formula: "(عدد الحوادث الكلية ÷ أيام الحضور الفعلية للأطفال) × 1,000",
    importance: "يُقيّم مستوى السلامة ويكشف الأنماط المتكررة التي تتطلب تدخلاً وقائياً.",
    thresholds: [
      { cls: "tp-green", label: "آمن",               range: "≤ 2.0"      },
      { cls: "tp-amber", label: "تحت المراقبة",      range: "2.01 – 5.0" },
      { cls: "tp-red",   label: "خطر",               range: "> 5.0"      },
    ],
    criticalAction: "إجراء تدقيق أمني شامل، وتحليل جذور الحوادث، وتدريب شهري للموظفين على إجراءات السلامة والوقاية.",
    dataSource: "/api/kpi/dashboard-data → incident_rate",
  },
  serious_incident_rate: {
    icon: "bi-shield-fill-exclamation",
    iconBg: "rgba(220,53,69,.1)",
    iconColor: "#dc3545",
    meaning: "الحوادث ذات الخطورة العالية (HIGH) أو الحرجة (CRITICAL) التي تتطلب تدخلاً طبياً أو إسعافاً، لكل 1,000 طفل-يوم.",
    formula: "(الحوادث HIGH أو CRITICAL ÷ أيام الحضور الفعلية) × 1,000",
    importance: "الهدف الصفر المطلق. أي حادثة جسيمة تستوجب إبلاغاً فورياً وتحقيقاً منهجياً.",
    thresholds: [
      { cls: "tp-green", label: "آمن",     range: "= 0.0"          },
      { cls: "tp-amber", label: "تنبيه",   range: "0.001 – 0.5"   },
      { cls: "tp-red",   label: "طارئ",    range: "> 0.5"          },
    ],
    criticalAction: "إطلاق بروتوكول الطوارئ فوراً، وإبلاغ الجهات الرسمية وأولياء الأمور، وإجراء تحقيق شامل في غضون 24 ساعة.",
    dataSource: "/api/kpi/dashboard-data → serious_incident_rate",
  },
  incident_followup_sla: {
    icon: "bi-clock-history",
    iconBg: "rgba(253,126,20,.1)",
    iconColor: "#fd7e14",
    meaning: "نسبة الحوادث التي تم إغلاق ملفاتها (التحقيق + الإجراءات التصحيحية + إبلاغ الأهل) خلال 48 ساعة من وقوع الحادثة.",
    formula: "(الحوادث المغلقة ≤ 48 ساعة ÷ الحوادث التي تستوجب متابعة) × 100",
    importance: "يعكس سرعة استجابة الإدارة ويبني الثقة مع أولياء الأمور من خلال الشفافية والسرعة في التعامل.",
    thresholds: [
      { cls: "tp-green", label: "مثالي",   range: "= 100%"      },
      { cls: "tp-amber", label: "مقبول",   range: "90 – 99.9%"  },
      { cls: "tp-red",   label: "ضعيف",    range: "< 90%"       },
    ],
    criticalAction: "توحيد عملية متابعة الحوادث بخطوات واضحة ومواعيد نهائية، وإنشاء نظام تتبع إلكتروني بتذكيرات تلقائية.",
    dataSource: "/api/kpi/dashboard-data → incident_followup_sla",
  },
  chronic_absence_rate: {
    icon: "bi-person-dash-fill",
    iconBg: "rgba(108,117,125,.1)",
    iconColor: "#6c757d",
    meaning: "نسبة الأطفال الذين تجاوز غيابهم 10% من أيامهم المتوقعة في الفترة. يُحسب لكل طفل بناءً على تاريخ تسجيله الخاص.",
    formula: "(الأطفال الذين غابوا > 10% من أيامهم المتوقعة ÷ إجمالي الأطفال) × 100",
    importance: "الغياب المزمن يؤثر سلباً على التعلم والتطور الاجتماعي ويكشف عن مشكلات صحية أو أسرية تحتاج دعماً.",
    thresholds: [
      { cls: "tp-green", label: "ممتاز",        range: "< 5%"   },
      { cls: "tp-amber", label: "مثير للقلق",   range: "5 – 10%" },
      { cls: "tp-red",   label: "حرج",          range: "> 10%"  },
    ],
    criticalAction: "تفعيل نظام تتبع فردي مع إشعارات مبكرة للأهل، وتقديم دعم استشاري لحالات الغياب المتكرر.",
    dataSource: "/api/kpi/dashboard-data → chronic_absence_rate",
  },
  capacity_utilization_rate: {
    icon: "bi-building-fill",
    iconBg: "rgba(13,202,240,.1)",
    iconColor: "#0dcaf0",
    meaning: "نسبة الأطفال المسجلين نشطاً إلى الطاقة الاستيعابية القصوى للروضة. تجاوز 100% يعني اكتظاظاً.",
    formula: "(الأطفال المسجلون نشطاً ÷ الطاقة الاستيعابية القصوى) × 100",
    importance: "يساعد في التخطيط للنمو والتوسع ويضمن توفير مساحة ورعاية كافية لكل طفل.",
    thresholds: [
      { cls: "tp-green", label: "مثالي",   range: "90 – 100%"  },
      { cls: "tp-amber", label: "مقبول",   range: "80 – 89.9%" },
      { cls: "tp-red",   label: "مشكلة",   range: "< 80% أو > 100%" },
    ],
    criticalAction: "إجراء دراسة توسع عند الاقتراب من الحد الأقصى، ودراسة خيارات الجدولة المرنة عند الاكتظاظ.",
    dataSource: "/api/kpi/dashboard-data → capacity_utilization_rate",
  },
  active_enrollments: {
    icon: "bi-person-check-fill",
    iconBg: "rgba(47,125,98,.1)",
    iconColor: "#2F7D62",
    meaning: "عدد الأطفال المسجّلين حالياً بحالة نشطة (ACTIVE) في الروضة أو مجموعة الروضات المُحدَّدة.",
    formula: "عدّ سجلات التسجيل ذات الحالة = ACTIVE",
    importance: "يُعطي صورة فورية عن الطلب الحالي ويُستخدم قاسماً في حساب معظم المؤشرات الأخرى.",
    thresholds: [
      { cls: "tp-green", label: "طبيعي",   range: "حسب الطاقة الاستيعابية" },
    ],
    criticalAction: "مقارنة العدد بالطاقة الاستيعابية وتفعيل قائمة الانتظار عند الامتلاء.",
    dataSource: "/api/kpi/dashboard-data → active_enrollments",
  },
  new_enrollments: {
    icon: "bi-person-plus-fill",
    iconBg: "rgba(102,16,242,.1)",
    iconColor: "#6610f2",
    meaning: "عدد التسجيلات الجديدة التي أُضيفت خلال الفترة الزمنية المحددة في لوحة التحكم.",
    formula: "عدّ سجلات التسجيل المُنشَأة خلال نطاق التاريخ المحدد",
    importance: "يعكس معدل النمو وفعالية حملات التسويق والتوعية المجتمعية.",
    thresholds: [
      { cls: "tp-green", label: "نمو",   range: "أعلى من المتوسط السابق" },
    ],
    criticalAction: "مقارنة الأرقام بالفترات السابقة وتحليل أسباب الانخفاض إن وُجد.",
    dataSource: "/api/kpi/dashboard-data → new_enrollments",
  },
};

const BAND_BOOTSTRAP = {
  green: "success",
  amber: "warning",
  red: "danger",
  neutral: "secondary",
  insufficient: "secondary",
};

const BAND_LABEL = {
  green: () => dashboardText("dashboard.band.green", "جيد", "Good"),
  amber: () => dashboardText("dashboard.band.amber", "متوسط", "Needs follow-up"),
  red: () => dashboardText("dashboard.band.red", "حرج", "Critical"),
  neutral: () => dashboardText("dashboard.band.neutral", "محايد", "Neutral"),
  insufficient: () => dashboardText("dashboard.band.insufficient", "بيانات غير كافية", "Insufficient data"),
};

const DASHBOARD_STATE = {
  kpis: [],
  attendanceChart: null,
  enrollmentChart: null,
  attendanceSeries: [],
  attendanceChartType: "line",
  latestRequestId: 0,
  isLoading: false,
  validation: {
    status: "unknown",
    summary: dashboardText(
      "dashboard.validation.checking",
      "جار التحقق من سلامة البيانات...",
      "Validating data integrity..."
    ),
    checks: [],
    lastUpdated: null,
  },
  managerSummary: {
    classes: 0,
    pendingReports: 0,
    activeSupervisors: 0,
    parents: 0,
  },
};
const DASHBOARD_REQUEST_CACHE_KEY = "kinjo_dashboard_response_cache_v1";
const DASHBOARD_CACHE_TTL_MS = 15000;
const dashboardInFlight = new Map();

function nowMs() {
  return Date.now();
}

function shouldCacheDashboardRequest(url) {
  if (!url || typeof url !== "string") return false;
  return (
    url.startsWith("/api/admin/dashboard") ||
    url.startsWith("/api/supervisor/dashboard") ||
    url.startsWith("/api/manager/") ||
    url.startsWith("/api/kpi/") ||
    url.startsWith("/api/users/me")
  );
}

function readDashboardCacheStore() {
  try {
    const raw = sessionStorage.getItem(DASHBOARD_REQUEST_CACHE_KEY);
    if (!raw) return {};
    const parsed = JSON.parse(raw);
    return parsed && typeof parsed === "object" ? parsed : {};
  } catch (_error) {
    return {};
  }
}

function writeDashboardCacheStore(store) {
  try {
    sessionStorage.setItem(DASHBOARD_REQUEST_CACHE_KEY, JSON.stringify(store));
  } catch (_error) {
    // Ignore cache persistence failures.
  }
}

function getDashboardCachedResponse(cacheKey) {
  const store = readDashboardCacheStore();
  const entry = store[cacheKey];
  if (!entry || typeof entry !== "object") return null;
  const expiresAt = Number(entry.expiresAt || 0);
  if (!Number.isFinite(expiresAt) || expiresAt <= nowMs()) {
    delete store[cacheKey];
    writeDashboardCacheStore(store);
    return null;
  }
  return entry.payload ?? null;
}

function setDashboardCachedResponse(cacheKey, payload) {
  const store = readDashboardCacheStore();
  store[cacheKey] = {
    payload,
    expiresAt: nowMs() + DASHBOARD_CACHE_TTL_MS,
  };
  writeDashboardCacheStore(store);
}

const currentUserRole = window.currentUserRole || "PARENT";

function safeRoleValue(role) {
  return String(role || "").toUpperCase();
}

function getDashboardDateRange() {
  const state = window.dashboardDateRange || {};
  const params = {};
  if (state.start) params.period_start = state.start;
  if (state.end) params.period_end = state.end;
  if (state.range) params.range = state.range;
  return params;
}

function buildUrlWithParams(url, params = {}) {
  const query = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value == null || value === "") return;
    if (Array.isArray(value)) {
      value.forEach((item) => {
        if (item != null && item !== "") query.append(key, String(item));
      });
      return;
    }
    query.append(key, String(value));
  });
  const qs = query.toString();
  return qs ? `${url}?${qs}` : url;
}

function setDashboardLoadingState(isLoading) {
  DASHBOARD_STATE.isLoading = Boolean(isLoading);
  document.body.setAttribute("aria-busy", isLoading ? "true" : "false");
}

function updateValidationIndicator(status, summary, checks = []) {
  const indicator = document.getElementById("validationStatusIndicator");
  const normalizedStatus = ["valid", "warning", "error", "unknown"].includes(status)
    ? status
    : "unknown";
  const resolvedSummary =
    summary || dashboardText("common.not_available", "غير متاح", "Not available");

  DASHBOARD_STATE.validation = {
    status: normalizedStatus,
    summary: resolvedSummary,
    checks: Array.isArray(checks) ? checks : [],
    lastUpdated: new Date().toISOString(),
  };

  if (!indicator) return;

  indicator.classList.remove("status-valid", "status-warning", "status-error", "status-unknown");
  indicator.classList.add(`status-${normalizedStatus}`);

  const icon = indicator.querySelector("i");
  if (icon) {
    icon.className =
      normalizedStatus === "valid"
        ? "bi bi-check-circle-fill me-1"
        : normalizedStatus === "warning"
          ? "bi bi-exclamation-triangle-fill me-1"
          : normalizedStatus === "error"
            ? "bi bi-x-circle-fill me-1"
            : "bi bi-question-circle-fill me-1";
  }

  const label = indicator.querySelector("span");
  if (label) label.textContent = resolvedSummary;
}

function renderValidationDetails() {
  const container = document.querySelector("#validationDetailsModal .validation-report");
  if (!container) return;

  const state = DASHBOARD_STATE.validation;
  const checks = Array.isArray(state.checks) ? state.checks : [];
  const statusClass =
    state.status === "valid"
      ? "success"
      : state.status === "warning"
        ? "warning"
        : state.status === "error"
          ? "danger"
          : "secondary";
  const statusLabel =
    state.status === "valid"
      ? dashboardText("dashboard.validation.valid", "سليم", "Valid")
      : state.status === "warning"
        ? dashboardText(
            "dashboard.validation.warning",
            "يحتاج متابعة",
            "Needs follow-up"
          )
        : state.status === "error"
          ? dashboardText(
              "dashboard.validation.error",
              "تعذر التحقق",
              "Validation failed"
            )
          : dashboardText("dashboard.validation.unknown", "غير معروف", "Unknown");

  const rows = checks.length
    ? checks
        .map((check) => {
          const cStatus = check.ok ? "success" : "danger";
          const cLabel = check.ok
            ? dashboardText("common.success", "نجح", "Passed")
            : dashboardText("common.failed", "تعذر", "Failed");
          return `
            <tr>
              <td>${escapeHtml(check.name || "-")}</td>
              <td><span class="badge bg-${cStatus}">${cLabel}</span></td>
              <td>${escapeHtml(check.message || "-")}</td>
            </tr>
          `;
        })
        .join("")
    : `<tr><td colspan="3" class="text-center text-muted py-3">${dashboardText(
        "dashboard.validation.no_extra_details",
        "لا توجد تفاصيل إضافية",
        "No additional details"
      )}</td></tr>`;

  const lastUpdated = state.lastUpdated
    ? new Date(state.lastUpdated).toLocaleString(dashboardCurrentLocale())
    : dashboardText("common.not_available", "غير متاح", "Not available");

  container.innerHTML = `
    <div class="alert alert-${statusClass}-subtle border border-${statusClass} mb-3">
      <div class="d-flex justify-content-between align-items-center flex-wrap gap-2">
        <div class="fw-semibold">${escapeHtml(state.summary || dashboardText("common.not_available", "غير متاح", "Not available"))}</div>
        <span class="badge bg-${statusClass}">${statusLabel}</span>
      </div>
      <div class="small text-muted mt-1">${dashboardText("common.last_updated", "آخر تحديث", "Last updated")}: ${escapeHtml(lastUpdated)}</div>
    </div>
    <div class="table-responsive">
      <table class="table table-sm align-middle">
        <thead>
          <tr>
            <th>${dashboardText("dashboard.validation.check", "الفحص", "Check")}</th>
            <th>${dashboardText("dashboard.validation.result", "النتيجة", "Result")}</th>
            <th>${dashboardText("dashboard.validation.details", "التفاصيل", "Details")}</th>
          </tr>
        </thead>
        <tbody>${rows}</tbody>
      </table>
    </div>
  `;
}

function updateElementText(id, value) {
  const element = document.getElementById(id);
  if (element) {
    // Remove shimmer placeholder and set real value
    element.querySelectorAll(".kj-stat-pending").forEach((el) => el.remove());
    element.textContent = value;
  }
}

function safeNumber(value, fallback = 0) {
  const n = Number(value);
  return Number.isFinite(n) ? n : fallback;
}

function formatNumber(value) {
  return safeNumber(value).toLocaleString(dashboardCurrentLocale());
}

function formatOneDecimal(value) {
  return safeNumber(value).toFixed(1);
}

function formatMaybeNumber(value) {
  if (value == null || value === "") return "-";
  const n = Number(value);
  if (!Number.isFinite(n)) return "-";
  return formatNumber(n);
}

function formatDateLabel(input) {
  if (!input) return "";
  const d = new Date(input);
  if (Number.isNaN(d.getTime())) return String(input);
  return d.toLocaleDateString(dashboardCurrentLocale(), { month: "short", day: "numeric" });
}

function getNameInitial(name) {
  const normalized = String(name || "").trim();
  if (!normalized) return "-";
  return normalized.charAt(0).toUpperCase();
}

function formatLocalizedDate(input) {
  if (!input) return "-";
  const parsed = new Date(input);
  if (Number.isNaN(parsed.getTime())) return String(input);
  return parsed.toLocaleDateString(dashboardCurrentLocale());
}

function getDaysSinceDate(input) {
  if (!input) return null;
  const parsed = new Date(input);
  if (Number.isNaN(parsed.getTime())) return null;
  const today = new Date();
  const todayDate = new Date(today.getFullYear(), today.getMonth(), today.getDate());
  const targetDate = new Date(parsed.getFullYear(), parsed.getMonth(), parsed.getDate());
  const msPerDay = 24 * 60 * 60 * 1000;
  const raw = Math.floor((todayDate - targetDate) / msPerDay);
  return Math.max(raw, 0);
}

function reportPriorityMeta(reportDate) {
  const days = getDaysSinceDate(reportDate);
  if (days == null) {
    return {
      levelClass: "level-medium",
      label: dashboardText(
        "dashboard.priority.needs_followup",
        "تحتاج متابعة",
        "Needs follow-up"
      ),
    };
  }
  if (days >= 3) {
    return {
      levelClass: "level-high",
      label:
        dashboardCurrentLang() === "en"
          ? `Overdue by ${formatNumber(days)} day(s)`
          : `${dashboardText("dashboard.priority.overdue_prefix", "متأخر", "Overdue")} ${formatNumber(days)} ${dashboardText("dashboard.priority.day", "يوم", "day(s)")}`,
    };
  }
  if (days >= 1) {
    return {
      levelClass: "level-medium",
      label:
        dashboardCurrentLang() === "en"
          ? `Pending review for ${formatNumber(days)} day(s)`
          : `${dashboardText("dashboard.priority.pending_review_since", "بانتظار المراجعة منذ", "Pending review for")} ${formatNumber(days)} ${dashboardText("dashboard.priority.day", "يوم", "day(s)")}`,
    };
  }
  return {
    levelClass: "level-low",
    label: dashboardText(
      "dashboard.priority.new_today",
      "تقرير جديد اليوم",
      "New report today"
    ),
  };
}

function utilizationColor(percent) {
  const pct = clampPercent(percent);
  if (pct >= 100) return "danger";
  if (pct >= 85) return "warning";
  return "success";
}

function clampPercent(value) {
  const n = safeNumber(value);
  if (n < 0) return 0;
  if (n > 100) return 100;
  return n;
}

function escapeHtml(text) {
  if (text == null) return "";
  return String(text)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function normalizeBand(raw) {
  const value = String(raw || "")
    .trim()
    .toLowerCase();
  if (!value) return null;
  if (["green", "excellent", "good", "success"].includes(value)) return "green";
  if (["amber", "yellow", "average", "warning", "caution"].includes(value)) return "amber";
  if (["red", "poor", "critical", "danger"].includes(value)) return "red";
  if (value === "insufficient") return "insufficient";
  return "neutral";
}

function normalizeTrend(raw) {
  const value = String(raw || "")
    .trim()
    .toLowerCase();
  if (["up", "increase", "rising"].includes(value)) return "up";
  if (["down", "decrease", "falling"].includes(value)) return "down";
  return "flat";
}

function trendSymbol(trend) {
  if (trend === "up") return dashboardText("dashboard.trend.up", "صاعد", "Up");
  if (trend === "down") return dashboardText("dashboard.trend.down", "هابط", "Down");
  return dashboardText("dashboard.trend.flat", "ثابت", "Flat");
}

function inferBand(metricKey, value) {
  const n = safeNumber(value);
  const lowerIsBetter = new Set(["incident_rate", "serious_incident_rate", "chronic_absence_rate"]);

  if (metricKey === "overall_gcei") {
    if (n >= 80) return "green";
    if (n >= 60) return "amber";
    return "red";
  }

  if (metricKey === "capacity_utilization_rate") {
    if (n >= 70 && n <= 95) return "green";
    if ((n >= 50 && n < 70) || (n > 95 && n <= 110)) return "amber";
    return "red";
  }

  if (metricKey === "incident_rate") {
    if (n <= 2.0) return "green";
    if (n <= 5.0) return "amber";
    return "red";
  }
  if (metricKey === "serious_incident_rate") {
    if (n === 0) return "green";
    if (n <= 0.5) return "amber";
    return "red";
  }
  if (lowerIsBetter.has(metricKey)) {
    if (n <= 5) return "green";
    if (n <= 10) return "amber";
    return "red";
  }

  if (metricKey === "active_enrollments" || metricKey === "new_enrollments") {
    return "neutral";
  }

  if (n >= 85) return "green";
  if (n >= 70) return "amber";
  return "red";
}

function statusLabel(status) {
  const s = String(status || "").toUpperCase();
  const labels = {
    ACTIVE: dashboardText("status.active", "نشط", "Active"),
    DRAFT: dashboardText("status.draft", "مسودة", "Draft"),
    INACTIVE: dashboardText("status.inactive", "غير نشط", "Inactive"),
    ARCHIVED: dashboardText("status.archived", "مؤرشف", "Archived"),
    PENDING_REVIEW: dashboardText(
      "status.pending_review",
      "بانتظار المراجعة",
      "Pending review"
    ),
    SUBMITTED: dashboardText("status.submitted", "مقدم", "Submitted"),
    APPROVED: dashboardText("status.approved", "معتمد", "Approved"),
    WAITLISTED: dashboardText("status.waitlisted", "قائمة الانتظار", "Waitlisted"),
    SENT_TO_PARENT: dashboardText(
      "status.sent_to_parent",
      "مرسل لولي الأمر",
      "Sent to parent"
    ),
    ACCEPTED: dashboardText("status.accepted", "مقبول", "Accepted"),
    REJECTED: dashboardText("status.rejected", "مرفوض", "Rejected"),
    WITHDRAWN: dashboardText("status.withdrawn", "منسحب", "Withdrawn"),
  };
  return labels[s] || dashboardText("common.unspecified", "غير محدد", "Unspecified");
}

async function dashboardFetch(url, options = {}) {
  const method = String(options.method || "GET").toUpperCase();
  const canCache = method === "GET" && shouldCacheDashboardRequest(url);
  const cacheKey = `${method}:${url}`;

  if (canCache) {
    const cached = getDashboardCachedResponse(cacheKey);
    if (cached != null) {
      return cached;
    }
    if (dashboardInFlight.has(cacheKey)) {
      return dashboardInFlight.get(cacheKey);
    }
  }

  const requestPromise = (async () => {
    const headers = {
      "Content-Type": "application/json",
      ...options.headers,
    };

    let response = null;
    if (typeof window.fetchWithAuth === "function") {
      response = await window.fetchWithAuth(url, { ...options, headers });
      if (!response) {
        throw new Error(
          dashboardText("auth.login.required", "يتطلب تسجيل الدخول", "Sign-in is required")
        );
      }
    } else {
      const token = localStorage.getItem("kinjo_token") || sessionStorage.getItem("kinjo_token");
      if (token) {
        headers.Authorization = `Bearer ${token}`;
      }
      response = await fetch(url, { ...options, headers });
    }

    if (!response.ok) {
      let message = "";
      const contentType = response.headers.get("content-type") || "";
      if (contentType.includes("application/json")) {
        const payload = await response.json().catch(() => ({}));
        message = payload?.detail?.message || payload?.detail || payload?.message || "";
      } else {
        message = await response.text().catch(() => "");
      }
      throw new Error(
        message ||
          response.statusText ||
          dashboardText("common.unexpected_error", "حدث خطأ غير متوقع", "Unexpected error")
      );
    }

    if (response.status === 204) return null;
    const payload = await response.json().catch(() => ({}));
    if (canCache) {
      setDashboardCachedResponse(cacheKey, payload);
    }
    return payload;
  })();

  if (!canCache) {
    return requestPromise;
  }

  dashboardInFlight.set(cacheKey, requestPromise);
  try {
    return await requestPromise;
  } finally {
    dashboardInFlight.delete(cacheKey);
  }
}

async function loadDashboard() {
  const requestId = ++DASHBOARD_STATE.latestRequestId;
  setDashboardLoadingState(true);
  updateValidationIndicator(
    "unknown",
    dashboardText(
      "dashboard.validation.checking",
      "جار التحقق من سلامة البيانات...",
      "Validating data integrity..."
    )
  );

  try {
    const currentUser = await dashboardFetch("/api/users/me");
    const actualRole = currentUser.role;

    if (actualRole === "SUPERVISOR" && currentUserRole !== "SUPERVISOR") {
      window.location.href = "/supervisor/dashboard";
      return;
    }
    if (actualRole === "PARENT" && currentUserRole !== "PARENT") {
      window.location.href = "/parent/dashboard";
      return;
    }
    if (
      (actualRole === "ADMIN" || actualRole === "MANAGER") &&
      (currentUserRole === "SUPERVISOR" || currentUserRole === "PARENT")
    ) {
      window.location.href = "/dashboard";
      return;
    }

    if (requestId !== DASHBOARD_STATE.latestRequestId) return;

    if (currentUserRole === "SUPERVISOR") {
      await loadSupervisorDashboard();
      updateValidationIndicator(
        "valid",
        dashboardText(
          "dashboard.validation.supervisor_loaded",
          "تم تحميل لوحة المشرف بنجاح",
          "Supervisor dashboard loaded successfully"
        ),
        [
          {
            name: dashboardText(
              "dashboard.validation.user_identity",
              "هوية المستخدم",
              "User identity"
            ),
            ok: true,
            message: dashboardText(
              "dashboard.validation.session_verified",
              "تم التحقق من صلاحية الجلسة.",
              "Session validity verified."
            ),
          },
          {
            name: dashboardText(
              "dashboard.validation.supervisor_data",
              "بيانات لوحة المشرف",
              "Supervisor dashboard data"
            ),
            ok: true,
            message: dashboardText(
              "dashboard.validation.core_loaded",
              "تم تحميل البيانات الأساسية.",
              "Core data loaded."
            ),
          },
        ]
      );
      return;
    }
    if (currentUserRole === "MANAGER") {
      await loadManagerDashboard();
      const hasAnyKpi = DASHBOARD_STATE.kpis.length > 0;
      updateValidationIndicator(
        hasAnyKpi ? "valid" : "warning",
        hasAnyKpi
          ? dashboardText(
              "dashboard.validation.manager_loaded",
              "تم تحميل لوحة المدير بنجاح",
              "Manager dashboard loaded successfully"
            )
          : dashboardText(
              "dashboard.validation.kpi_missing",
              "تم تحميل الصفحة مع نقص في مؤشرات الأداء الرئيسية.",
              "Loaded with missing KPI indicators"
            ),
        [
          {
            name: dashboardText(
              "dashboard.validation.user_identity",
              "هوية المستخدم",
              "User identity"
            ),
            ok: true,
            message: dashboardText(
              "dashboard.validation.session_verified",
              "تم التحقق من صلاحية الجلسة.",
              "Session validity verified."
            ),
          },
          {
            name: dashboardText(
              "dashboard.validation.classes_reports",
              "الفصول والتقارير",
              "Classes and reports"
            ),
            ok: true,
            message: dashboardText(
              "dashboard.validation.operational_loaded",
              "تم تحميل الأقسام التشغيلية.",
              "Operational sections loaded."
            ),
          },
          {
            name: dashboardText("dashboard.validation.kpi", "مؤشرات الأداء الرئيسية (KPI)", "KPIs"),
            ok: hasAnyKpi,
            message: hasAnyKpi
              ? dashboardText(
                  "dashboard.validation.kpi_loaded",
                  "تم تحميل مؤشرات الأداء الرئيسية.",
                  "KPI indicators loaded."
                )
              : dashboardText(
                  "dashboard.validation.kpi_failed",
                  "تعذر تحميل مؤشرات الأداء الرئيسية بالكامل.",
                  "Unable to load all KPI indicators."
                ),
          },
        ]
      );
      return;
    }
    if (currentUserRole === "ADMIN") {
      await loadAdminDashboard();
      const hasCriticalKpis = DASHBOARD_STATE.kpis.some((kpi) => kpi.band === "red");
      const hasAnyKpi = DASHBOARD_STATE.kpis.length > 0;
      const status = !hasAnyKpi ? "warning" : hasCriticalKpis ? "warning" : "valid";
      const summary = !hasAnyKpi
        ? dashboardText(
            "dashboard.validation.admin_missing_metrics",
            "تم تحميل الصفحة مع نقص في بيانات المؤشرات.",
            "Loaded with missing indicator data"
          )
        : hasCriticalKpis
          ? dashboardText(
              "dashboard.validation.admin_critical_kpis",
              "تم تحميل الصفحة مع وجود مؤشرات حرجة تحتاج إلى متابعة.",
              "Loaded with critical indicators that need follow-up"
            )
          : dashboardText(
              "dashboard.validation.admin_loaded",
              "تم تحميل لوحة الإدارة بنجاح",
              "Admin dashboard loaded successfully"
            );
      updateValidationIndicator(status, summary, [
        {
          name: dashboardText(
            "dashboard.validation.user_identity",
            "هوية المستخدم",
            "User identity"
          ),
          ok: true,
          message: dashboardText(
            "dashboard.validation.session_verified",
            "تم التحقق من صلاحية الجلسة.",
            "Session validity verified."
          ),
        },
        {
          name: dashboardText(
            "dashboard.validation.admin_data",
            "بيانات الإدارة",
            "Administration data"
          ),
          ok: true,
          message: dashboardText(
            "dashboard.validation.kg_summary_loaded",
            "تم تحميل بيانات الروضات والملخص.",
            "Kindergarten and summary data loaded."
          ),
        },
        {
          name: dashboardText("dashboard.validation.kpi", "مؤشرات الأداء الرئيسية (KPI)", "KPIs"),
          ok: hasAnyKpi,
          message: hasAnyKpi
            ? dashboardText(
                "dashboard.validation.kpi_loaded",
                "تم تحميل مؤشرات الأداء الرئيسية.",
                "KPI indicators loaded."
              )
            : dashboardText(
                "dashboard.validation.kpi_failed",
                "تعذر تحميل مؤشرات الأداء الرئيسية بالكامل.",
                "Unable to load all KPI indicators."
              ),
        },
      ]);
      return;
    }
    if (currentUserRole === "PARENT") {
      await loadParentDashboard();
      updateValidationIndicator(
        "valid",
        dashboardText(
          "dashboard.validation.parent_ready",
          "لوحة ولي الأمر جاهزة",
          "Parent dashboard is ready"
        ),
        [
          {
            name: dashboardText(
              "dashboard.validation.user_identity",
              "هوية المستخدم",
              "User identity"
            ),
            ok: true,
            message: dashboardText(
              "dashboard.validation.session_verified",
              "تم التحقق من صلاحية الجلسة.",
              "Session validity verified."
            ),
          },
        ]
      );
    }
  } catch (error) {
    console.error("Error loading dashboard:", error);
    updateValidationIndicator(
      "error",
      dashboardText(
        "dashboard.validation.load_failed",
        "تعذر تحميل البيانات بالكامل",
        "Unable to load all data"
      ),
      [
        {
          name: dashboardText(
            "dashboard.validation.user_session",
            "جلسة المستخدم",
            "User session"
          ),
          ok: false,
          message:
            error.message ||
            dashboardText(
              "dashboard.validation.session_fetch_failed",
              "تعذر استرجاع بيانات الجلسة.",
              "Unable to retrieve session data."
            ),
        },
      ]
    );
    if (error.message && error.message.includes("Forbidden")) {
      try {
        const user = await dashboardFetch("/api/users/me");
        if (user.role === "SUPERVISOR") window.location.href = "/supervisor/dashboard";
        else if (user.role === "PARENT") window.location.href = "/parent/dashboard";
        else window.location.href = "/dashboard";
      } catch {
        window.location.href = "/login";
      }
    }
  } finally {
    if (requestId === DASHBOARD_STATE.latestRequestId) {
      setDashboardLoadingState(false);
      renderValidationDetails();
    }
  }
}

async function loadSupervisorDashboard() {
  try {
    const data = await dashboardFetch(DASHBOARD_API.supervisor.dashboard);
    updateElementText("totalChildren", formatNumber(data.total_children || 0));
    updateElementText("todayAttendance", formatNumber(data.attendance_summary?.today || 0));
    updateElementText("pendingReports", formatNumber(data.pending_reports || 0));
  } catch (error) {
    console.error("Error loading supervisor dashboard:", error);
  }
}

async function loadManagerDashboard() {
  DASHBOARD_STATE.managerSummary = {
    classes: 0,
    pendingReports: 0,
    activeSupervisors: 0,
    parents: 0,
  };
  renderManagerSummary();

  const jobs = await Promise.allSettled([
    loadClasses(),
    loadSubmittedReports(),
    loadSupervisorStats(),
    loadManagerAccounts(),
    loadKPIs(),
  ]);

  renderManagerSummary();
  loadSuggestedActions();

  const failedJobs = jobs.filter((job) => job.status === "rejected");
  if (failedJobs.length > 0) {
    failedJobs.forEach((job) =>
      console.error("Error loading manager dashboard section:", job.reason)
    );
  }
}

async function loadAdminDashboard() {
  try {
    const rangeParams = getDashboardDateRange();
    const dashboardUrl = buildUrlWithParams(DASHBOARD_API.admin.dashboard, rangeParams);
    const kpiUrl = buildUrlWithParams(DASHBOARD_API.admin.kpis, {
      ...rangeParams,
      locale: dashboardCurrentLang(),
    });

    const [adminResult, kpiResult] = await Promise.allSettled([
      dashboardFetch(dashboardUrl),
      dashboardFetch(kpiUrl),
    ]);

    let adminAlerts = [];

    if (adminResult.status === "fulfilled") {
      const dashboard = adminResult.value || {};
      renderAdminSummaryCards(dashboard.summary || {});
      renderAdminSystemOverview(dashboard.system_overview || {});
      renderAdminKindergartensTable(dashboard.kindergartens || []);
      renderPendingReportsList(dashboard.kindergartens || [], dashboard.summary || {});
      renderAttendanceChart(dashboard.charts?.attendance || []);
      renderEnrollmentChart(dashboard.charts?.enrollment || {});
      adminAlerts = Array.isArray(dashboard.alerts) ? dashboard.alerts : [];
      renderAlerts(adminAlerts);
      if (dashboard.generated_at) {
        const tsEl = document.getElementById("dashboardLastUpdated");
        if (tsEl) {
          const dt = new Date(dashboard.generated_at);
          tsEl.textContent = dt.toLocaleTimeString(dashboardCurrentLocale(), { hour: "2-digit", minute: "2-digit" });
        }
      }
    } else {
      console.error("Error loading admin dashboard payload:", adminResult.reason);
      await loadKindergartensOverview();
    }

    if (kpiResult.status === "fulfilled") {
      await loadKPIs(kpiResult.value);
      if (adminAlerts.length > 0) {
        updateElementText("alertCount", String(adminAlerts.length));
      }
    } else {
      console.error("Error loading KPI payload:", kpiResult.reason);
      await loadKPIs();
    }
    loadSuggestedActions();
  } catch (error) {
    console.error("Error loading admin dashboard:", error);
    await Promise.all([loadKindergartensOverview(), loadKPIs()]);
  }
}

async function loadSuggestedActions() {
  try {
    const data = await dashboardFetch("/api/dashboard/suggested-actions");
    if (!data || !data.success || !Array.isArray(data.data)) return;
    const isEn = document.documentElement.lang === "en";

    for (const action of data.data) {
      if (action.id === "attendance_trend") {
        const cardEl  = document.getElementById("actionAttendanceCard");
        const descEl  = document.getElementById("actionAttendanceDesc");

        if (action.change !== null && action.change !== undefined) {
          const sign       = action.change >= 0 ? "↑" : "↓";
          const absChange  = Math.abs(action.change).toFixed(1);
          const rate       = action.current_rate != null ? action.current_rate.toFixed(1) : "—";

          if (descEl) {
            descEl.textContent = isEn
              ? `Attendance rate this week: ${rate}% (${sign} ${absChange}% vs last week).`
              : `معدل الحضور هذا الأسبوع: ${rate}% (${sign} ${absChange}% مقارنة بالأسبوع الماضي).`;
          }

          if (cardEl && action.change < -1) {
            cardEl.classList.add("border-danger");
          }
        }

        if (action.route && cardEl) {
          cardEl.href = action.route;
        }
      }

      if (action.id === "pending_enrollments") {
        const descEl = document.getElementById("actionEnrollmentDesc");
        if (descEl && action.pending_count > 0) {
          descEl.textContent = isEn
            ? `${action.pending_count} enrollment request(s) pending your review.`
            : `${action.pending_count} طلب تسجيل معلق بانتظار مراجعتك.`;
        }
      }
    }
  } catch (e) {
    console.warn("Suggested actions load failed:", e);
  }
}

async function loadParentDashboard() {
  // Parent dashboard is mostly server-rendered.
}

function renderManagerSummary() {
  updateElementText("managerSummaryClasses", formatNumber(DASHBOARD_STATE.managerSummary.classes));
  updateElementText(
    "managerSummaryPendingReports",
    formatNumber(DASHBOARD_STATE.managerSummary.pendingReports)
  );
  updateElementText(
    "managerSummarySupervisors",
    formatNumber(DASHBOARD_STATE.managerSummary.activeSupervisors)
  );
  updateElementText("managerSummaryParents", formatNumber(DASHBOARD_STATE.managerSummary.parents));
}

function renderManagerUsersTable(tableId, users, type) {
  const tableBody = document.getElementById(tableId);
  if (!tableBody) return;

  if (!Array.isArray(users) || users.length === 0) {
    const colspan = type === "supervisor" ? 4 : 5;
    tableBody.innerHTML = dashboardTemplate(
      `<tr><td colspan="${colspan}" class="text-center py-4 text-muted">لا توجد بيانات متاحة</td></tr>`
    );
    return;
  }

  if (type === "supervisor") {
    tableBody.innerHTML = dashboardTemplate(
      users
        .map((user) => {
          const displayName = user.full_name || user.username || "-";
          const initial = getNameInitial(displayName);
          const createdAt = user.created_at
            ? new Date(user.created_at).toLocaleDateString(dashboardCurrentLocale())
            : "-";
          const userId = user.id != null ? String(user.id) : "";
          const profileLink = userId
            ? `/communication/messages?recipient=${encodeURIComponent(userId)}`
            : "#";
          const actionAttrs = userId
            ? 'class="btn btn-sm btn-outline-primary"'
            : 'class="btn btn-sm btn-outline-secondary disabled" tabindex="-1" aria-disabled="true"';
          return `
          <tr>
            <td>
              <div class="manager-user">
                <span class="manager-user-badge">${escapeHtml(initial)}</span>
                <div>
                  <div class="fw-semibold">${escapeHtml(displayName)}</div>
                  <div class="small text-muted">${escapeHtml(user.username || "-")}</div>
                </div>
              </div>
            </td>
            <td>${escapeHtml(user.email || "-")}</td>
            <td>${escapeHtml(createdAt)}</td>
            <td>
              <a href="${profileLink}" ${actionAttrs} aria-label="${dashboardLiteral("مراسلة المشرف")}">
                <i class="bi bi-envelope"></i>
              </a>
            </td>
          </tr>
        `;
        })
        .join("")
    );
    return;
  }

  tableBody.innerHTML = dashboardTemplate(
    users
      .map((user) => {
        const displayName = user.full_name || user.username || "-";
        const initial = getNameInitial(displayName);
        const phone = user.phone_number || user.phone || "-";
        const childrenCount = Number.isFinite(Number(user.children_count))
          ? formatNumber(user.children_count)
          : "-";
        const userId = user.id != null ? String(user.id) : "";
        const profileLink = userId
          ? `/communication/messages?recipient=${encodeURIComponent(userId)}`
          : "#";
        const actionAttrs = userId
          ? 'class="btn btn-sm btn-outline-primary"'
          : 'class="btn btn-sm btn-outline-secondary disabled" tabindex="-1" aria-disabled="true"';

        return `
        <tr>
          <td>
            <div class="manager-user">
              <span class="manager-user-badge">${escapeHtml(initial)}</span>
              <span class="fw-semibold">${escapeHtml(displayName)}</span>
            </div>
          </td>
          <td>${escapeHtml(user.username || "-")}</td>
          <td>${escapeHtml(phone)}</td>
          <td>${escapeHtml(childrenCount)}</td>
          <td>
            <a href="${profileLink}" ${actionAttrs} aria-label="${dashboardLiteral("مراسلة ولي الأمر")}">
              <i class="bi bi-envelope"></i>
            </a>
          </td>
        </tr>
      `;
      })
      .join("")
  );
}

async function loadManagerAccounts() {
  const [supervisorsResult, parentsResult] = await Promise.allSettled([
    dashboardFetch(DASHBOARD_API.manager.supervisors),
    dashboardFetch(DASHBOARD_API.manager.parents),
  ]);

  if (supervisorsResult.status === "fulfilled") {
    const supervisorsRaw =
      supervisorsResult.value?.users ||
      supervisorsResult.value?.items ||
      supervisorsResult.value ||
      [];
    const supervisors = Array.isArray(supervisorsRaw) ? supervisorsRaw : [];
    renderManagerUsersTable("supervisorsTable", supervisors, "supervisor");
  } else {
    console.error("Error loading supervisors table:", supervisorsResult.reason);
    renderManagerUsersTable("supervisorsTable", [], "supervisor");
  }

  if (parentsResult.status === "fulfilled") {
    const parentsRaw =
      parentsResult.value?.users || parentsResult.value?.items || parentsResult.value || [];
    const parents = Array.isArray(parentsRaw) ? parentsRaw : [];
    DASHBOARD_STATE.managerSummary.parents = parents.length;
    renderManagerUsersTable("parentsTable", parents, "parent");
  } else {
    console.error("Error loading parents table:", parentsResult.reason);
    DASHBOARD_STATE.managerSummary.parents = 0;
    renderManagerUsersTable("parentsTable", [], "parent");
  }
}

async function loadClasses() {
  const tableBody = document.getElementById("classesTable");
  const overviewTableBodies = Array.from(document.querySelectorAll("#classOverviewTable"));
  const hasOverviewTables = overviewTableBodies.length > 0;
  if (!tableBody && !hasOverviewTables) return;

  try {
    const data = await dashboardFetch(DASHBOARD_API.manager.classes);
    const classes = data.classes || data.items || data || [];

    if (!Array.isArray(classes) || classes.length === 0) {
      if (tableBody) {
        tableBody.innerHTML = dashboardTemplate(
          '<tr><td colspan="7" class="text-center py-4 text-muted">لا توجد فصول</td></tr>'
        );
      }
      if (hasOverviewTables) {
        const emptyRow = dashboardTemplate(
          '<tr><td colspan="7" class="text-center py-4 text-muted">لا توجد بيانات فصول لعرضها</td></tr>'
        );
        overviewTableBodies.forEach((body) => {
          body.innerHTML = emptyRow;
        });
      }
      DASHBOARD_STATE.managerSummary.classes = 0;
      return;
    }

    const list = Array.isArray(classes) ? classes : [];
    DASHBOARD_STATE.managerSummary.classes = list.length;

    if (tableBody) {
      tableBody.innerHTML = dashboardTemplate(
        list
          .map((cls) => {
            const classId = cls.id != null ? cls.id : cls.class_id;
            const className = cls.name_ar || cls.name || cls.name_en || "-";
            const supervisorName = cls.supervisor_name || cls.current_supervisor?.name || "-";
            const isActive = cls.is_active == null ? true : Boolean(cls.is_active);
            const enrolled = safeNumber(cls.enrolled_count ?? cls.enrolled);
            const waitlist = safeNumber(cls.waitlist_count ?? cls.waiting_list);
            const capacityTotal = safeNumber(cls.capacity_total ?? cls.capacity);
            const utilizationPct =
              capacityTotal > 0 ? clampPercent((enrolled / capacityTotal) * 100) : 0;
            const utilizationClass = utilizationColor(utilizationPct);
            const classUrl = classId != null ? `/classes/${classId}` : "#";
            const actionAttrs =
              classId != null
                ? 'class="btn btn-sm btn-outline-primary"'
                : 'class="btn btn-sm btn-outline-secondary disabled" tabindex="-1" aria-disabled="true"';
            return `
          <tr>
            <td>${escapeHtml(className)}</td>
            <td>${escapeHtml(supervisorName)}</td>
            <td>
              <div class="manager-capacity-cell">
                <div class="manager-capacity-meta">
                  <span>${formatNumber(capacityTotal)}</span>
                  <span>${formatOneDecimal(utilizationPct)}%</span>
                </div>
                <div class="progress mt-1" role="progressbar" aria-label="${dashboardLiteral("نسبة إشغال الفصل")}"
                  aria-valuemin="0" aria-valuemax="100" aria-valuenow="${formatOneDecimal(utilizationPct)}">
                  <div class="progress-bar bg-${utilizationClass}" style="width:${utilizationPct}%"></div>
                </div>
              </div>
            </td>
            <td>${formatNumber(enrolled)}</td>
            <td>${formatNumber(waitlist)}</td>
            <td><span class="badge bg-${isActive ? "success" : "secondary"}">${isActive ? dashboardLiteral("نشط") : dashboardLiteral("غير نشط")}</span></td>
            <td>
              <a href="${classUrl}" ${actionAttrs} aria-label="${dashboardLiteral("عرض الفصل")}">
                <i class="bi bi-eye"></i>
              </a>
            </td>
          </tr>
        `;
          })
          .join("")
      );
    }

    if (hasOverviewTables) {
      const overviewHtml = dashboardTemplate(
        list
          .map((cls) => {
            const classId = cls.id != null ? cls.id : cls.class_id;
            const className = cls.name_ar || cls.name || cls.name_en || "-";
            const isActive = cls.is_active == null ? true : Boolean(cls.is_active);
            const capacity = cls.capacity_total ?? cls.capacity;
            const present = cls.attendance_today ?? cls.present_count ?? null;
            const absent = cls.absent_today ?? cls.absent_count ?? null;
            const pendingReports = cls.pending_reports ?? cls.pending_reports_count ?? null;
            const classUrl = classId != null ? `/classes/${classId}` : "#";
            const actionAttrs =
              classId != null
                ? 'class="btn btn-sm btn-outline-primary"'
                : 'class="btn btn-sm btn-outline-secondary disabled" tabindex="-1" aria-disabled="true"';
            return `
            <tr>
              <td>${escapeHtml(className)}</td>
              <td>${formatMaybeNumber(capacity)}</td>
              <td>${formatMaybeNumber(present)}</td>
              <td>${formatMaybeNumber(absent)}</td>
              <td>${formatMaybeNumber(pendingReports)}</td>
              <td><span class="badge bg-${isActive ? "success" : "secondary"}">${isActive ? dashboardLiteral("نشط") : dashboardLiteral("غير نشط")}</span></td>
              <td>
                <a href="${classUrl}" ${actionAttrs} aria-label="${dashboardLiteral("عرض الفصل")}">
                  <i class="bi bi-eye"></i>
                </a>
              </td>
            </tr>
          `;
          })
          .join("")
      );
      overviewTableBodies.forEach((body) => {
        body.innerHTML = overviewHtml;
      });
    }
  } catch (error) {
    console.error("Error loading classes:", error);
    if (tableBody) {
      tableBody.innerHTML = dashboardTemplate(
        '<tr><td colspan="7" class="text-center py-4 text-danger">تعذر تحميل الفصول</td></tr>'
      );
    }
    if (hasOverviewTables) {
      const errorRow = dashboardTemplate(
        '<tr><td colspan="7" class="text-center py-4 text-danger">تعذر تحميل ملخص الفصول</td></tr>'
      );
      overviewTableBodies.forEach((body) => {
        body.innerHTML = errorRow;
      });
    }
    DASHBOARD_STATE.managerSummary.classes = 0;
  }
}

async function loadSubmittedReports() {
  const tableBody = document.getElementById("reportsTable");
  if (!tableBody) return;

  try {
    const data = await dashboardFetch(DASHBOARD_API.manager.reports);
    const reports = data.reports || data.items || data || [];
    const reportList = Array.isArray(reports) ? reports : [];
    DASHBOARD_STATE.managerSummary.pendingReports = reportList.length;

    if (reportList.length === 0) {
      tableBody.innerHTML = dashboardTemplate(
        '<tr><td colspan="5" class="text-center py-4 text-muted">لا توجد تقارير معلقة</td></tr>'
      );
      return;
    }

    tableBody.innerHTML = dashboardTemplate(
      reportList
        .slice(0, 10)
        .map((report) => {
          const dateText = formatLocalizedDate(report.date);
          const submitterName = report.supervisor_name || report.submitted_by || "-";
          const daysSince = getDaysSinceDate(report.date);
          const relativeText =
            daysSince == null
              ? dashboardLiteral("تاريخ غير محدد")
              : daysSince === 0
                ? dashboardLiteral("اليوم")
                : daysSince === 1
                  ? dashboardLiteral("أمس")
                  : dashboardCurrentLang() === "en"
                    ? `${formatNumber(daysSince)} day(s) ago`
                    : `${dashboardText("dashboard.time.ago_prefix", "منذ", "ago")} ${formatNumber(daysSince)} ${dashboardText("dashboard.priority.day", "يوم", "day(s)")}`;
          const priority = reportPriorityMeta(report.date);
          return `
          <tr>
            <td>${escapeHtml(report.child_name || "-")}</td>
            <td>
              <div>${escapeHtml(dateText)}</div>
              <div class="small text-muted">${escapeHtml(relativeText)}</div>
            </td>
            <td>${escapeHtml(submitterName)}</td>
            <td>
              <span class="badge bg-warning">${dashboardLiteral("بانتظار المراجعة")}</span>
              <div class="manager-report-priority ${priority.levelClass}">
                <i class="bi bi-clock-history"></i>
                <span>${escapeHtml(priority.label)}</span>
              </div>
            </td>
            <td>
              <a href="/reports/${report.id}" class="btn btn-sm btn-outline-primary" aria-label="${dashboardLiteral("عرض التقرير")}">
                <i class="bi bi-eye"></i>
              </a>
            </td>
          </tr>
        `;
        })
        .join("")
    );
  } catch (error) {
    console.error("Error loading reports:", error);
    DASHBOARD_STATE.managerSummary.pendingReports = 0;
    tableBody.innerHTML = dashboardTemplate(
      '<tr><td colspan="5" class="text-center py-4 text-danger">تعذر تحميل التقارير</td></tr>'
    );
  }
}

async function loadSupervisorStats() {
  const container = document.getElementById("supervisorStatsContainer");
  if (!container) return;

  try {
    const data = await dashboardFetch(DASHBOARD_API.manager.supervisors);
    const supervisors = data.users || data.items || data || [];
    const all = Array.isArray(supervisors) ? supervisors : [];
    const active = all.filter((s) => safeRoleValue(s.status) === "ACTIVE").length;
    const inactive = Math.max(all.length - active, 0);
    const activeRate = all.length > 0 ? (active / all.length) * 100 : 0;
    const inactiveRate = Math.max(100 - activeRate, 0);

    container.innerHTML = dashboardTemplate(`
      <div class="row g-3 manager-stats-grid">
        <div class="col-md-4">
          <div class="card border-0 bg-primary-subtle h-100">
            <div class="card-body">
              <div class="small text-primary mb-1">إجمالي المشرفين</div>
              <h3 class="fw-bold mb-0">${formatNumber(all.length)}</h3>
              <div class="small text-muted mt-2">النطاق الإداري الحالي</div>
            </div>
          </div>
        </div>
        <div class="col-md-4">
          <div class="card border-0 bg-success-subtle h-100">
            <div class="card-body">
              <div class="small text-success mb-1">المشرفون النشطون</div>
              <h3 class="fw-bold mb-0">${formatNumber(active)}</h3>
              <div class="small text-muted mt-1">${formatOneDecimal(activeRate)}% من إجمالي المشرفين</div>
              <div class="progress manager-stats-progress mt-2" role="progressbar" aria-label="معدل نشاط المشرفين"
                aria-valuemin="0" aria-valuemax="100" aria-valuenow="${formatOneDecimal(activeRate)}">
                <div class="progress-bar bg-success" style="width:${clampPercent(activeRate)}%"></div>
              </div>
            </div>
          </div>
        </div>
        <div class="col-md-4">
          <div class="card border-0 bg-secondary-subtle h-100">
            <div class="card-body">
              <div class="small text-secondary mb-1">المشرفون غير النشطين</div>
              <h3 class="fw-bold mb-0">${formatNumber(inactive)}</h3>
              <div class="small text-muted mt-1">${formatOneDecimal(inactiveRate)}% من إجمالي المشرفين</div>
              <div class="progress manager-stats-progress mt-2" role="progressbar" aria-label="معدل عدم النشاط"
                aria-valuemin="0" aria-valuemax="100" aria-valuenow="${formatOneDecimal(inactiveRate)}">
                <div class="progress-bar bg-secondary" style="width:${clampPercent(inactiveRate)}%"></div>
              </div>
            </div>
          </div>
        </div>
      </div>
    `);
    DASHBOARD_STATE.managerSummary.activeSupervisors = active;
  } catch (error) {
    console.error("Error loading supervisor stats:", error);
    DASHBOARD_STATE.managerSummary.activeSupervisors = 0;
    container.innerHTML = dashboardTemplate(
      '<p class="text-muted mb-0">غير متاح حالياً</p>'
    );
  }
}

function renderAdminSummaryCards(summary) {
  const attendanceToday = safeNumber(summary.attendance_today);
  const pendingApplications = safeNumber(summary.pending_applications);
  const pendingReports = safeNumber(summary.pending_daily_reports);
  const recentIncidents = safeNumber(summary.recent_incidents);
  const attendanceRate = safeNumber(summary.attendance_rate);

  updateElementText("presentTodayValue", formatNumber(attendanceToday));
  updateElementText("pendingEnrollmentsValue", formatNumber(pendingApplications));
  updateElementText("pendingReportsValue", formatNumber(pendingReports));
  updateElementText("incidentsTodayValue", formatNumber(recentIncidents));

  const progress = document.getElementById("attendanceProgressBar") ||
    document.querySelector("#attendanceCard .progress-bar");
  if (progress) {
    const pct = clampPercent(attendanceRate);
    progress.style.width = `${pct}%`;
    progress.setAttribute("aria-valuenow", String(pct));
    progress.className = `progress-bar ${pct >= 85 ? "bg-success" : pct >= 70 ? "bg-warning" : "bg-danger"}`;
  }

  const attendanceRateText = document.getElementById("attendanceRateText");
  if (attendanceRateText) {
    const isEn = dashboardCurrentLang() === "en";
    if (attendanceToday === 0) {
      attendanceRateText.innerHTML = `<i class="bi bi-bell me-1"></i>` + (isEn
        ? "No attendance recorded yet today — send reminders to kindergartens."
        : "لم يُسجَّل حضور اليوم بعد — أرسل تذكيرات للروضات.");
    } else {
      attendanceRateText.textContent = isEn
        ? `${formatOneDecimal(attendanceRate)}% attendance rate today`
        : `نسبة الحضور اليوم: ${formatOneDecimal(attendanceRate)}%`;
    }
  }

  const attendanceBadge = document.getElementById("attendanceBadge");
  if (attendanceBadge) {
    if (attendanceToday === 0) {
      attendanceBadge.style.background = "#fef3c7";
      attendanceBadge.style.color = "#b45309";
      attendanceBadge.textContent = dashboardCurrentLang() === "en" ? "No data yet" : "لا توجد بيانات بعد";
    } else if (attendanceRate >= 85) {
      attendanceBadge.style.background = "#d1fae5";
      attendanceBadge.style.color = "#047857";
      attendanceBadge.textContent = dashboardCurrentLang() === "en" ? "On track" : "مؤشر إيجابي";
    } else if (attendanceRate >= 70) {
      attendanceBadge.style.background = "#fef3c7";
      attendanceBadge.style.color = "#b45309";
      attendanceBadge.textContent = dashboardCurrentLang() === "en" ? "Below average" : "دون المتوسط";
    } else {
      attendanceBadge.style.background = "#fee2e2";
      attendanceBadge.style.color = "#b91c1c";
      attendanceBadge.textContent = dashboardCurrentLang() === "en" ? "Critical" : "حرج";
    }
  }

  const attendanceLastUpdate = document.getElementById("attendanceLastUpdate");
  if (attendanceLastUpdate) {
    const now = new Date();
    attendanceLastUpdate.textContent = now.toLocaleTimeString(
      dashboardCurrentLang() === "en" ? "en-US" : "ar-JO",
      { hour: "2-digit", minute: "2-digit" }
    );
  }

  const pendingBadge = document.getElementById("pendingEnrollmentsBadge");
  if (pendingBadge) {
    if (pendingApplications === 0) {
      pendingBadge.className = "badge bg-success-subtle text-success rounded-pill px-3";
      pendingBadge.textContent = dashboardLiteral("لا توجد طلبات");
    } else if (pendingApplications > 10) {
      pendingBadge.className = "badge bg-danger-subtle text-danger rounded-pill px-3";
      pendingBadge.textContent = dashboardLiteral("إجراء فوري");
    } else {
      pendingBadge.className = "badge bg-warning-subtle text-warning rounded-pill px-3";
      pendingBadge.textContent = dashboardLiteral("تحتاج متابعة");
    }
  }

  const incidentsBadge = document.getElementById("incidentsBadge");
  if (incidentsBadge) {
    if (recentIncidents === 0) {
      incidentsBadge.className = "badge bg-success-subtle text-success rounded-pill px-3";
      incidentsBadge.textContent = dashboardLiteral("مستقر");
    } else if (recentIncidents >= 5) {
      incidentsBadge.className = "badge bg-danger-subtle text-danger rounded-pill px-3";
      incidentsBadge.textContent = dashboardLiteral("حرج");
    } else {
      incidentsBadge.className = "badge bg-warning-subtle text-warning rounded-pill px-3";
      incidentsBadge.textContent = dashboardLiteral("تحت المراقبة");
    }
  }
}

function renderAdminSystemOverview(overview) {
  const totalKindergartens = safeNumber(overview.total_kindergartens);
  const activeKindergartens = safeNumber(overview.active_kindergartens);
  const totalUsers = safeNumber(overview.total_users);

  updateElementText("totalKindergartens", formatNumber(totalKindergartens));
  updateElementText("activeKindergartens", formatNumber(activeKindergartens));
  updateElementText("totalUsers", formatNumber(totalUsers));

  const health = document.getElementById("systemHealth");
  if (health) {
    health.querySelectorAll(".kj-stat-pending").forEach((el) => el.remove());
    const activeRate =
      totalKindergartens > 0 ? (activeKindergartens / totalKindergartens) * 100 : 0;
    if (activeRate >= 90) health.textContent = dashboardLiteral("ممتاز");
    else if (activeRate >= 75) health.textContent = dashboardLiteral("جيد");
    else if (activeRate >= 50) health.textContent = dashboardLiteral("متوسط");
    else health.textContent = dashboardLiteral("حرج");
  }
}

function renderAdminKindergartensTable(kindergartens) {
  const tableBody = document.getElementById("kindergartensOverviewTable");
  if (!tableBody) return;

  if (!Array.isArray(kindergartens) || kindergartens.length === 0) {
    tableBody.innerHTML = dashboardTemplate(
      '<tr><td colspan="8" class="text-center py-4 text-muted">لا توجد روضات</td></tr>'
    );
    return;
  }

  tableBody.innerHTML = dashboardTemplate(
    kindergartens
      .map((kg) => {
        const statusClass =
          String(kg.status || "").toUpperCase() === "ACTIVE" ? "success" : "secondary";
        const license = String(kg.license_status || "unknown").toLowerCase();
        const licenseClass =
          license === "valid" ? "success" : license === "expiring_soon" ? "warning" : "danger";
        const licenseText =
          license === "valid"
            ? dashboardLiteral("ساري")
            : license === "expiring_soon"
              ? dashboardLiteral("قارب على الانتهاء")
              : dashboardLiteral("منتهي");

        // Row risk coloring: high = license expired or over capacity, medium = expiring or pending reports, low = all good
        const capUtil = parseFloat(kg.capacity_utilization || 0);
        const rowRisk = license === "expired" || capUtil > 100
          ? "row-risk-high"
          : license === "expiring_soon" || safeNumber(kg.pending_reports) > 0
          ? "row-risk-medium"
          : "";

        return `
        <tr class="${rowRisk}">
          <td>${escapeHtml(kg.name_ar || kg.name_en || "-")}</td>
          <td><span class="badge bg-${statusClass}">${statusLabel(kg.status)}</span></td>
          <td>${formatNumber(kg.enrollments || 0)}</td>
          <td>${formatNumber(kg.attendance_today || 0)}</td>
          <td>${formatNumber(kg.pending_reports || 0)}</td>
          <td class="${capUtil > 100 ? "text-danger fw-bold" : capUtil > 85 ? "text-warning fw-semibold" : ""}">${formatOneDecimal(capUtil)}%</td>
          <td><span class="badge bg-${licenseClass}">${licenseText}</span></td>
          <td>
            <a href="/kindergartens/${kg.id}" class="btn btn-sm btn-outline-primary" aria-label="${dashboardLiteral("عرض الروضة")}">
              <i class="bi bi-eye"></i>
            </a>
          </td>
        </tr>
      `;
      })
      .join("")
  );
}

function setPendingReportsBadge(value) {
  updateElementText("pendingReportsListBadge", formatNumber(value));
}

function renderPendingReportsList(kindergartens, summary) {
  const list = document.getElementById("pendingReportsList");
  if (!list) return;

  const totalFromSummary = safeNumber(summary.pending_daily_reports);
  setPendingReportsBadge(totalFromSummary);

  if (!Array.isArray(kindergartens)) {
    list.innerHTML = dashboardTemplate(
      '<div class="text-center py-4 text-muted">لا توجد بيانات</div>'
    );
    return;
  }

  const rows = kindergartens
    .filter((kg) => safeNumber(kg.pending_reports) > 0)
    .sort((a, b) => safeNumber(b.pending_reports) - safeNumber(a.pending_reports))
    .slice(0, 6);

  if (rows.length === 0) {
    list.innerHTML = dashboardTemplate(`
      <div class="text-center py-4 text-muted">
        <i class="bi bi-check-circle fs-1 d-block mb-2 opacity-25"></i>
        <span>لا توجد تقارير معلقة</span>
      </div>
    `);
    return;
  }

  list.innerHTML = dashboardTemplate(
    rows
      .map((kg) => {
        return `
        <a href="/daily-reports" class="list-group-item list-group-item-action">
          <div class="d-flex justify-content-between align-items-center">
            <div>
              <div class="fw-semibold">${escapeHtml(kg.name_ar || kg.name_en || "-")}</div>
              <small class="text-muted">${dashboardLiteral("بانتظار المراجعة")}</small>
            </div>
            <span class="badge bg-warning rounded-pill">${formatNumber(kg.pending_reports || 0)}</span>
          </div>
        </a>
      `;
      })
      .join("")
  );
}

function translateAlertType(rawType) {
  const key = String(rawType || "")
    .trim()
    .toLowerCase();
  const labels = {
    alert: dashboardLiteral("تنبيه"),
    license_expiry: dashboardLiteral("انتهاء الترخيص"),
    high_pending_applications: dashboardLiteral("طلبات تسجيل معلقة"),
    low_attendance: dashboardLiteral("انخفاض الحضور"),
    high_incidents: dashboardLiteral("ارتفاع الحوادث"),
    applications: dashboardLiteral("طلبات التسجيل"),
    safety: dashboardLiteral("السلامة"),
    license: dashboardLiteral("الترخيص"),
    compliance: dashboardLiteral("الامتثال"),
  };
  return labels[key] || dashboardLiteral("تنبيه");
}

function normalizeAlertPriority(rawPriority, rawSeverity) {
  const priority = String(rawPriority || "")
    .trim()
    .toLowerCase();
  if (priority) return priority;

  const severity = String(rawSeverity || "")
    .trim()
    .toLowerCase();
  if (severity === "critical") return "critical";
  if (severity === "error" || severity === "high") return "high";
  if (severity === "warning") return "medium";
  return "low";
}

function normalizeAlerts(alerts) {
  if (!Array.isArray(alerts)) return [];
  return alerts.map((alert, index) => {
    const resolvedType = alert.title || alert.type || dashboardLiteral("تنبيه");
    const resolvedPriority = normalizeAlertPriority(alert.priority, alert.severity);
    return {
      id: alert.id || `${alert.type || "alert"}-${index}`,
      type: translateAlertType(resolvedType),
      message: String(
        alert.message || alert.details || dashboardLiteral("لا توجد تفاصيل متاحة.")
      ),
      priority: resolvedPriority,
      kindergartenId: alert.kindergarten_id || alert.entity_id || alert.kindergartenId || null,
    };
  });
}

function _getDismissedAlertIds() {
  try {
    return JSON.parse(localStorage.getItem("kinjo_dismissed_alerts") || "[]");
  } catch (_) {
    return [];
  }
}

function _saveDismissedAlertId(alertId) {
  try {
    const ids = _getDismissedAlertIds();
    if (!ids.includes(String(alertId))) ids.push(String(alertId));
    localStorage.setItem("kinjo_dismissed_alerts", JSON.stringify(ids.slice(-200)));
  } catch (_) {}
}

function dismissAlertItem(btn, alertId) {
  _saveDismissedAlertId(alertId);
  const item = btn.closest(".dfe-alert-item");
  if (!item) return;
  item.classList.add("dismissed");
  item.addEventListener("transitionend", function handler() {
    item.removeEventListener("transitionend", handler);
    item.remove();
    const container = document.getElementById("alertsContainer");
    const remaining = container ? container.querySelectorAll(".dfe-alert-item").length : 0;
    const badge = document.getElementById("alertCountBadge");
    if (badge) {
      badge.textContent = remaining;
      badge.style.display = remaining > 0 ? "" : "none";
    }
    updateElementText("alertCount", String(remaining));
    if (remaining === 0) {
      const allClear = document.getElementById("alertsAllClear");
      if (allClear) allClear.style.display = "";
    }
  });
}

function renderAlerts(rawAlerts) {
  const dismissedIds = _getDismissedAlertIds();
  const alerts = normalizeAlerts(rawAlerts).filter(function (a) {
    return !dismissedIds.includes(String(a.id));
  });
  const container = document.getElementById("alertsContainer");
  const allClear = document.getElementById("alertsAllClear");
  const badge = document.getElementById("alertCountBadge");

  updateElementText("alertCount", String(alerts.length));

  if (!container) return;

  // Update counter badge
  if (badge) {
    badge.textContent = alerts.length;
    badge.style.display = alerts.length > 0 ? "" : "none";
  }

  if (alerts.length === 0) {
    if (allClear) allClear.style.display = "";
    // Clear any old alert items but keep allClear
    Array.from(container.children).forEach(function (el) {
      if (el.id !== "alertsAllClear") el.remove();
    });
    return;
  }

  // Hide all-clear, show real alerts
  if (allClear) allClear.style.display = "none";

  const severityColor = {
    critical: "#dc3545",
    high:     "#f59e0b",
    medium:   "#2F7D62",
    low:      "#64748b",
  };
  const severityIcon = {
    critical: "bi-exclamation-circle-fill",
    high:     "bi-exclamation-triangle-fill",
    medium:   "bi-info-circle-fill",
    low:      "bi-bell-fill",
  };
  const priorityClass = {
    critical: "danger",
    high:     "warning",
    medium:   "info",
    low:      "secondary",
  };

  // Remove old alert items (keep allClear)
  Array.from(container.children).forEach(function (el) {
    if (el.id !== "alertsAllClear") el.remove();
  });

  alerts.forEach(function (alert) {
    const klass = priorityClass[alert.priority] || "secondary";
    const color = severityColor[alert.priority] || "#64748b";
    const icon = severityIcon[alert.priority] || "bi-bell-fill";
    const actionUrl = alert.kindergartenId
      ? `/kindergartens/${alert.kindergartenId}`
      : "/dashboard";
    const item = document.createElement("div");
    item.className = "dfe-alert-item";
    item.style.setProperty("--sev-color", color);
    item.innerHTML = `
      <div class="dfe-alert-icon"><i class="bi ${icon}"></i></div>
      <div class="dfe-alert-body">
        <div class="dfe-alert-name">${escapeHtml(alert.type)}</div>
        <div class="dfe-alert-desc">${escapeHtml(alert.message)}</div>
      </div>
      <div class="dfe-alert-btns">
        <a href="${actionUrl}" class="dfe-alert-btn view">
          ${dashboardCurrentLang && dashboardCurrentLang() === "en" ? "View" : "فتح"}
        </a>
        <button class="dfe-alert-btn dismiss" onclick="dismissAlertItem(this, '${escapeHtml(String(alert.id))}')" type="button">
          ${dashboardCurrentLang && dashboardCurrentLang() === "en" ? "Dismiss" : "تجاهل"}
        </button>
      </div>`;
    container.appendChild(item);
  });
}

function destroyChartInstance(chartInstance) {
  if (chartInstance && typeof chartInstance.destroy === "function") {
    chartInstance.destroy();
  }
}

const NO_DATA_CHART_PLUGIN = {
  id: "dashboardNoDataOverlay",
  afterDraw(chart, _args, options) {
    const dataset = chart?.data?.datasets?.[0]?.data || [];
    const hasData = dataset.some((value) => safeNumber(value) > 0);
    if (hasData) return;

    const area = chart.chartArea;
    if (!area) return;

    const ctx = chart.ctx;
    ctx.save();
    ctx.fillStyle = "#6c757d";
    ctx.font = '13px "Segoe UI", Tahoma, sans-serif';
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillText(
      options?.message || dashboardLiteral("لا توجد بيانات متاحة"),
      (area.left + area.right) / 2,
      (area.top + area.bottom) / 2
    );
    ctx.restore();
  },
};

const DOUGHNUT_SUMMARY_PLUGIN = {
  id: "dashboardDoughnutSummary",
  afterDraw(chart, _args, options) {
    if (chart?.config?.type !== "doughnut") return;
    const dataset = chart?.data?.datasets?.[0]?.data || [];
    const total = dataset.reduce((sum, value) => sum + safeNumber(value), 0);
    if (!total) return;

    const metaPoint = chart.getDatasetMeta(0)?.data?.[0];
    const centerX = metaPoint?.x;
    const centerY = metaPoint?.y;
    if (!Number.isFinite(centerX) || !Number.isFinite(centerY)) return;

    const ctx = chart.ctx;
    ctx.save();
    ctx.textAlign = "center";
    ctx.fillStyle = "#1f2937";
    ctx.font = '700 17px "Segoe UI", Tahoma, sans-serif';
    ctx.fillText(total.toLocaleString(dashboardCurrentLocale()), centerX, centerY - 2);
    ctx.fillStyle = "#6c757d";
    ctx.font = '12px "Segoe UI", Tahoma, sans-serif';
    ctx.fillText(
      options?.label || dashboardLiteral("إجمالي الحالات"),
      centerX,
      centerY + 15
    );
    ctx.restore();
  },
};

function renderAttendanceChart(series) {
  const canvas = document.getElementById("attendanceChart");
  if (!canvas || typeof Chart === "undefined") return;

  const list = Array.isArray(series) ? series : [];
  const labels = list.map((item) => formatDateLabel(item.date || item.label));
  const values = list.map((item) => safeNumber(item.count ?? item.value));

  DASHBOARD_STATE.attendanceSeries = list;
  const chartType = DASHBOARD_STATE.attendanceChartType === "bar" ? "bar" : "line";
  const context = canvas.getContext("2d");
  const areaGradient = context
    ? (() => {
        const gradient = context.createLinearGradient(0, 0, 0, 260);
        gradient.addColorStop(0, "rgba(31, 94, 71, 0.30)");
        gradient.addColorStop(1, "rgba(31, 94, 71, 0.02)");
        return gradient;
      })()
    : "rgba(31, 94, 71, 0.15)";

  destroyChartInstance(DASHBOARD_STATE.attendanceChart);
  DASHBOARD_STATE.attendanceChart = new Chart(canvas, {
    type: chartType,
    plugins: [NO_DATA_CHART_PLUGIN],
    data: {
      labels: labels.length > 0 ? labels : [dashboardLiteral("لا توجد بيانات")],
      datasets: [
        {
          label: dashboardLiteral("الحضور"),
          data: values.length > 0 ? values : [0],
          fill: chartType === "line",
          borderColor: "#1F5E47",
          backgroundColor: chartType === "line" ? areaGradient : "rgba(31, 94, 71, 0.45)",
          borderWidth: chartType === "line" ? 2.5 : 1,
          tension: 0.35,
          pointRadius: chartType === "line" ? 3.5 : 0,
          pointHoverRadius: chartType === "line" ? 5 : 0,
          pointBackgroundColor: "#1F5E47",
          borderRadius: chartType === "bar" ? 8 : 0,
          maxBarThickness: chartType === "bar" ? 36 : undefined,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: { duration: 550, easing: "easeOutQuart" },
      interaction: {
        mode: "index",
        intersect: false,
      },
      plugins: {
        legend: { display: false },
        dashboardNoDataOverlay: {
          message: dashboardLiteral(
            "لا توجد بيانات حضور ضمن الفترة المختارة"
          ),
        },
        tooltip: {
          backgroundColor: "rgba(17, 24, 39, 0.92)",
          titleColor: "#f8fafc",
          bodyColor: "#f8fafc",
          padding: 10,
          callbacks: {
            title(items) {
              return items?.[0]?.label || "";
            },
            label(context) {
              const value = safeNumber(context.parsed?.y ?? context.parsed);
              return `${dashboardText("dashboard.chart.attendance", "الحضور", "Attendance")}: ${value.toLocaleString(dashboardCurrentLocale())}`;
            },
          },
        },
      },
      scales: {
        x: {
          ticks: { color: "#6c757d" },
          grid: { display: false },
        },
        y: {
          beginAtZero: true,
          ticks: {
            precision: 0,
            color: "#6c757d",
            callback(value) {
              return safeNumber(value).toLocaleString(dashboardCurrentLocale());
            },
          },
          grid: { color: "rgba(108, 117, 125, 0.15)" },
        },
      },
    },
  });

  // Chart insight: compute trend from series data
  const insightEl = document.getElementById("attendanceChartInsight");
  if (insightEl && values.length >= 2) {
    const latest = values[values.length - 1];
    const prev = values[values.length - 2];
    const diff = latest - prev;
    const isEn = dashboardCurrentLang() === "en";
    let insightText = "";
    let insightIcon = "";
    let insightClass = "";
    if (diff < -2) {
      insightText = isEn
        ? `Attendance dropped ${Math.abs(diff)} this period — follow up on absences.`
        : `انخفض الحضور بمقدار ${Math.abs(diff)} في هذه الفترة — تابع حالات الغياب.`;
      insightIcon = "bi-arrow-down-right text-danger";
      insightClass = "chart-insight-warn";
    } else if (diff > 2) {
      insightText = isEn
        ? `Attendance improved by ${diff} — good progress this period.`
        : `تحسّن الحضور بمقدار ${diff} — تقدم جيد في هذه الفترة.`;
      insightIcon = "bi-arrow-up-right text-success";
      insightClass = "chart-insight-good";
    } else {
      insightText = isEn
        ? "Attendance is stable compared to the previous period."
        : "الحضور مستقر مقارنةً بالفترة السابقة.";
      insightIcon = "bi-dash-circle text-muted";
      insightClass = "";
    }
    insightEl.className = `chart-insight ${insightClass}`;
    insightEl.innerHTML = `<i class="bi ${insightIcon} me-1"></i>${insightText}`;
  } else if (insightEl) {
    insightEl.innerHTML = "";
  }
}

function renderEnrollmentChart(enrollmentMap) {
  const canvas = document.getElementById("enrollmentPieChart");
  if (!canvas || typeof Chart === "undefined") return;

  const map = enrollmentMap && typeof enrollmentMap === "object" ? enrollmentMap : {};
  const entries = Object.entries(map);
  const labels = entries.map(([status]) => statusLabel(status));
  const values = entries.map(([, count]) => safeNumber(count));
  const hasData = values.some((value) => value > 0);

  destroyChartInstance(DASHBOARD_STATE.enrollmentChart);
  DASHBOARD_STATE.enrollmentChart = new Chart(canvas, {
    type: "doughnut",
    plugins: [NO_DATA_CHART_PLUGIN, DOUGHNUT_SUMMARY_PLUGIN],
    data: {
      labels: hasData ? labels : [dashboardLiteral("لا توجد بيانات")],
      datasets: [
        {
          data: hasData ? values : [0],
          backgroundColor: hasData
            ? ["#1F5E47", "#10b981", "#f59e0b", "#ef4444", "#64748b", "#2F7D62"]
            : ["#dee2e6"],
          borderWidth: 2,
          borderColor: "#ffffff",
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      cutout: "68%",
      animation: { duration: 650, easing: "easeOutQuart" },
      plugins: {
        dashboardNoDataOverlay: {
          message: dashboardLiteral("لا توجد حالات تسجيل متاحة"),
        },
        dashboardDoughnutSummary: { label: dashboardLiteral("إجمالي الحالات") },
        legend: {
          position: "bottom",
          labels: {
            usePointStyle: true,
            boxWidth: 10,
            boxHeight: 10,
            padding: 14,
          },
        },
        tooltip: {
          backgroundColor: "rgba(17, 24, 39, 0.92)",
          titleColor: "#f8fafc",
          bodyColor: "#f8fafc",
          padding: 10,
          callbacks: {
            label(context) {
              const dataset = context.dataset?.data || [];
              const total = dataset.reduce((sum, item) => sum + safeNumber(item), 0);
              const value = safeNumber(context.parsed);
              const percentage = total > 0 ? (value / total) * 100 : 0;
              return `${context.label}: ${value.toLocaleString(dashboardCurrentLocale())} (${percentage.toFixed(1)}%)`;
            },
          },
        },
      },
    },
  });

  // Enrollment chart insight
  const enrollInsight = document.getElementById("enrollmentChartInsight");
  if (enrollInsight && hasData) {
    const isEn = dashboardCurrentLang() === "en";
    const total = values.reduce((a, b) => a + b, 0);
    const pendingIdx = labels.findIndex((l) => /pending|انتظار/i.test(l));
    const pending = pendingIdx >= 0 ? values[pendingIdx] : 0;
    const pendingPct = total > 0 ? ((pending / total) * 100).toFixed(0) : 0;
    if (pending > 0) {
      enrollInsight.className = "chart-insight chart-insight-warn";
      enrollInsight.innerHTML = `<i class="bi bi-hourglass-split text-warning me-1"></i>` + (isEn
        ? `${pendingPct}% of applications (${pending}) are pending review.`
        : `${pendingPct}% من الطلبات (${pending}) بانتظار المراجعة.`);
    } else {
      enrollInsight.className = "chart-insight chart-insight-good";
      enrollInsight.innerHTML = `<i class="bi bi-check-circle text-success me-1"></i>` + (isEn
        ? "All enrollment requests have been processed."
        : "تمت معالجة جميع طلبات التسجيل.");
    }
  } else if (enrollInsight) {
    enrollInsight.innerHTML = "";
  }
}

function bindChartTypeToggles() {
  const buttons = document.querySelectorAll("[data-chart-type]");
  if (!buttons.length) return;

  buttons.forEach((button) => {
    button.addEventListener("click", (event) => {
      const selectedType = event.currentTarget?.dataset?.chartType;
      if (!selectedType || !["line", "bar"].includes(selectedType)) return;

      DASHBOARD_STATE.attendanceChartType = selectedType;
      buttons.forEach((btn) => btn.classList.remove("active"));
      event.currentTarget.classList.add("active");
      renderAttendanceChart(DASHBOARD_STATE.attendanceSeries || []);
    });
  });
}

function buildKpiRows(payload) {
  const rows = [];
  for (const definition of KPI_DEFINITIONS) {
    const card = payload?.[definition.key];
    if (!card || typeof card !== "object") continue;

    const value = safeNumber(card.value ?? card.current_value);
    const unit = card.unit != null ? String(card.unit) : definition.unit;
    // quality.has_data === false means the backend cannot reliably compute this KPI
    const qualityMeta = payload?.quality?.[definition.key];
    const hasData = qualityMeta?.has_data !== false;
    const band = hasData
      ? normalizeBand(card.band || card.rating || card.status) || inferBand(definition.key, value)
      : "insufficient";
    const trend = normalizeTrend(card.trend_indicator || card.trend);
    const explanation = card.explanation?.ar || card.explanation?.en || card.tooltip || "";
    const managerNote = card.manager_note?.ar || card.manager_note?.en || "";
    const actions = Array.isArray(card.action_items) ? card.action_items : [];

    rows.push({
      key: definition.key,
      label: typeof definition.label === "function" ? definition.label() : definition.label,
      value,
      unit,
      band,
      trend,
      explanation,
      managerNote,
      actions,
      confidence: card.confidence || null,
      numerator: card.numerator != null ? card.numerator : null,
      denominator: card.denominator != null ? card.denominator : null,
      meaning: card.meaning_ar || card.meaning_en || null,
      decisionGuidance: card.decision_guidance_ar || card.decision_guidance_en || null,
    });
  }
  return rows;
}

function renderKpiCards(kpis) {
  const container = document.getElementById("kpiCardsContainer");
  if (!container) return;

  if (!Array.isArray(kpis) || kpis.length === 0) {
    container.innerHTML = dashboardTemplate(
      '<div class="col-12 text-center py-4 text-muted">لا توجد بيانات مؤشرات حالياً</div>'
    );
    return;
  }

  container.innerHTML = dashboardTemplate(
    kpis
      .map((kpi) => {
        const color = BAND_BOOTSTRAP[kpi.band] || "secondary";
        const bandText = (BAND_LABEL[kpi.band] || BAND_LABEL.neutral)();
        const formattedValue = Number.isFinite(kpi.value) ? formatOneDecimal(kpi.value) : "--";
        const unit = kpi.unit || "";
        const hasActions = Array.isArray(kpi.actions) && kpi.actions.length > 0;

        const confIcon = kpi.confidence === "high" ? "bi-check-circle-fill text-success"
          : kpi.confidence === "medium" ? "bi-exclamation-circle-fill text-warning"
          : kpi.confidence === "low" ? "bi-exclamation-triangle-fill text-danger"
          : kpi.confidence === "insufficient" ? "bi-question-circle-fill text-secondary"
          : "";
        const confLabel = kpi.confidence === "high" ? dashboardLiteral("ثقة عالية")
          : kpi.confidence === "medium" ? dashboardLiteral("ثقة متوسطة")
          : kpi.confidence === "low" ? dashboardLiteral("عينة صغيرة")
          : kpi.confidence === "insufficient" ? dashboardLiteral("بيانات غير كافية")
          : "";
        const denomStr = (kpi.numerator != null && kpi.denominator != null && kpi.denominator > 0)
          ? `<small class="text-muted font-monospace">${Math.round(kpi.numerator)}/${Math.round(kpi.denominator)}</small>`
          : "";
        const meaningHtml = kpi.meaning
          ? `<div class="mt-1 fst-italic text-muted" style="font-size:.75rem">${escapeHtml(kpi.meaning)}</div>`
          : "";

        return `
        <div class="col-md-6 col-lg-4">
          <div class="kpi-card card border-0 shadow-sm h-100" data-status="${kpi.band}" style="border-radius: 16px;">
            <div class="card-body">
              <div class="d-flex justify-content-between align-items-start mb-2">
                <h6 class="text-muted mb-0">${escapeHtml(kpi.label)}</h6>
                <div class="d-flex align-items-center gap-1">
                  ${confIcon ? `<i class="bi ${confIcon}" title="${confLabel}" aria-hidden="true"></i>` : ""}
                  <span class="badge bg-${color}">${bandText}</span>
                </div>
              </div>
              <div class="display-6 fw-bold text-${color}">${formattedValue}<small class="fs-6 ms-1 text-muted">${escapeHtml(unit)}</small></div>
              <div class="d-flex align-items-center justify-content-between mt-1">
                <span class="text-muted small">${trendSymbol(kpi.trend)}</span>
                ${denomStr}
              </div>
              ${meaningHtml}
              ${
                hasActions
                  ? `<button type="button" class="btn btn-sm btn-outline-${color} mt-3" onclick="openKpiActionItems('${kpi.key}')">${dashboardLiteral("عرض الإجراءات")}</button>`
                  : ""
              }
            </div>
          </div>
        </div>
      `;
      })
      .join("")
  );
}

function renderKpiTable(kpis) {
  const tableBody = document.getElementById("kpiTableBody");
  if (!tableBody) return;

  if (!Array.isArray(kpis) || kpis.length === 0) {
    tableBody.innerHTML = dashboardTemplate(
      '<tr><td colspan="5" class="text-center py-4 text-muted">لا توجد بيانات مؤشرات حالياً</td></tr>'
    );
    return;
  }

  tableBody.innerHTML = dashboardTemplate(
    kpis
      .map((kpi) => {
        const color = BAND_BOOTSTRAP[kpi.band] || "secondary";
        const value = Number.isFinite(kpi.value) ? formatOneDecimal(kpi.value) : "--";
        const actionsLabel =
          Array.isArray(kpi.actions) && kpi.actions.length > 0
            ? `<button type="button" class="btn btn-sm btn-outline-${color}" onclick="openKpiActionItems('${kpi.key}')">${dashboardLiteral("إجراءات")}</button>`
            : "-";

        return `
        <tr>
          <td>${escapeHtml(kpi.label)}</td>
          <td class="fw-bold">${value}${escapeHtml(kpi.unit || "")}</td>
          <td><span class="badge bg-${color}">${(BAND_LABEL[kpi.band] || BAND_LABEL.neutral)()}</span></td>
          <td>${trendSymbol(kpi.trend)}</td>
          <td>${actionsLabel}</td>
        </tr>
      `;
      })
      .join("")
  );
}

function renderKpiStatusCounts(kpis, alertCount) {
  const excellent = kpis.filter((k) => k.band === "green").length;
  const caution = kpis.filter((k) => k.band === "amber").length;
  const critical = kpis.filter((k) => k.band === "red").length;

  updateElementText("excellentCount", String(excellent));
  updateElementText("cautionCount", String(caution));
  updateElementText("criticalCount", String(critical));

  if (typeof alertCount === "number") {
    updateElementText("alertCount", String(alertCount));
  }
}

function _kpiExplainCard(kpi, meta, now) {
  const color     = BAND_BOOTSTRAP[kpi.band] || "secondary";
  const bandText  = (BAND_LABEL[kpi.band] || BAND_LABEL.neutral)();
  const fmtVal    = Number.isFinite(kpi.value) ? formatOneDecimal(kpi.value) : "--";
  const unit      = kpi.unit || "";
  const icon      = meta ? meta.icon      : "bi-bar-chart-fill";
  const iconBg    = meta ? meta.iconBg    : "rgba(100,116,139,.1)";
  const iconColor = meta ? meta.iconColor : "#64748b";

  const thresholdPills = meta && Array.isArray(meta.thresholds)
    ? meta.thresholds.map((t) => `
        <span class="kpi-threshold-pill ${t.cls}">
          ${escapeHtml(t.label)} — ${escapeHtml(t.range)}
        </span>`).join("")
    : "";

  const actionList = kpi.actions && kpi.actions.length > 0
    ? kpi.actions.map((a) => `
        <li>
          <i class="bi bi-arrow-left-circle-fill ai-icon"></i>
          <span>${escapeHtml(a.ar || a.action || a.en || "")}</span>
        </li>`).join("")
    : (meta && meta.criticalAction
        ? `<li><i class="bi bi-arrow-left-circle-fill ai-icon"></i><span>${escapeHtml(meta.criticalAction)}</span></li>`
        : "");

  const managerNote = kpi.managerNote
    ? `<div class="kpi-explain-section">
        <div class="kpi-explain-section-title"><i class="bi bi-lightbulb-fill me-1"></i>ملاحظة المشرف</div>
        <div style="font-size:.84rem;color:#475569;line-height:1.8;">${escapeHtml(kpi.managerNote)}</div>
       </div>`
    : "";

  return `
  <div class="kpi-explain-card" data-kpi-key="${kpi.key}" data-kpi-label="${escapeHtml(kpi.label)}">
    <div class="kpi-explain-header" onclick="this.closest('.kpi-explain-card').classList.toggle('kec-open')" role="button" aria-expanded="false">
      <div class="kpi-explain-icon" style="background:${iconBg}; color:${iconColor};">
        <i class="bi ${icon}"></i>
      </div>
      <div class="kpi-explain-title">
        <div class="kpi-explain-name">${escapeHtml(kpi.label)}</div>
        <div class="kpi-explain-val">
          القيمة الحالية:
          <strong style="color:${iconColor};">${fmtVal}${escapeHtml(unit)}</strong>
        </div>
      </div>
      <span class="badge bg-${color} kpi-explain-badge">${bandText}</span>
      <i class="bi bi-chevron-down kpi-explain-chevron"></i>
    </div>

    <div class="kpi-explain-body">

      ${meta && meta.meaning ? `
      <div class="kpi-explain-section">
        <div class="kpi-explain-section-title"><i class="bi bi-info-circle me-1"></i>ماذا يعني هذا المؤشر؟</div>
        <p style="font-size:.875rem;color:#334155;line-height:1.9;margin:0;">${escapeHtml(meta.meaning)}</p>
      </div>` : ""}

      ${meta && meta.formula ? `
      <div class="kpi-explain-section">
        <div class="kpi-explain-section-title"><i class="bi bi-calculator me-1"></i>طريقة الحساب</div>
        <div class="kpi-formula">${escapeHtml(meta.formula)}</div>
      </div>` : ""}

      ${meta && meta.importance ? `
      <div class="kpi-explain-section">
        <div class="kpi-explain-section-title"><i class="bi bi-star-fill me-1"></i>لماذا هذا المؤشر مهم؟</div>
        <p style="font-size:.875rem;color:#334155;line-height:1.9;margin:0;">${escapeHtml(meta.importance)}</p>
      </div>` : ""}

      ${thresholdPills ? `
      <div class="kpi-explain-section">
        <div class="kpi-explain-section-title"><i class="bi bi-thermometer-half me-1"></i>تفسير النطاقات</div>
        <div class="kpi-threshold-row">${thresholdPills}</div>
      </div>` : ""}

      ${actionList ? `
      <div class="kpi-explain-section">
        <div class="kpi-explain-section-title"><i class="bi bi-tools me-1"></i>الإجراءات المقترحة عند التراجع</div>
        <ul class="kpi-action-list">${actionList}</ul>
      </div>` : ""}

      ${managerNote}

      <div class="kpi-explain-section">
        <div class="kpi-explain-section-title"><i class="bi bi-database me-1"></i>مصدر البيانات والفترة</div>
        <div class="d-flex flex-wrap gap-2 align-items-center">
          <code class="kpi-source-badge"><i class="bi bi-plug me-1"></i>${escapeHtml(meta ? meta.dataSource : "/api/kpi/dashboard-data")}</code>
          <span style="font-size:.78rem;color:#64748b;">
            <i class="bi bi-calendar3 me-1"></i>الفترة المحددة في لوحة التحكم
          </span>
          ${now ? `<span style="font-size:.78rem;color:#94a3b8;"><i class="bi bi-clock me-1"></i>آخر تحديث: ${escapeHtml(now)}</span>` : ""}
        </div>
      </div>

    </div>
  </div>`;
}

function renderKpiExplanations(kpis) {
  // ── 1. Update legacy modal explanationsContainer (keep old modal working) ──
  const legacyContainer = document.getElementById("explanationsContainer");
  if (legacyContainer) {
    if (!Array.isArray(kpis) || kpis.length === 0) {
      legacyContainer.innerHTML = dashboardTemplate('<p class="text-muted mb-0">لا توجد شروحات متاحة للمؤشرات.</p>');
    } else {
      legacyContainer.innerHTML = dashboardTemplate(
        kpis.map((kpi) => {
          const meta = KPI_EXPLAIN_META[kpi.key];
          return `<div class="mb-3"><h6 class="fw-bold">${escapeHtml(kpi.label)}</h6>
            <p class="small mb-1 text-muted">${escapeHtml(meta ? meta.meaning : (kpi.explanation || ""))}</p>
            ${meta && meta.formula ? `<code class="kpi-source-badge">${escapeHtml(meta.formula)}</code>` : ""}
          </div>`;
        }).join("")
      );
    }
  }

  // ── 2. Populate rich explain panel ─────────────────────────────────────────
  const explainView = document.getElementById("kpiExplainView");
  if (!explainView) return;
  if (!Array.isArray(kpis) || kpis.length === 0) {
    explainView.innerHTML = dashboardTemplate(
      '<div class="kpi-explain-empty"><i class="bi bi-hourglass-split fs-3 d-block mb-2"></i>لم تُحمَّل بيانات المؤشرات بعد.</div>'
    );
    return;
  }

  const now = new Date().toLocaleTimeString("ar-JO", { hour: "2-digit", minute: "2-digit" });
  const periodEl = document.getElementById("dashboardLastUpdated");
  const periodText = periodEl && periodEl.textContent ? periodEl.textContent : now;

  const cards = kpis.map((kpi) => _kpiExplainCard(kpi, KPI_EXPLAIN_META[kpi.key] || null, periodText)).join("");

  explainView.innerHTML = dashboardTemplate(`
    <div class="kpi-explain-intro">
      <strong><i class="bi bi-info-circle-fill me-1"></i>دليل مؤشرات الأداء الرئيسية</strong><br>
      تساعد مؤشرات الأداء الرئيسية في فهم مستوى أداء الروضات والحضانات من حيث الحضور، الالتزام بالتقارير، السلامة، الإشراف، التدريب، استغلال السعة، وجودة الحوكمة. يتم احتساب هذه المؤشرات بناءً على البيانات المسجلة في النظام خلال الفترة المحددة، وتساعد الإدارة على تحديد الأولويات واتخاذ الإجراءات المناسبة.
    </div>
    <input
      type="search"
      class="kpi-explain-search"
      placeholder="ابحث عن مؤشر..."
      oninput="window._kpiExplainSearch(this.value)"
      aria-label="بحث في المؤشرات"
    >
    <div id="kpiExplainCards">${cards}</div>
  `);
}

window._kpiExplainSearch = function(term) {
  const q = term.trim().toLowerCase();
  document.querySelectorAll("#kpiExplainCards .kpi-explain-card").forEach(function(card) {
    const label = (card.dataset.kpiLabel || "").toLowerCase();
    card.style.display = (!q || label.includes(q)) ? "" : "none";
  });
};

function renderKpiSummaryRow(payload) {
  const attendanceValue = safeNumber(payload?.attendance_rate?.value);
  const ratioValue = safeNumber(payload?.ratio_compliance?.value);
  const incidentValue = safeNumber(payload?.incident_rate?.value);
  const governanceValue = safeNumber(payload?.overall_gcei?.value);

  updateElementText("kpiAttendance", `${formatOneDecimal(attendanceValue)}%`);
  updateElementText("kpiRatioCompliance", `${formatOneDecimal(ratioValue)}%`);
  updateElementText("kpiIncidentRate", `${formatOneDecimal(incidentValue)}/1K`);

  const band =
    normalizeBand(payload?.overall_gcei?.band) || inferBand("overall_gcei", governanceValue);
  const governanceBand = document.getElementById("governanceBand");
  if (governanceBand) {
    governanceBand.className = `badge fs-4 px-4 py-2 bg-${BAND_BOOTSTRAP[band] || "secondary"}`;
    governanceBand.textContent = (BAND_LABEL[band] || BAND_LABEL.neutral)();
  }

  updateElementText("governanceScore", `${formatOneDecimal(governanceValue)}%`);
}

async function loadKPIs(prefetchedData = null) {
  try {
    const data =
      prefetchedData ||
      (await dashboardFetch(
        buildUrlWithParams(DASHBOARD_API.admin.kpis, {
          ...getDashboardDateRange(),
          locale: dashboardCurrentLang(),
        })
      ));
    const kpis = buildKpiRows(data);

    DASHBOARD_STATE.kpis = kpis;
    renderKpiCards(kpis);
    renderKpiTable(kpis);
    renderKpiStatusCounts(kpis, Array.isArray(data?.alerts) ? data.alerts.length : undefined);
    renderKpiExplanations(kpis);
    renderKpiSummaryRow(data);
  } catch (error) {
    console.error("Error loading KPIs:", error);
    renderKpiCards([]);
    renderKpiTable([]);
  }
}

function openKpiActionItems(metricKey) {
  const metric = DASHBOARD_STATE.kpis.find((kpi) => kpi.key === metricKey);
  const title = document.getElementById("actionModalTitle");
  const container = document.getElementById("actionItemsContainer");
  const modalElement = document.getElementById("kpiActionModal");

  if (!title || !container || !modalElement) return;

  title.textContent = metric
    ? `${dashboardLiteral("خطة الإجراء")}: ${metric.label}`
    : dashboardLiteral("خطة الإجراء");

  if (!metric || !Array.isArray(metric.actions) || metric.actions.length === 0) {
    container.innerHTML = dashboardTemplate(
      '<p class="text-muted mb-0">لا توجد إجراءات مقترحة لهذا المؤشر.</p>'
    );
  } else {
    container.innerHTML = dashboardTemplate(
      metric.actions
        .map((item, index) => {
          const priority = String(item.priority || "medium").toLowerCase();
          const priorityLabel =
            priority === "high"
              ? dashboardLiteral("عالية")
              : priority === "medium"
                ? dashboardLiteral("متوسطة")
                : dashboardLiteral("منخفضة");
          const actionText = item.ar || item.action || item.en || dashboardLiteral("إجراء");
          const detail = item.ar || item.en || "";
          return `
          <div class="border rounded p-3 mb-2">
            <div class="d-flex justify-content-between align-items-start gap-2">
              <div>
                <div class="fw-semibold">${index + 1}. ${escapeHtml(actionText)}</div>
                ${detail ? `<div class="small text-muted mt-1">${escapeHtml(detail)}</div>` : ""}
              </div>
              <span class="badge bg-${priority === "high" ? "danger" : priority === "medium" ? "warning" : "info"}">${escapeHtml(priorityLabel)}</span>
            </div>
          </div>
        `;
        })
        .join("")
    );
  }

  new bootstrap.Modal(modalElement).show();
}

window.openKpiActionItems = openKpiActionItems;
window.loadDashboard = loadDashboard;
window.renderValidationDetails = renderValidationDetails;

function ensureDashboardDateRangeDefaults() {
  if (window.dashboardDateRange?.start && window.dashboardDateRange?.end) return;
  const today = new Date();
  const start = new Date(today.getFullYear(), today.getMonth(), 1);
  const end = new Date(today.getFullYear(), today.getMonth(), today.getDate());
  const toIso = (value) => value.toISOString().slice(0, 10);
  window.dashboardDateRange = {
    range: "month",
    start: toIso(start),
    end: toIso(end),
  };
}

async function loadKindergartensOverview() {
  const tableBody = document.getElementById("kindergartensOverviewTable");
  if (!tableBody) return;

  try {
    const data = await dashboardFetch(DASHBOARD_API.admin.kindergartens);
    const kindergartens = data.kindergartens || data.items || data || [];

    if (!Array.isArray(kindergartens) || kindergartens.length === 0) {
      tableBody.innerHTML = dashboardTemplate(
        '<tr><td colspan="8" class="text-center py-4 text-muted">لا توجد روضات</td></tr>'
      );
      return;
    }

    tableBody.innerHTML = dashboardTemplate(
      kindergartens
        .map((kg) => {
          const status = String(kg.status || "").toUpperCase();
          const statusClass = status === "ACTIVE" ? "success" : "secondary";
          return `
          <tr>
            <td>${escapeHtml(kg.name_ar || kg.name_en || "-")}</td>
            <td><span class="badge bg-${statusClass}">${statusLabel(status)}</span></td>
            <td>${formatNumber(kg.enrolled_count || 0)}</td>
            <td>${formatNumber(kg.attendance_today || 0)}</td>
            <td>${formatNumber(kg.pending_reports || 0)}</td>
            <td>${formatOneDecimal(kg.capacity_utilization || 0)}%</td>
            <td><span class="badge bg-${kg.license_valid ? "success" : "danger"}">${kg.license_valid ? dashboardLiteral("ساري") : dashboardLiteral("منتهي")}</span></td>
            <td>
              <a href="/kindergartens/${kg.id}" class="btn btn-sm btn-outline-primary" aria-label="${dashboardLiteral("عرض الروضة")}">
                <i class="bi bi-eye"></i>
              </a>
            </td>
          </tr>
        `;
        })
        .join("")
    );
  } catch (error) {
    console.error("Error loading kindergartens:", error);
    tableBody.innerHTML = dashboardTemplate(
      '<tr><td colspan="8" class="text-center py-4 text-danger">تعذر تحميل بيانات الروضات</td></tr>'
    );
  }
}

document.addEventListener("DOMContentLoaded", () => {
  ensureDashboardDateRangeDefaults();
  bindChartTypeToggles();
  renderValidationDetails();
  loadDashboard();
});
