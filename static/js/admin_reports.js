// admin_reports.js — Enterprise Reports Center logic
// Requires: Chart.js, chart_utils.js, sanitize.js, admin_analytics.js loaded beforehand.

(function () {
  "use strict";

  if (window.AdminReports) return;
  window.AdminReports = {};

  const API_BASE = "/api/analytics";
  const STRATEGIC_API_BASE = "/api/admin/reports";

  let historyItems = [];
  let previewItems = [];
  let previewColumns = [];
  let previewCurrentPage = 1;
  const previewPageSize = 5;
  let previewSortColumn = "";
  let previewSortDirection = "asc";
  let historySearchText = "";
  let historyCurrentPage = 1;
  const historyPageSize = 5;

  function showToast(msg) {
    const toastMessage = getEl("toastMessage");
    const actionToast = getEl("actionToast");
    if (toastMessage && actionToast) {
      toastMessage.innerText = msg;
      const toast = new window.bootstrap.Toast(actionToast);
      toast.show();
    }
  }

  function updateFilterVisibility() {
    // Only Governorate and Kindergarten are actually applied by the strategic
    // report endpoints (see buildStrategicQuery()). The remaining tab-specific
    // filters (status/severity/incident-type/SLA/district/sensitivity/…) were
    // never sent to the backend and had zero effect, so they are kept hidden
    // rather than presenting controls that silently do nothing.
    const deadFilters = [
      "filterStatusContainer",
      "filterSeverityContainer",
      "filterSourceContainer",
      "filterReviewerContainer",
      "filterAbsenceReasonContainer",
      "filterIncidentTypeContainer",
      "filterSlaContainer",
      "filterParentInformedContainer",
      "filterDistrictContainer",
      "filterSensitivityContainer",
      "filterActorRoleContainer",
      "filterTrainingStatusContainer",
    ];
    deadFilters.forEach((id) => {
      const el = getEl(id);
      if (el) el.classList.add("d-none");
    });

    ["filterGovContainer", "filterKgContainer"].forEach((id) => {
      const el = getEl(id);
      if (el) el.classList.remove("d-none");
    });
  }

  // ===========================================================================
  // Helpers
  // ===========================================================================
  function getMultiSelectValues(id) {
    const el = getEl(id);
    if (!el) return [];
    return Array.from(el.selectedOptions)
      .map((opt) => opt.value)
      .filter((val) => val !== "");
  }

  function escapeHtml(value) {
    return String(value ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function reportsText(ar, en) {
    const lang =
      document.documentElement.getAttribute("lang") === "en" ? "en" : "ar";
    return lang === "en" ? en : ar;
  }

  /* Arabic/English labels for report sample_data column keys.
     Fallback humanizes unknown keys instead of showing raw snake_case. */
  const COLUMN_LABELS = {
    b1: ["يوم إلى 3 أشهر", "1 day to 3 months"],
    b2: ["3 إلى 6 أشهر", "3 to 6 months"],
    b3: ["6 إلى 9 أشهر", "6 to 9 months"],
    b4: ["9 إلى 12 شهر", "9 to 12 months"],
    b5: ["12 إلى 15 شهر", "12 to 15 months"],
    b6: ["15 إلى 18 شهر", "15 to 18 months"],
    b7: ["18 إلى 21 شهر", "18 to 21 months"],
    b8: ["21 إلى 24 شهر", "21 to 24 months"],
    b9: ["24 إلى 27 شهر", "24 to 27 months"],
    b10: ["27 إلى 30 شهر", "27 to 30 months"],
    b11: ["30 إلى 33 شهر", "30 to 33 months"],
    b12: ["33 إلى 36 شهر", "33 to 36 months"],
    b13: ["36 إلى 39 شهر", "36 to 39 months"],
    b14: ["39 إلى 42 شهر", "39 to 42 months"],
    b15: ["42 إلى 45 شهر", "42 to 45 months"],
    b16: ["45 إلى 48 شهر", "45 to 48 months"],
    b17: ["48 إلى 51 شهر", "48 to 51 months"],
    b18: ["51 إلى 54 شهر", "51 to 54 months"],
    b19: ["54 إلى 57 شهر", "54 to 57 months"],
    governorate: ["المحافظة", "Governorate"],
    city: ["المدينة", "City"],
    district: ["اللواء", "District"],
    kindergarten: ["الحضانة", "Kindergarten"],
    kindergartens: ["الحضانات", "Kindergartens"],
    kindergarten_name: ["اسم الحضانة", "Kindergarten name"],
    kindergarten_count: ["عدد الحضانات", "Kindergartens"],
    class: ["الشعبة", "Class"],
    classes: ["الشعب", "Classes"],
    class_count: ["عدد الشعب", "Classes"],
    children: ["الأطفال", "Children"],
    children_count: ["عدد الأطفال", "Children"],
    total_children: ["إجمالي الأطفال", "Total children"],
    total_kindergartens: ["إجمالي الحضانات", "Total kindergartens"],
    total_classes: ["إجمالي الشعب", "Total classes"],
    supervisor: ["المشرفة", "Supervisor"],
    supervisors: ["المشرفات", "Supervisors"],
    supervisor_count: ["عدد المشرفات", "Supervisors"],
    total_supervisors: ["إجمالي المشرفات", "Total supervisors"],
    required_supervisors: ["المشرفات المطلوبات", "Required supervisors"],
    actual_supervisors: ["المشرفات الفعليات", "Actual supervisors"],
    supervisor_gap: ["فجوة الإشراف", "Supervisor gap"],
    capacity: ["الطاقة الاستيعابية", "Capacity"],
    capacity_total: ["إجمالي الطاقة الاستيعابية", "Total capacity"],
    capacity_utilization_pct: ["نسبة الإشغال %", "Utilization %"],
    utilization: ["الإشغال", "Utilization"],
    utilization_pct: ["نسبة الإشغال %", "Utilization %"],
    status: ["الحالة", "Status"],
    score: ["الدرجة", "Score"],
    risk: ["المخاطر", "Risk"],
    risk_score: ["درجة المخاطر", "Risk score"],
    pct: ["النسبة %", "Pct"],
    per: ["لكل", "Per"],
    total: ["الإجمالي", "Total"],
    month: ["الشهر", "Month"],
    date: ["التاريخ", "Date"],
    period: ["الفترة", "Period"],
    from: ["من", "From"],
    to: ["إلى", "To"],
    compliance: ["الامتثال", "Compliance"],
    compliance_score: ["درجة الامتثال", "Compliance score"],
    quality: ["الجودة", "Quality"],
    data_quality_score: ["درجة جودة البيانات", "Data quality score"],
    gap: ["الفجوة", "Gap"],
    data: ["البيانات", "Data"],
    actual: ["الفعلي", "Actual"],
    required: ["المطلوب", "Required"],
    normal: ["طبيعي", "Normal"],
    name: ["الاسم", "Name"],
    count: ["العدد", "Count"],
    value: ["القيمة", "Value"],
    rate: ["المعدل", "Rate"],
    average: ["المتوسط", "Average"],
    attendance: ["الحضور", "Attendance"],
    attendance_rate: ["معدل الحضور", "Attendance rate"],
    incidents: ["الحوادث", "Incidents"],
    incident_count: ["عدد الحوادث", "Incidents"],
    enrollment: ["التسجيل", "Enrollment"],
    age_group: ["الفئة العمرية", "Age group"],
    children_per_kindergarten: ["أطفال لكل حضانة", "Children per kindergarten"],
    children_per_supervisor: ["أطفال لكل مشرفة", "Children per supervisor"],
    children_per_class: ["أطفال لكل شعبة", "Children per class"],
  };

  function columnLabel(col) {
    const key = String(col).toLowerCase();
    const hit = COLUMN_LABELS[key];
    if (hit) return reportsText(hit[0], hit[1]);
    // humanize unknown keys; try word-by-word translation of compound keys
    const words = key.split(/[_\s]+/).map((w) => {
      const wHit = COLUMN_LABELS[w];
      return wHit ? reportsText(wHit[0], wHit[1]) : w;
    });
    return words.join(" ");
  }

  function formatCellValue(val) {
    if (val === null || val === undefined) return "-";
    if (Array.isArray(val)) return val.map(formatCellValue).join("، ");
    if (typeof val === "object") {
      // bilingual {ar, en} payloads → pick by language; other objects →
      // readable key: value pairs instead of [object Object]
      const lang = document.documentElement.getAttribute("lang") === "en" ? "en" : "ar";
      if (val[lang] !== undefined) return String(val[lang]);
      if (val.ar !== undefined || val.en !== undefined) return String(val.ar ?? val.en);
      return Object.entries(val)
        .map(([k, v]) => `${columnLabel(k)}: ${formatCellValue(v)}`)
        .join("، ");
    }
    if (typeof val === "string" && /^\d{4}-\d{2}-\d{2}/.test(val)) {
      return formatDateSafe(val);
    }
    return String(val);
  }

  function getEl(id) {
    return document.getElementById(id);
  }

  function setText(id, text) {
    const el = getEl(id);
    if (!el) return;
    el.innerText = text;
  }

  function showEl(id) {
    const el = getEl(id);
    if (el) el.classList.remove("d-none");
  }

  function hideEl(id) {
    const el = getEl(id);
    if (el) el.classList.add("d-none");
  }

  function getPeriod() {
    return {
      start: getEl("periodStart")?.value || "",
      end: getEl("periodEnd")?.value || "",
    };
  }

  function getGovernorate() {
    return getEl("governorateFilter")?.value || "";
  }

  function getReportLevel() {
    return getEl("reportLevel")?.value || "jordan";
  }

  function getCityFilter() {
    return (getEl("cityFilter")?.value || "").trim();
  }

  function getFilters() {
    const singleVal = (id) => {
      const el = getEl(id);
      return el?.value || "";
    };
    return {
      governorates: getMultiSelectValues("governorateFilter"),
      kindergarten_ids: getMultiSelectValues("kindergartenFilter").map(Number),
      statuses: getMultiSelectValues("statusFilter"),
      severities: getMultiSelectValues("severityFilter"),
      sources: getMultiSelectValues("sourceFilter"),
      reviewer_ids: getMultiSelectValues("reviewerFilter").map(Number),
      absence_reasons: getMultiSelectValues("absenceReasonFilter"),
      incident_types: getMultiSelectValues("incidentTypeFilter"),
      sla_status: singleVal("slaFilter"),
      parent_informed: singleVal("parentInformedFilter"),
      district: singleVal("districtFilter"),
      sensitivity_level: singleVal("sensitivityFilter")
        ? Number(singleVal("sensitivityFilter"))
        : null,
      actor_role: singleVal("actorRoleFilter"),
      training_status: singleVal("trainingStatusFilter"),
    };
  }

  function getReportType() {
    const activeTab = document.querySelector(
      "#reportCategoryTabs .nav-link.active",
    );
    if (activeTab) {
      const target = activeTab.getAttribute("data-bs-target");
      if (target === "#pane-incidents") return "incidents";
      if (target === "#pane-compliance") return "compliance";
      if (target === "#pane-enrollment") return "enrollment";
      if (target === "#pane-audit") return "full_audit";
      if (target === "#pane-staff") return "staff_training";
      if (target === "#pane-welfare") return "welfare";
      if (target === "#pane-trends") return "trends";
      if (target === "#pane-capacity") return "capacity";
      if (target === "#pane-parent") return "parent_engagement";
      if (target === "#pane-dataquality") return "data_quality";
    }
    return "attendance";
  }

  function getStrategicEndpoint(reportType) {
    const map = {
      attendance: "/children/summary",
      incidents: "/risk-ranking",
      compliance: "/compliance",
      enrollment: "/children/geography",
      full_audit: "/data-quality",
      staff_training: "/supervisors/coverage",
      welfare: "/children/gender",
      trends: "/overview",
      capacity: "/kindergartens/summary",
      parent_engagement: "/children/age-buckets",
      data_quality: "/data-quality",
    };
    return map[reportType] || "/overview";
  }

  function getStrategicReportType(reportType) {
    const map = {
      attendance: "children_summary",
      incidents: "risk_ranking",
      compliance: "compliance",
      enrollment: "children_geography",
      full_audit: "data_quality",
      staff_training: "supervisors_coverage",
      welfare: "children_gender",
      trends: "overview",
      capacity: "kindergartens_summary",
      parent_engagement: "children_age_buckets",
      data_quality: "data_quality",
    };
    return map[reportType] || "overview";
  }

  function buildStrategicQuery() {
    const period = getPeriod();
    const params = new URLSearchParams();
    const reportLang = getEl("reportLang")?.value;
    params.set(
      "lang",
      reportLang || (document.documentElement.getAttribute("lang") === "en" ? "en" : "ar"),
    );
    params.set("level", getReportLevel());
    if (period.start) params.set("date_from", period.start);
    if (period.end) params.set("date_to", period.end);

    const gov = getGovernorate();
    if (gov) params.set("governorate", gov);
    const city = getCityFilter();
    if (city) params.set("city", city);

    const kgVals = getMultiSelectValues("kindergartenFilter");
    if (kgVals.length) params.set("kindergarten_id", kgVals[0]);
    return params.toString();
  }

  function toPreviewPayloadFromStrategic(data) {
    const kpis = [];
    if (data.kpis) {
      Object.entries(data.kpis).forEach(([key, value]) => {
        if (typeof value === "number") {
          const hit = COLUMN_LABELS[key.toLowerCase()];
          const labelAr = hit ? hit[0] : key;
          const labelEn = hit ? hit[1] : key;
          kpis.push({
            label_ar: labelAr,
            label_en: labelEn,
            value,
            unit: key.includes("pct") || key.includes("score") ? "%" : "",
          });
        }
      });
    }

    const charts = [];
    if (data.charts?.children_by_governorate) {
      charts.push({
        id: "children_by_governorate",
        type: "bar",
        label_ar: "الأطفال حسب المحافظة",
        label_en: "Children by Governorate",
        data: data.charts.children_by_governorate,
      });
    }
    if (data.charts?.children_by_city) {
      charts.push({
        id: "children_by_city",
        type: "bar",
        label_ar: "الأطفال حسب المدينة",
        label_en: "Children by City",
        data: data.charts.children_by_city,
      });
    }
    if (data.charts?.age_distribution) {
      charts.push({
        id: "age_distribution",
        type: "bar",
        label_ar: "توزيع الفئات العمرية",
        label_en: "Age Buckets",
        data: data.charts.age_distribution,
      });
    }

    let sample_data = [];
    if (Array.isArray(data)) {
      sample_data = data;
    } else {
      sample_data =
        data.tables?.risk_ranking ||
        data.tables?.city_breakdown ||
        data.tables?.governorate_breakdown ||
        data.supervisors ||
        data.ranking ||
        data.cities ||
        data.governorates ||
        data.age_buckets ||
        [];
    }

    const insights = [];
    if (data.interpretation?.summary)
      insights.push(data.interpretation.summary);
    if (data.interpretation?.recommended_action)
      insights.push(data.interpretation.recommended_action);

    return {
      total_records: Array.isArray(sample_data) ? sample_data.length : 0,
      kpis,
      charts,
      sample_data,
      insights,
      warnings: [],
    };
  }

  /**
   * Debounce a function to delay execution until after `ms` milliseconds
   * have elapsed since the last invocation. Used to prevent excessive
   * updates during rapid user input (e.g., search filters).
   */
  function debounce(fn, ms = 250) {
    let timer;
    return function (...args) {
      clearTimeout(timer);
      timer = setTimeout(() => fn.apply(this, args), ms);
    };
  }

  const _AMMAN_TZ = "Asia/Amman";
  const _DATE_FMT_AR = new Intl.DateTimeFormat("ar-JO", {
    year: "numeric",
    month: "short",
    day: "numeric",
    timeZone: _AMMAN_TZ,
  });
  const _DATETIME_FMT_AR = new Intl.DateTimeFormat("ar-JO", {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    timeZone: _AMMAN_TZ,
  });
  const _DATE_FMT_EN = new Intl.DateTimeFormat("en-JO", {
    year: "numeric",
    month: "short",
    day: "numeric",
    timeZone: _AMMAN_TZ,
  });
  const _DATETIME_FMT_EN = new Intl.DateTimeFormat("en-JO", {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    timeZone: _AMMAN_TZ,
  });
  const _TIME_FMT_AR = new Intl.DateTimeFormat("ar-JO", {
    hour: "2-digit",
    minute: "2-digit",
    timeZone: _AMMAN_TZ,
  });
  const _TIME_FMT_EN = new Intl.DateTimeFormat("en-JO", {
    hour: "2-digit",
    minute: "2-digit",
    timeZone: _AMMAN_TZ,
  });

  /** Format the time-of-day only (Asia/Amman). Returns "-" for empty/unparseable. */
  function formatTimeSafe(val) {
    if (val == null || val === "") return "-";
    const d = new Date(val);
    if (isNaN(d.getTime())) return "-";
    const lang =
      document.documentElement.getAttribute("lang") === "en" ? "en" : "ar";
    return (lang === "en" ? _TIME_FMT_EN : _TIME_FMT_AR).format(d);
  }

  /**
   * Safely format a date/datetime value for display in Asia/Amman timezone.
   * Returns "-" for null/undefined/empty. For unparseable values returns an
   * Invalid Date badge showing the raw string so the user can investigate.
   */
  function formatDateSafe(val, { time = false } = {}) {
    if (val == null || val === "") return "-";
    const d = new Date(val);
    if (isNaN(d.getTime())) {
      return `<span class="badge bg-warning text-dark" title="${escapeHtml(String(val))}">Invalid Date</span>`;
    }
    const lang =
      document.documentElement.getAttribute("lang") === "en" ? "en" : "ar";
    if (lang === "en") {
      return time ? _DATETIME_FMT_EN.format(d) : _DATE_FMT_EN.format(d);
    }
    return time ? _DATETIME_FMT_AR.format(d) : _DATE_FMT_AR.format(d);
  }

  async function fetchWithAuth(url, options) {
    const method = (options?.method || "GET").toUpperCase();
    const opts = Object.assign({ credentials: "same-origin" }, options || {});
    opts.headers = Object.assign(
      { Accept: "application/json" },
      opts.headers || {},
    );
    if (!["GET", "HEAD", "OPTIONS"].includes(method)) {
      const csrfToken =
        (window.CSRF_CONFIG &&
          window.CSRF_CONFIG.cookieName &&
          window.AuthStorage &&
          window.AuthStorage.getCookie &&
          window.AuthStorage.getCookie(window.CSRF_CONFIG.cookieName)) ||
        document
          .querySelector('meta[name="csrf-token"]')
          ?.getAttribute("content") ||
        "";
      if (csrfToken) {
        opts.headers["X-CSRF-Token"] = csrfToken;
      }
    }
    const response = await fetch(url, opts);
    if (response.status === 401) {
      window.location.href =
        "/login?redirect=" + encodeURIComponent(window.location.pathname);
      return null;
    }
    if (!response.ok) {
      const err = new Error(
        response.statusText || `Request failed with status ${response.status}`,
      );
      err.status = response.status;
      throw err;
    }
    return response;
  }

  function destroyChartInstances() {
    if (!window.Chart) return;
    Object.values(window.Chart.instances).forEach((chart) => {
      if (chart.canvas && chart.canvas.id.startsWith("chart-")) {
        chart.destroy();
      }
    });
  }

  // ===========================================================================
  // Governorate & Kindergarten population
  // ===========================================================================
  async function loadGovernorates() {
    const select = getEl("governorateFilter");
    if (!select) return;

    let list = [];
    try {
      const res = await fetchWithAuth("/api/admin/options/governorates");
      if (res) {
        const data = await res.json();
        list = data.governorates || [];
      }
    } catch (e) {
      console.error("Failed to load governorates from API", e);
    }

    if (!list.length) {
      console.warn("No governorates returned from API");
      return;
    }

    // keep first option
    while (select.options.length > 1) select.remove(1);
    list.forEach((g) => {
      const opt = document.createElement("option");
      opt.value = g.value ?? g.id ?? g;
      opt.textContent =
        g.label ||
        reportsText(g.name_ar || g.name_en, g.name_en || g.name_ar) ||
        String(g);
      select.appendChild(opt);
    });
  }

  async function loadCities() {
    const citySelect = getEl("cityFilter");
    const govSelect = getEl("governorateFilter");
    if (!citySelect || !govSelect) return;
    const gov = (govSelect.value || "").trim();
    citySelect.replaceChildren();
    const allCitiesOption = document.createElement("option");
    allCitiesOption.value = "";
    allCitiesOption.textContent = reportsText("جميع المدن", "All Cities");
    citySelect.appendChild(allCitiesOption);
    if (!gov) {
      citySelect.disabled = true;
      return;
    }
    citySelect.disabled = true;
    try {
      const resp = await fetchWithAuth("/api/locations/jordan/governorates/" + encodeURIComponent(gov) + "/areas");
      if (!resp) return;
      const json = await resp.json();
      const areas = (json.data && json.data.areas) || [];
      areas.forEach(a => {
        const opt = document.createElement("option");
        opt.value = a.key;
        opt.textContent = reportsText(a.name_ar, a.name_en || a.name_ar);
        citySelect.appendChild(opt);
      });
      citySelect.disabled = false;
    } catch (e) {
      console.warn("Failed to load cities:", e);
      citySelect.disabled = false;
    }
  }

  async function loadKindergartens() {
    const select = getEl("kindergartenFilter");
    if (!select) return;
    try {
      const gov = getGovernorate();
      const url = gov
        ? `/api/admin/options/kindergartens?governorate=${encodeURIComponent(gov)}`
        : "/api/admin/options/kindergartens";
      const res = await fetchWithAuth(url);
      if (!res) return;
      const data = await res.json();
      const list = data.kindergartens || [];
      while (select.options.length > 1) select.remove(1);
      list.forEach((kg) => {
        const opt = document.createElement("option");
        opt.value = kg.id || kg;
        opt.textContent = kg.name_ar || kg.name_en || kg;
        select.appendChild(opt);
      });
    } catch (e) {
      console.error("Failed to load kindergartens", e);
    }
  }

  async function loadReviewers() {
    const select = getEl("reviewerFilter");
    if (!select) return;
    try {
      const res = await fetchWithAuth(
        "/api/admin/users?role=MANAGER&limit=100",
      );
      if (!res) return;
      const data = await res.json();
      const users = data.data || [];
      while (select.options.length > 1) select.remove(1);
      users.forEach((u) => {
        const opt = document.createElement("option");
        opt.value = u.id;
        opt.textContent = u.full_name || u.username;
        select.appendChild(opt);
      });
    } catch (e) {
      console.error("Failed to load reviewers", e);
    }
  }

  async function loadStatuses() {
    const select = getEl("statusFilter");
    if (!select) return;
    const fallback = [
      { value: "DRAFT", label_ar: "غير مكتمل", label_en: "Incomplete" },
      {
        value: "SUBMITTED",
        label_ar: "قيد التحقق",
        label_en: "Under Verification",
      },
      {
        value: "PENDING_REVIEW",
        label_ar: "قيد المراجعة",
        label_en: "Pending Review",
      },
      { value: "ACCEPTED", label_ar: "موافق عليه", label_en: "Approved" },
      { value: "REJECTED", label_ar: "مرفوض", label_en: "Rejected" },
      { value: "ACTIVE", label_ar: "نشط", label_en: "Active" },
      { value: "WAITLISTED", label_ar: "قائمة انتظار", label_en: "Waitlisted" },
      { value: "WITHDRAWN", label_ar: "منسحب", label_en: "Withdrawn" },
    ];
    const lang =
      document.documentElement.getAttribute("lang") === "en" ? "en" : "ar";
    const labelKey = lang === "en" ? "label_en" : "label_ar";
    while (select.options.length > 1) select.remove(1);
    fallback.forEach((s) => {
      const opt = document.createElement("option");
      opt.value = s.value;
      opt.textContent = s[labelKey];
      select.appendChild(opt);
    });
  }

  // ===========================================================================
  // Preview
  // ===========================================================================
  async function loadReportPreview({ silent = false } = {}) {
    const period = getPeriod();
    if (!period.start || !period.end) {
      if (!silent)
        alert(
          reportsText("يرجى تحديد نطاق التاريخ", "Please select a date range"),
        );
      return;
    }

    const reportType = getReportType();
    destroyChartInstances();
    hideEl("dataQualityBanner");
    hideEl("previewInsights");
    hideEl("previewWarnings");
    setText("previewRecordCount", "...");
    setText(
      "reportsLastUpdated",
      reportsText("جاري تحميل المعاينة...", "Loading preview..."),
    );

    try {
      const endpoint = getStrategicEndpoint(reportType);
      const query = buildStrategicQuery();
      const res = await fetchWithAuth(
        `${STRATEGIC_API_BASE}${endpoint}?${query}`,
      );
      if (!res) return;
      const raw = await res.json();
      const adapted = toPreviewPayloadFromStrategic(raw);
      renderPreview(adapted);
      setText(
        "reportsLastUpdated",
        reportsText("تم تحديث المعاينة", "Preview updated"),
      );
    } catch (e) {
      console.error("Preview failed", e);
      setText(
        "reportsLastUpdated",
        reportsText("فشل تحميل المعاينة", "Preview failed"),
      );
      const tb = getEl("previewTableBody");
      if (tb)
        tb.innerHTML = `<tr><td colspan="5" class="text-center py-4 text-danger">${reportsText("تعذر تحميل المعاينة.", "Failed to load preview.")}</td></tr>`;
    }
  }

  function renderPreview(data) {
    setText(
      "previewRecordCount",
      `${data.total_records || 0} ${reportsText("سجل", "records")}`,
    );

    // KPIs
    const kpiContainer = getEl("previewKpis");
    if (kpiContainer && data.kpis && data.kpis.length) {
      kpiContainer.innerHTML = data.kpis
        .map(
          (kpi) => `
            <div class="col-md-3 col-sm-6">
              <div class="p-3 bg-light rounded text-center border">
                <div class="fs-4 fw-bold text-primary mb-1">${escapeHtml(kpi.value.toString())} <small class="text-muted fs-6">${escapeHtml(kpi.unit)}</small></div>
                <div class="small text-muted">${escapeHtml(reportsText(kpi.label_ar || kpi.label, kpi.label_en || kpi.label))}</div>
              </div>
            </div>
            `,
        )
        .join("");
    }

    // Charts
    const chartsContainer = getEl("previewCharts");
    if (chartsContainer && data.charts && data.charts.length) {
      chartsContainer.innerHTML = data.charts
        .map((chart) => {
          const isLarge = chart.type === "line" || chart.type === "bar";
          return `
            <div class="${isLarge ? "col-lg-12" : "col-lg-6"} mb-4">
              <div class="border rounded p-3 bg-white shadow-sm h-100">
                <div class="fw-bold mb-3 text-center">${escapeHtml(reportsText(chart.label_ar || chart.label, chart.label_en || chart.label))}</div>
                <div style="position: relative; height: 300px; width: 100%;">
                  <canvas id="chart-${chart.id}"></canvas>
                </div>
              </div>
            </div>
            `;
        })
        .join("");

      data.charts.forEach((chart) => {
        const canvas = document.getElementById(`chart-${chart.id}`);
        if (!canvas) return;
        const chartData = chart.data || { labels: [], datasets: [] };

        // Handle bilingual labels
        if (chartData.labels) {
          chartData.labels = chartData.labels.map((l) =>
            typeof l === "object" && l !== null
              ? reportsText(l.ar || l.en, l.en || l.ar)
              : l,
          );
        }
        if (chartData.datasets) {
          chartData.datasets.forEach((ds) => {
            if (typeof ds.label === "object" && ds.label !== null) {
              ds.label = reportsText(
                ds.label.ar || ds.label.en,
                ds.label.en || ds.label.ar,
              );
            }
          });
        }

        new window.Chart(canvas, {
          type: chart.type || "bar",
          data: chartData,
          options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
              legend: {
                position: "bottom",
                rtl:
                  document.documentElement.getAttribute("dir") === "rtl" ||
                  document.documentElement.getAttribute("lang") === "ar",
                textDirection:
                  document.documentElement.getAttribute("dir") === "rtl" ||
                  document.documentElement.getAttribute("lang") === "ar"
                    ? "rtl"
                    : "ltr",
              },
              tooltip: {
                rtl:
                  document.documentElement.getAttribute("dir") === "rtl" ||
                  document.documentElement.getAttribute("lang") === "ar",
                textDirection:
                  document.documentElement.getAttribute("dir") === "rtl" ||
                  document.documentElement.getAttribute("lang") === "ar"
                    ? "rtl"
                    : "ltr",
              },
            },
          },
        });
      });
    } else if (chartsContainer) {
      chartsContainer.innerHTML = `
        <div class="col-12 text-center text-muted py-4">
          <i class="bi bi-bar-chart fs-1"></i>
          <div class="small mt-2">${reportsText("ستظهر الرسوم البيانية هنا", "Charts will appear here")}</div>
        </div>
      `;
    }

    // Sample data table
    previewItems = data.sample_data || [];
    previewColumns = previewItems.length ? Object.keys(previewItems[0]) : [];
    previewCurrentPage = 1;
    previewSortColumn = "";

    renderPreviewTable();
  }

  function renderPreviewTable() {
    const thead = getEl("previewTableHead");
    const tbody = getEl("previewTableBody");
    const pag = getEl("previewTablePagination");

    if (!thead || !tbody) return;

    if (!previewItems.length) {
      thead.innerHTML = `<tr><th colspan="5" class="text-center text-muted">${reportsText("لا تتوفر معاينة للتقرير", "No preview data")}</th></tr>`;
      tbody.innerHTML = `<tr><td colspan="5" class="text-center py-4 text-muted">${reportsText("لا تتوفر بيانات للفترة أو المعايير المحددة. يرجى تعديل عوامل التصفية أو اختيار نطاق زمني مختلف.", "No data")}</td></tr>`;
      if (pag) pag.classList.add("d-none");
      return;
    }

    if (pag) pag.classList.remove("d-none");

    // Sort
    let sorted = [...previewItems];
    if (previewSortColumn) {
      sorted.sort((a, b) => {
        let valA = a[previewSortColumn];
        let valB = b[previewSortColumn];
        if (valA === null || valA === undefined) valA = "";
        if (valB === null || valB === undefined) valB = "";
        if (typeof valA === "string") valA = valA.toLowerCase();
        if (typeof valB === "string") valB = valB.toLowerCase();
        if (valA < valB) return previewSortDirection === "asc" ? -1 : 1;
        if (valA > valB) return previewSortDirection === "asc" ? 1 : -1;
        return 0;
      });
    }

    // Paginate
    const totalPages = Math.ceil(sorted.length / previewPageSize);
    if (previewCurrentPage > totalPages) previewCurrentPage = totalPages;
    if (previewCurrentPage < 1) previewCurrentPage = 1;

    const startIdx = (previewCurrentPage - 1) * previewPageSize;
    const endIdx = Math.min(startIdx + previewPageSize, sorted.length);
    const paginated = sorted.slice(startIdx, endIdx);

    // Render Headers with sort icons. Sort state used to be conveyed only by
    // the caret icon's visible shape (no aria-sort), and the header only
    // responded to a mouse click — no tabindex/keydown, so keyboard and
    // screen-reader users could not sort this table at all.
    thead.innerHTML = `<tr>${previewColumns
      .map((col) => {
        const isSorted = previewSortColumn === col;
        const caret = isSorted
          ? previewSortDirection === "asc"
            ? ' <i class="bi bi-caret-up-fill"></i>'
            : ' <i class="bi bi-caret-down-fill"></i>'
          : "";
        const ariaSort = isSorted
          ? (previewSortDirection === "asc" ? "ascending" : "descending")
          : "none";
        return `<th scope="col" style="cursor: pointer" class="sortable-header" data-col="${escapeHtml(col)}" tabindex="0" role="button" aria-sort="${ariaSort}">${escapeHtml(columnLabel(col))}${caret}</th>`;
      })
      .join("")}</tr>`;

    // Add sort listeners
    const applySort = (col) => {
      if (previewSortColumn === col) {
        previewSortDirection =
          previewSortDirection === "asc" ? "desc" : "asc";
      } else {
        previewSortColumn = col;
        previewSortDirection = "asc";
      }
      renderPreviewTable();
    };
    thead.querySelectorAll(".sortable-header").forEach((th) => {
      th.addEventListener("click", (e) => {
        applySort(e.currentTarget.getAttribute("data-col"));
      });
      th.addEventListener("keydown", (e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          applySort(e.currentTarget.getAttribute("data-col"));
        }
      });
    });

    // Render Rows
    tbody.innerHTML = paginated
      .map(
        (row) => `
      <tr>${previewColumns
        .map((col) => `<td>${escapeHtml(formatCellValue(row[col]))}</td>`)
        .join("")}</tr>`,
      )
      .join("");

    // Update pagination controls
    setText(
      "previewPaginationInfo",
      `${startIdx + 1}-${endIdx} ${reportsText("من", "of")} ${sorted.length}`,
    );
    const prevBtn = getEl("prevPreviewPageBtn");
    const nextBtn = getEl("nextPreviewPageBtn");
    if (prevBtn) prevBtn.disabled = previewCurrentPage === 1;
    if (nextBtn) nextBtn.disabled = previewCurrentPage === totalPages;
  }

  async function exportCurrentReport() {
    const period = getPeriod();
    if (!period.start || !period.end) {
      alert(
        reportsText("يرجى تحديد نطاق التاريخ", "Please select a date range"),
      );
      return;
    }

    const reportType = getReportType();
    const format = getEl("exportFormat")?.value || "CSV";
    try {
      const endpoint = getStrategicEndpoint(reportType);
      const params = new URLSearchParams(buildStrategicQuery());
      params.set("report_type", getStrategicReportType(reportType));
      params.set(
        "export_format",
        format.toLowerCase() === "json" ? "json" : "csv",
      );
      window.location.href = `${STRATEGIC_API_BASE}/export?${params.toString()}`;
    } catch (e) {
      console.error("Export failed", e);
      alert(reportsText("فشل بدء التصدير", "Export failed to start"));
    }
  }

  async function pollExportStatus(jobId) {
    const maxAttempts = 20;
    let attempts = 0;
    const interval = setInterval(async () => {
      attempts++;
      try {
        const res = await fetchWithAuth(`${API_BASE}/export/${jobId}`);
        if (!res) return;
        const status = await res.json();
        if (status.status === "COMPLETED") {
          clearInterval(interval);
          window.location.href = `${API_BASE}/export/${jobId}/file`;
        } else if (status.status === "FAILED") {
          clearInterval(interval);
          showExportJobError(status, jobId);
        } else if (attempts >= maxAttempts) {
          clearInterval(interval);
          showExportJobError(
            {
              error: reportsText(
                "تجاوز الوقت المسموح",
                "Export timed out after maximum wait",
              ),
            },
            jobId,
          );
        }
      } catch (e) {
        clearInterval(interval);
        console.error("Polling failed", e);
      }
    }, 1500);
  }

  function showExportJobError(status, jobId) {
    const banner = getEl("exportJobErrorBanner");
    const msgEl = getEl("exportJobErrorMsg");
    const traceLink = getEl("exportJobTraceLink");
    const retryBtn = getEl("retryExportBtn");
    if (!banner) return;

    if (msgEl) {
      const ts = status.created_at
        ? ` (${formatDateSafe(status.created_at, { time: true })})`
        : "";
      msgEl.textContent =
        (status.error ||
          reportsText("فشلت عملية التصدير", "The export operation failed")) +
        ts;
    }
    if (traceLink && status.trace_url) {
      traceLink.href = status.trace_url;
      traceLink.classList.remove("d-none");
    }
    if (retryBtn) {
      retryBtn.onclick = () => {
        banner.classList.add("d-none");
        exportCurrentReport();
      };
    }
    banner.classList.remove("d-none");
    loadRecentHistory();
  }

  // ===========================================================================
  // Templates
  // ===========================================================================

  // ===========================================================================
  // Templates Loading logic
  // ===========================================================================
  let loadedTemplates = [];

  async function loadSavedTemplates() {
    const list = getEl("templateList");
    if (!list) return;
    try {
      const res = await fetchWithAuth(`${API_BASE}/reports/templates`);
      if (!res) return;
      loadedTemplates = await res.json();

      if (!loadedTemplates.length) {
        list.innerHTML = `<li><span class="dropdown-item-text text-muted small">${reportsText("لا توجد قوالب محفوظة", "No saved templates")}</span></li>`;
        return;
      }

      list.innerHTML = loadedTemplates
        .map((t) => {
          return `<li><a class="dropdown-item" href="#" data-template-id="${t.id}">${escapeHtml(t.name)}</a></li>`;
        })
        .join("");

      list.querySelectorAll(".dropdown-item").forEach((item) => {
        item.addEventListener("click", (e) => {
          e.preventDefault();
          const tid = e.target.getAttribute("data-template-id");
          applyTemplate(tid);
        });
      });
    } catch (e) {
      console.error("Failed to load templates", e);
      list.innerHTML = `<li><span class="dropdown-item-text text-danger small">${reportsText("تعذر التحميل", "Failed to load")}</span></li>`;
    }
  }

  function applyTemplate(id) {
    const t = loadedTemplates.find((x) => String(x.id) === String(id));
    if (!t) return;

    // switch tab
    const tabMap = {
      attendance: "#tab-attendance",
      incidents: "#tab-incidents",
      compliance: "#tab-compliance",
      enrollment: "#tab-enrollment",
      full_audit: "#tab-audit",
      staff_training: "#tab-staff",
      welfare: "#tab-welfare",
      trends: "#tab-trends",
      capacity: "#tab-capacity",
      parent_engagement: "#tab-parent",
      data_quality: "#tab-dataquality",
    };
    const tabId = tabMap[t.report_type];
    if (tabId) {
      const tabEl = document.querySelector(tabId);
      if (tabEl) {
        const tab = new window.bootstrap.Tab(tabEl);
        tab.show();
      }
    }

    // Wait a moment for tab switch to update visibility
    setTimeout(() => {
      if (t.filters) {
        const setMultiValues = (id, vals) => {
          const select = getEl(id);
          if (!select || !vals) return;
          const arr = Array.isArray(vals) ? vals : [vals];
          Array.from(select.options).forEach((opt) => {
            opt.selected = arr.map(String).includes(String(opt.value));
          });
        };
        setMultiValues(
          "governorateFilter",
          t.filters.governorates || t.filters.governorate,
        );
        setMultiValues(
          "kindergartenFilter",
          t.filters.kindergarten_ids || t.filters.kindergarten_id,
        );
        setMultiValues("statusFilter", t.filters.statuses || t.filters.status);
        setMultiValues(
          "severityFilter",
          t.filters.severities || t.filters.severity,
        );
        setMultiValues("sourceFilter", t.filters.sources || t.filters.source);
        setMultiValues(
          "reviewerFilter",
          t.filters.reviewer_ids || t.filters.reviewer_id,
        );
      }
      if (getEl("exportFormat"))
        getEl("exportFormat").value = t.export_format || "CSV";
      if (getEl("includeCharts"))
        getEl("includeCharts").checked = t.include_charts;
      if (getEl("includeSummary"))
        getEl("includeSummary").checked = t.include_summary;

      loadReportPreview();
    }, 100);
  }

  async function saveAsTemplate() {
    const name = getEl("templateName")?.value?.trim();
    if (!name) {
      alert(
        reportsText("يرجى إدخال اسم القالب", "Please enter a template name"),
      );
      return;
    }

    const payload = {
      name,
      report_type: getReportType(),
      filters: getFilters(),
      export_format: getEl("exportFormat")?.value || "CSV",
      include_charts: getEl("includeCharts")?.checked ?? true,
      include_summary: getEl("includeSummary")?.checked ?? true,
    };

    try {
      const res = await fetchWithAuth(`${API_BASE}/reports/templates`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!res) return;
      await res.json();
      const modal = window.bootstrap?.Modal?.getInstance(
        getEl("saveTemplateModal"),
      );
      if (modal) modal.hide();
      showToast(
        reportsText("تم حفظ القالب بنجاح", "Template saved successfully"),
      );
      loadSavedTemplates();
    } catch (e) {
      console.error("Save template failed", e);
      alert(reportsText("فشل حفظ القالب", "Failed to save template"));
    }
  }

  // ===========================================================================
  // Scheduling
  // ===========================================================================
  async function scheduleReport() {
    const name = getEl("scheduleName")?.value?.trim();
    if (!name) {
      alert(
        reportsText("يرجى إدخال اسم الجدولة", "Please enter a schedule name"),
      );
      return;
    }

    const frequency = getEl("scheduleFrequency")?.value || "monthly";
    const recipientsRaw = getEl("scheduleRecipients")?.value || "";
    const recipients = recipientsRaw
      .split(",")
      .map((r) => r.trim())
      .filter((r) => r.length > 0);

    const payload = {
      name,
      report_type: getReportType(),
      filters: getFilters(),
      export_format: getEl("exportFormat")?.value || "CSV",
      frequency,
      recipients,
    };

    try {
      const res = await fetchWithAuth(`${API_BASE}/reports/schedules`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!res) return;
      await res.json();
      const modal = window.bootstrap?.Modal?.getInstance(
        getEl("scheduleModal"),
      );
      if (modal) modal.hide();
      alert(reportsText("تمت الجدولة بنجاح", "Report scheduled successfully"));
      loadRecentHistory();
    } catch (e) {
      console.error("Schedule failed", e);
      alert(reportsText("فشل جدولة التقرير", "Failed to schedule report"));
    }
  }

  // ===========================================================================
  // Recent History
  // ===========================================================================
  async function loadRecentHistory() {
    const tbody = getEl("reportsHistoryBody");
    if (!tbody) return;
    tbody.innerHTML = `<tr><td colspan="5" class="text-center py-4 text-muted">${reportsText("جارٍ تحميل البيانات، يرجى الانتظار.", "Loading...")}</td></tr>`;

    try {
      const res = await fetchWithAuth(`${API_BASE}/reports/history?limit=100`);
      if (!res) return;
      const data = await res.json();
      historyItems = Array.isArray(data) ? data : [];
      historyCurrentPage = 1;
      renderRecentHistory();
    } catch (e) {
      console.error("History load failed", e);
      tbody.innerHTML = `<tr><td colspan="5" class="text-center py-4 text-danger">${reportsText("تعذر تحميل السجل", "Failed to load history")}</td></tr>`;
    }
  }

  function renderRecentHistory() {
    const tbody = getEl("reportsHistoryBody");
    const pag = getEl("historyTablePagination");
    if (!tbody) return;

    // Filter
    const filtered = historyItems.filter((item) => {
      const name = (item.report_name || item.report_type || "").toLowerCase();
      const format = (item.format || "").toLowerCase();
      const status = (item.status || "").toLowerCase();
      const query = historySearchText.toLowerCase();
      return (
        name.includes(query) || format.includes(query) || status.includes(query)
      );
    });

    if (!filtered.length) {
      tbody.innerHTML = `<tr><td colspan="5" class="text-center py-4 text-muted">${reportsText("لا توجد نتائج مطابقة", "No matching reports")}</td></tr>`;
      setText("historyPaginationInfo", "0-0 of 0");
      if (pag) pag.classList.add("d-none");
      return;
    }

    if (pag) pag.classList.remove("d-none");

    const totalPages = Math.ceil(filtered.length / historyPageSize);
    if (historyCurrentPage > totalPages) historyCurrentPage = totalPages;
    if (historyCurrentPage < 1) historyCurrentPage = 1;

    const startIdx = (historyCurrentPage - 1) * historyPageSize;
    const endIdx = Math.min(startIdx + historyPageSize, filtered.length);
    const paginated = filtered.slice(startIdx, endIdx);

    const statusBadge = (status) => {
      const map = {
        PENDING: "bg-warning",
        PROCESSING: "bg-info",
        COMPLETED: "bg-success",
        FAILED: "bg-danger",
      };
      return map[status] || "bg-secondary";
    };

    const statusLabels = {
      PENDING: ["قيد الانتظار", "PENDING"],
      PROCESSING: ["جاري المعالجة", "PROCESSING"],
      COMPLETED: ["مكتمل", "COMPLETED"],
      FAILED: ["فاشل", "FAILED"]
    };

    const getStatusText = (status) => {
      const hit = statusLabels[status];
      return hit ? reportsText(hit[0], hit[1]) : status;
    };

    tbody.innerHTML = paginated
      .map((item) => {
        const isFailed = item.status === "FAILED";
        const reportLabel = escapeHtml(item.report_name || item.report_type);
        const errorDetail =
          isFailed && item.error
            ? `<div class="small text-danger mt-1"><i class="bi bi-exclamation-circle me-1" aria-hidden="true"></i>${escapeHtml(item.error)}</div>`
            : "";
        const traceLink =
          isFailed && item.trace_url
            ? `<a href="${escapeHtml(item.trace_url)}" class="btn btn-sm btn-outline-secondary ms-1" title="${reportsText("عرض سجلات", "View logs for")} ${reportLabel}"><i class="bi bi-journal-text" aria-hidden="true"></i></a>`
            : "";
        return `
      <tr>
        <td class="fw-medium">${escapeHtml(item.report_name || item.report_type)}</td>
        <td>${escapeHtml(item.format)}</td>
        <td>${formatDateSafe(item.generated_at, { time: true })}</td>
        <td>
          <span class="badge ${statusBadge(item.status)}">${escapeHtml(getStatusText(item.status))}</span>
          ${errorDetail}
        </td>
        <td class="text-center">
          ${item.status === "COMPLETED" && item.id ? `<a href="/api/analytics/export/${item.id}/file" class="btn btn-sm btn-outline-primary" title="${reportsText("تنزيل", "Download")} ${reportLabel}"><i class="bi bi-download" aria-hidden="true"></i></a>` : ""}
          <button class="btn btn-sm btn-outline-secondary retry-export-btn" data-action="rerun" data-id="${item.id}" title="${reportsText("إعادة إنشاء", "Regenerate")} ${reportLabel}"><i class="bi bi-arrow-clockwise" aria-hidden="true"></i></button>
          ${traceLink}
        </td>
      </tr>
    `;
      })
      .join("");

    // Wire rerun buttons
    tbody.querySelectorAll("[data-action='rerun']").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const id = btn.getAttribute("data-id");
        if (!id) return;
        await retryExportJob(id);
      });
    });

    async function retryExportJob(jobId) {
      showToast(
        reportsText("جاري إعادة محاولة التصدير...", "Retrying export..."),
      );
      try {
        const res = await fetchWithAuth(`${API_BASE}/export`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ retry_job_id: Number(jobId) }),
        });
        if (res) {
          showToast(reportsText("تم بدء تصدير التقرير", "Export job started"));
          await loadRecentHistory();
        }
      } catch (e) {
        showToast(
          reportsText("تعذر إعادة محاولة التصدير", "Failed to retry export"),
        );
      }
    }

    // Update pagination elements
    setText(
      "historyPaginationInfo",
      `${startIdx + 1}-${endIdx} ${reportsText("من", "of")} ${filtered.length}`,
    );
    const prevBtn = getEl("prevHistoryPageBtn");
    const nextBtn = getEl("nextHistoryPageBtn");
    if (prevBtn) prevBtn.disabled = historyCurrentPage === 1;
    if (nextBtn) nextBtn.disabled = historyCurrentPage === totalPages;
  }

  // ===========================================================================
  // Stats
  // ===========================================================================
  async function loadSummaryStats() {
    try {
      const res = await fetchWithAuth(`${API_BASE}/reports/history?limit=100`);
      if (!res) return;
      const data = await res.json();
      const items = Array.isArray(data) ? data : [];
      const now = new Date();
      const thisMonth = items.filter((it) => {
        const d = new Date(it.generated_at);
        // Skip entries whose generated_at cannot be parsed (avoids NaN comparisons)
        if (isNaN(d.getTime())) return false;
        return (
          d.getMonth() === now.getMonth() &&
          d.getFullYear() === now.getFullYear()
        );
      });
      const failed = items.filter((it) => it.status === "FAILED");

      setText("statReportsGenerated", String(thisMonth.length));
      setText("statFailedExports", String(failed.length));

      // Guard: only update last-generated stats when there is at least one item
      if (items.length > 0) {
        const latest = items[0];
        setText("statLastGenerated", formatDateSafe(latest.generated_at));
        setText("statLastGeneratedTime", formatTimeSafe(latest.generated_at));
      }
    } catch (e) {
      console.error("Stats load failed", e);
    }
  }

  async function loadScheduledCount() {
    try {
      const res = await fetchWithAuth(`${API_BASE}/reports/schedules`);
      if (!res) return;
      const data = await res.json();
      const active = Array.isArray(data) ? data.filter((s) => s.is_active) : [];
      setText("statScheduledReports", String(active.length));
    } catch (e) {
      console.error("Schedules load failed", e);
    }
  }

  // ===========================================================================
  // Init
  // ===========================================================================
  async function init() {
    await loadGovernorates();
    await loadKindergartens();
    await loadStatuses();
    await loadReviewers();
    await loadSummaryStats();
    await loadScheduledCount();
    await loadRecentHistory();
    await loadSavedTemplates();

    // Wire events
    updateFilterVisibility();

    // History search input
    getEl("searchHistoryInput")?.addEventListener("input", (e) => {
      historySearchText = e.target.value;
      historyCurrentPage = 1;
      renderRecentHistory();
    });

    // History Pagination controls
    getEl("prevHistoryPageBtn")?.addEventListener("click", () => {
      if (historyCurrentPage > 1) {
        historyCurrentPage--;
        renderRecentHistory();
      }
    });

    getEl("nextHistoryPageBtn")?.addEventListener("click", () => {
      const totalPages = Math.ceil(historyItems.length / historyPageSize);
      if (historyCurrentPage < totalPages) {
        historyCurrentPage++;
        renderRecentHistory();
      }
    });

    // Preview Pagination controls
    getEl("prevPreviewPageBtn")?.addEventListener("click", () => {
      if (previewCurrentPage > 1) {
        previewCurrentPage--;
        renderPreviewTable();
      }
    });

    getEl("nextPreviewPageBtn")?.addEventListener("click", () => {
      const totalPages = Math.ceil(previewItems.length / previewPageSize);
      if (previewCurrentPage < totalPages) {
        previewCurrentPage++;
        renderPreviewTable();
      }
    });

    getEl("previewReportBtn")?.addEventListener("click", loadReportPreview);
    getEl("exportReportBtn")?.addEventListener("click", exportCurrentReport);
    getEl("saveTemplateBtn")?.addEventListener("click", () => {
      getEl("templateName")?.focus();
      const modal = new window.bootstrap.Modal(getEl("saveTemplateModal"));
      modal.show();
    });
    getEl("confirmSaveTemplate")?.addEventListener("click", saveAsTemplate);
    getEl("scheduleReportBtn")?.addEventListener("click", () => {
      getEl("scheduleName")?.focus();
      const modal = new window.bootstrap.Modal(getEl("scheduleModal"));
      modal.show();
    });
    getEl("confirmSchedule")?.addEventListener("click", scheduleReport);
    getEl("refreshHistoryBtn")?.addEventListener("click", () => {
      loadRecentHistory();
      loadSummaryStats();
      loadScheduledCount();
    });
    getEl("resetFiltersBtn")?.addEventListener("click", () => {
      setTimeout(() => {
        loadRecentHistory();
        loadSummaryStats();
        loadScheduledCount();
      }, 100);
    });

    // Governorate -> kindergarten cascade & reload preview
    getEl("governorateFilter")?.addEventListener("change", async () => {
      await loadCities();
      await loadKindergartens();
      loadReportPreview();
    });

    // Tab change -> update hidden reportType and refresh preview (silent — no alert if dates not set yet)
    document
      .querySelectorAll("#reportCategoryTabs .nav-link")
      .forEach((tab) => {
        tab.addEventListener("shown.bs.tab", () => {
          getEl("reportType").value = getReportType();
          updateFilterVisibility();
          loadReportPreview({ silent: true });
        });
      });

    // Period change — user explicitly set dates, show alert if still incomplete
    getEl("periodStart")?.addEventListener("change", loadReportPreview);
    getEl("periodEnd")?.addEventListener("change", loadReportPreview);

    // Auto-load initial preview silently (no alert if dates not pre-filled)
    loadReportPreview({ silent: true });
  }



  document.addEventListener("DOMContentLoaded", init);

  // Expose helpers for tests and external callers
  window.AdminReports = window.AdminReports || {};
  window.AdminReports.formatDateSafe = formatDateSafe;
  window.AdminReports.formatToAmman = formatDateSafe;
  window.AdminReports.debounce = debounce;
  window.AdminReports.loadReportPreview = loadReportPreview;
})();
