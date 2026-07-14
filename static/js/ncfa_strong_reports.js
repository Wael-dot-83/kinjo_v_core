(function () {
  "use strict";

  const root = document.querySelector("[data-ncfa-strong-reports]");
  if (!root) return;

  const lang = document.documentElement.lang === "en" ? "en" : "ar";
  const t = (ar, en) => (lang === "en" ? en : ar);
  const bundleGrid = document.getElementById("ncfa-report-bundles");
  const resultSection = document.getElementById("ncfa-report-result");
  const resultTitle = document.getElementById("ncfa-result-title");
  const resultDescription = document.getElementById("ncfa-result-description");
  const resultStatus = document.getElementById("ncfa-result-status");
  const resultBody = document.getElementById("ncfa-result-body");
  const exportButton = document.getElementById("ncfa-export-csv");
  const periodSelect = document.getElementById("ncfa-period");
  const governorateSelect = document.getElementById("ncfa-governorate");
  const districtSelect = document.getElementById("ncfa-district");
  const resetScopeButton = document.getElementById("ncfa-reset-scope");

  let divisions = [];
  let activeBundle = null;
  let activePayload = null;
  let requestSequence = 0;
  const chartInstances = [];

  const REPORT_BUNDLES = [
    {
      code: "early_childhood_profile",
      icon: "bi-people-fill",
      titleAr: "الملف الإداري للطفولة المبكرة",
      titleEn: "Early Childhood Administrative Profile",
      descriptionAr: "ملخص الأطفال المسجلين وخصائصهم الديموغرافية وحالات التسجيل ضمن النطاق المختار.",
      descriptionEn: "A summary of recorded children, demographic distribution, and enrolment status in the selected scope.",
      indicators: ["children_count", "gender_distribution", "age_distribution_6mo", "enrollment_status"],
      bulletsAr: ["عدد الأطفال المسجلين", "التوزيع حسب الجنس والعمر", "حالات التسجيل"],
      bulletsEn: ["Recorded children", "Sex and age distribution", "Enrolment status"],
      caveatAr: "يعكس التقرير الأطفال المسجلين في KinJo ولا يمثل تعداداً سكانياً وطنياً.",
      caveatEn: "This report reflects children recorded in KinJo and is not a national population census."
    },
    {
      code: "nursery_capacity",
      icon: "bi-buildings-fill",
      titleAr: "الحضانات والطاقة الاستيعابية",
      titleEn: "Nurseries and Operational Capacity",
      descriptionAr: "عدد الحضانات وحالتها والسعة الصفية والتسجيلات النشطة ونسبة الإشغال التشغيلية.",
      descriptionEn: "Nursery counts and status, recorded class capacity, active enrolments, and operational occupancy.",
      indicators: ["kindergarten_count", "kindergarten_status", "occupancy_rate"],
      bulletsAr: ["عدد الحضانات وحالتها", "السعة الصفية المسجلة", "نسبة الإشغال"],
      bulletsEn: ["Nursery count and status", "Recorded class capacity", "Occupancy rate"],
      caveatAr: "نسبة الإشغال تعتمد على السعة الصفية المسجلة والتسجيلات النشطة، ولا تستبدل مطابقة السعة المرخصة رسمياً.",
      caveatEn: "Occupancy uses recorded class capacity and active enrolments; it does not replace reconciliation with officially licensed capacity."
    },
    {
      code: "attendance_daily_care",
      icon: "bi-calendar2-check-fill",
      titleAr: "الحضور واستمرارية الرعاية اليومية",
      titleEn: "Attendance and Daily-Care Continuity",
      descriptionAr: "مؤشرات الحضور المسجل وطلبات الغياب وإنجاز التقارير اليومية والتقارير المتأخرة.",
      descriptionEn: "Recorded attendance, absence requests, daily-report completion, and late-report indicators.",
      indicators: ["attendance_rate", "absence_requests", "daily_report_completion", "late_reports"],
      bulletsAr: ["الحضور المسجل", "طلبات الغياب", "إنجاز التقارير اليومية"],
      bulletsEn: ["Recorded attendance", "Absence requests", "Daily-report completion"],
      caveatAr: "نسبة الحضور محسوبة من سجلات الحضور المتاحة، ومعدل إنجاز التقارير من التقارير المنشأة؛ يجب مراجعة اكتمال التسجيل قبل النشر الرسمي.",
      caveatEn: "Attendance uses available attendance rows and report completion uses created reports; recording completeness must be reviewed before official publication."
    },
    {
      code: "child_safety",
      icon: "bi-shield-fill-check",
      titleAr: "سلامة الطفل والحوادث",
      titleEn: "Child Safety and Incidents",
      descriptionAr: "الحوادث المسجلة حسب مستوى الخطورة مع إبراز الحوادث الحرجة خلال الفترة المحددة.",
      descriptionEn: "Recorded incidents by severity, highlighting critical incidents in the selected period.",
      indicators: ["critical_incidents", "incidents_by_severity"],
      bulletsAr: ["إجمالي الحوادث", "الحوادث حسب الخطورة", "الحوادث الحرجة"],
      bulletsEn: ["Total incidents", "Incidents by severity", "Critical incidents"],
      caveatAr: "هذه بيانات حوادث معروفة ومسجلة في الحضانات، وليست تقديراً لانتشار العنف على المستوى الوطني.",
      caveatEn: "These are known, recorded nursery incidents and are not an estimate of national violence prevalence."
    },
    {
      code: "workforce_supervision",
      icon: "bi-person-workspace",
      titleAr: "الكوادر والإشراف والتوزيع الصفي",
      titleEn: "Workforce, Supervision, and Class Assignment",
      descriptionAr: "المدراء والمشرفون المسجلون والفصول غير المسندة والأطفال النشطون غير المسجلين في صف.",
      descriptionEn: "Recorded managers and supervisors, unassigned classes, and active children without class assignment.",
      indicators: ["staff_count", "unassigned_classes", "unassigned_children"],
      bulletsAr: ["المدراء والمشرفون", "الفصول دون مشرف", "الأطفال دون صف"],
      bulletsEn: ["Managers and supervisors", "Classes without supervisor", "Children without class assignment"],
      caveatAr: "عدد الموظفين الحالي يشمل أدوار المدير والمشرف المسجلة في النظام، ولا يمثل بالضرورة جميع العاملين في الحضانة.",
      caveatEn: "The current staff count covers registered manager and supervisor roles and may not represent every nursery worker."
    },
    {
      code: "reporting_participation",
      icon: "bi-database-check",
      titleAr: "المشاركة الحديثة في الإبلاغ",
      titleEn: "Recent Reporting Participation",
      descriptionAr: "نسبة الحضانات النشطة التي قدمت تقريراً يومياً واحداً على الأقل خلال الأيام السبعة الأخيرة.",
      descriptionEn: "The share of active nurseries with at least one daily report in the most recent seven days.",
      indicators: ["data_quality_score"],
      bulletsAr: ["الحضانات النشطة", "الحضانات المبلّغة", "نسبة المشاركة"],
      bulletsEn: ["Active nurseries", "Reporting nurseries", "Participation rate"],
      caveatAr: "هذا مؤشر مشاركة في الإبلاغ وليس تقييماً شاملاً لاكتمال البيانات ودقتها واتساقها وحداثتها.",
      caveatEn: "This is a reporting-participation indicator, not a comprehensive assessment of completeness, accuracy, consistency, and timeliness."
    }
  ];

  // Bilingual presentation maps. The custom-report backend returns Arabic-only
  // KPI labels/units and Arabic chart titles, and pushes raw enum values
  // (ACTIVE, PENDING_REVIEW, CRITICAL, ...) into chart categories and table
  // cells. These maps localise that output for both languages without changing
  // the shared backend contract, and reframe data_quality_score as the
  // reporting-participation metric it actually is in the NCFA context.
  const KPI_LABELS = {
    children_count: { ar: "عدد الأطفال", en: "Recorded children" },
    gender_distribution: { ar: "نسبة الذكور", en: "Male share" },
    age_distribution_6mo: { ar: "عدد الفئات العمرية (كل 6 أشهر)", en: "Six-month age bands" },
    enrollment_status: { ar: "التسجيلات النشطة", en: "Active enrolments" },
    kindergarten_count: { ar: "عدد الحضانات", en: "Nurseries" },
    kindergarten_status: { ar: "الحضانات النشطة", en: "Active nurseries" },
    occupancy_rate: { ar: "نسبة الإشغال", en: "Occupancy rate" },
    attendance_rate: { ar: "نسبة الحضور", en: "Attendance rate" },
    absence_requests: { ar: "طلبات الغياب", en: "Absence requests" },
    daily_report_completion: { ar: "معدل إنجاز التقارير اليومية", en: "Daily-report completion" },
    late_reports: { ar: "التقارير المتأخرة", en: "Late reports" },
    critical_incidents: { ar: "الحوادث الحرجة", en: "Critical incidents" },
    incidents_by_severity: { ar: "إجمالي الحوادث", en: "Total incidents" },
    staff_count: { ar: "عدد الموظفين", en: "Managers & supervisors" },
    unassigned_classes: { ar: "الفصول غير المسندة لمشرف", en: "Classes without supervisor" },
    unassigned_children: { ar: "الأطفال غير المسجلين في صف", en: "Children without a class" },
    // NCFA reframes this indicator as reporting participation, matching the
    // bundle caveat — it is NOT a comprehensive data-quality score.
    data_quality_score: { ar: "نسبة المشاركة في الإبلاغ", en: "Reporting participation rate" }
  };

  const UNIT_LABELS = {
    "طفل": { ar: "طفل", en: "children" },
    "%": { ar: "%", en: "%" },
    "فئة": { ar: "فئة", en: "bands" },
    "تسجيل": { ar: "تسجيل", en: "enrolments" },
    "حضانة": { ar: "حضانة", en: "nurseries" },
    "طلب": { ar: "طلب", en: "requests" },
    "تقرير": { ar: "تقرير", en: "reports" },
    "حادثة": { ar: "حادثة", en: "incidents" },
    "موظف": { ar: "موظف", en: "staff" },
    "صف": { ar: "صف", en: "classes" }
  };

  const CHART_TITLES = {
    "التوزيع حسب الجنس": { ar: "التوزيع حسب الجنس", en: "Sex distribution" },
    "التوزيع العمري كل 6 أشهر": { ar: "التوزيع العمري كل 6 أشهر", en: "Age distribution (6-month bands)" },
    "حالة التسجيل": { ar: "حالة التسجيل", en: "Enrolment status" },
    "حالة الحضانات": { ar: "حالة الحضانات", en: "Nursery status" },
    "الحوادث حسب الخطورة": { ar: "الحوادث حسب الخطورة", en: "Incidents by severity" }
  };

  // Raw enum values (and pre-translated gender labels) that the backend emits
  // as category labels. Localised in BOTH languages — the Arabic UI currently
  // leaks the raw uppercase enum too, so this fixes the primary language as well.
  const CATEGORY_LABELS = {
    DRAFT: { ar: "مسودة", en: "Draft" },
    SUBMITTED: { ar: "مُقدَّم", en: "Submitted" },
    PENDING_REVIEW: { ar: "قيد المراجعة", en: "Pending review" },
    ACCEPTED: { ar: "مقبول", en: "Accepted" },
    REJECTED: { ar: "مرفوض", en: "Rejected" },
    WITHDRAWN: { ar: "منسحب", en: "Withdrawn" },
    WAITLISTED: { ar: "قائمة الانتظار", en: "Waitlisted" },
    ACTIVE: { ar: "نشط", en: "Active" },
    FROZEN: { ar: "مجمّدة", en: "Frozen" },
    INACTIVE: { ar: "غير نشطة", en: "Inactive" },
    DELETED: { ar: "محذوفة", en: "Deleted" },
    LOW: { ar: "منخفضة", en: "Low" },
    MEDIUM: { ar: "متوسطة", en: "Medium" },
    HIGH: { ar: "عالية", en: "High" },
    CRITICAL: { ar: "حرجة", en: "Critical" },
    "ذكر": { ar: "ذكر", en: "Male" },
    "أنثى": { ar: "أنثى", en: "Female" },
    "غير محدد": { ar: "غير محدد", en: "Unspecified" },
    "غير معروف": { ar: "غير معروف", en: "Unknown" },
    "محجوب": { ar: "محجوب", en: "Suppressed" }
  };

  // Common table headers the backend returns as Arabic dict keys.
  const HEADER_LABELS = {
    "المؤشر": "Indicator",
    "القيمة": "Value",
    "الفئة": "Category",
    "النسبة %": "Percent %"
  };

  function pickLocale(map, key) {
    const meta = key == null ? null : map[String(key)];
    if (!meta) return null;
    return lang === "en" ? meta.en : meta.ar;
  }

  function localizeCategory(value) {
    const localized = pickLocale(CATEGORY_LABELS, value);
    return localized == null ? value : localized;
  }

  function localizeHeader(header) {
    if (lang !== "en") return header;
    return HEADER_LABELS[header] || header;
  }

  function getCookie(name) {
    const escaped = name.replace(/([.$?*|{}()[\]\\/+^])/g, "\\$1");
    const match = document.cookie.match(new RegExp("(?:^|; )" + escaped + "=([^;]*)"));
    return match ? decodeURIComponent(match[1]) : "";
  }

  function createElement(tag, options) {
    const node = document.createElement(tag);
    const opts = options || {};
    if (opts.className) node.className = opts.className;
    if (opts.text != null) node.textContent = String(opts.text);
    if (opts.attrs) Object.keys(opts.attrs).forEach((key) => node.setAttribute(key, opts.attrs[key]));
    (opts.children || []).forEach((child) => child && node.appendChild(child));
    return node;
  }

  function bundleText(bundle, field) {
    return lang === "en" ? bundle[field + "En"] : bundle[field + "Ar"];
  }

  function renderBundles() {
    bundleGrid.innerHTML = "";
    REPORT_BUNDLES.forEach((bundle) => {
      const card = createElement("article", { className: "ncfa-bundle-card", attrs: { role: "listitem" } });
      const icon = createElement("span", { className: "ncfa-bundle-card__icon", attrs: { "aria-hidden": "true" } });
      icon.appendChild(createElement("i", { className: "bi " + bundle.icon }));
      const titleWrap = createElement("div");
      titleWrap.append(
        createElement("h3", { text: bundleText(bundle, "title") }),
        createElement("span", { className: "ncfa-bundle-card__rating", text: t("توافق قوي", "Strong alignment") })
      );
      const head = createElement("div", { className: "ncfa-bundle-card__head", children: [icon, titleWrap] });
      const description = createElement("p", { text: bundleText(bundle, "description") });
      const bullets = lang === "en" ? bundle.bulletsEn : bundle.bulletsAr;
      const list = createElement("ul");
      bullets.forEach((item) => list.appendChild(createElement("li", { text: item })));
      const button = createElement("button", {
        className: "admin-btn admin-btn-primary",
        text: t("إنشاء التقرير", "Generate report"),
        attrs: { type: "button", "data-bundle-code": bundle.code }
      });
      button.addEventListener("click", () => generateBundle(bundle));
      card.append(head, description, list, button);
      bundleGrid.appendChild(card);
    });
  }

  function resetDistricts(placeholder) {
    districtSelect.innerHTML = "";
    districtSelect.appendChild(createElement("option", { text: placeholder, attrs: { value: "" } }));
    districtSelect.disabled = true;
  }

  function loadDivisions() {
    const url = window.NCFA_ADMIN_DIVISIONS_URL || "/static/data/jordan_admin_divisions.json";
    fetch(url, { credentials: "same-origin" })
      .then((response) => {
        if (!response.ok) throw new Error("HTTP " + response.status);
        return response.json();
      })
      .then((data) => {
        divisions = Array.isArray(data) ? data : [];
        divisions.forEach((entry) => {
          governorateSelect.appendChild(createElement("option", { text: entry.gov, attrs: { value: entry.gov } }));
        });
      })
      .catch(() => {
        divisions = [];
      });
  }

  function fillDistricts(governorate) {
    resetDistricts(t("كل الألوية", "All districts"));
    if (!governorate) {
      resetDistricts(t("اختر المحافظة أولاً", "Select governorate first"));
      return;
    }
    const entry = divisions.find((item) => item.gov === governorate);
    if (!entry || !Array.isArray(entry.districts)) return;
    entry.districts.forEach((district) => {
      districtSelect.appendChild(createElement("option", { text: district.name, attrs: { value: district.name } }));
    });
    districtSelect.disabled = false;
  }

  function currentScope(bundle) {
    const governorate = governorateSelect.value || null;
    const city = districtSelect.value || null;
    return {
      agency: "ncfa",
      level: city ? "city" : (governorate ? "governorate" : "national"),
      period: periodSelect.value || "quarter",
      governorate: governorate,
      city: city,
      kindergarten_id: null,
      indicators: bundle.indicators.slice(),
      report_name: bundleText(bundle, "title"),
      purpose: bundleText(bundle, "description")
    };
  }

  function clearCharts() {
    while (chartInstances.length) {
      const chart = chartInstances.pop();
      try { chart.destroy(); } catch (error) { /* no-op */ }
    }
  }

  function setStatus(kind, text) {
    resultStatus.className = "ncfa-result-status ncfa-result-status--" + kind;
    resultStatus.textContent = text;
  }

  function showLoading(bundle) {
    clearCharts();
    resultSection.hidden = false;
    exportButton.hidden = true;
    activePayload = null;
    resultTitle.textContent = bundleText(bundle, "title");
    resultDescription.textContent = bundleText(bundle, "description");
    setStatus("loading", t("جارٍ الاحتساب", "Calculating"));
    resultBody.innerHTML = "";
    resultBody.appendChild(createElement("div", {
      className: "ncfa-loading",
      text: t("جارٍ احتساب المؤشرات من البيانات المسجلة...", "Calculating indicators from recorded data...")
    }));
    resultTitle.focus();
  }

  function generateBundle(bundle) {
    activeBundle = bundle;
    const sequence = ++requestSequence;
    const scope = currentScope(bundle);
    showLoading(bundle);

    fetch("/api/admin/agency-reports/custom", {
      method: "POST",
      credentials: "same-origin",
      headers: {
        "Content-Type": "application/json",
        "X-Requested-With": "XMLHttpRequest",
        "X-CSRF-Token": getCookie("kinjo_csrf_token")
      },
      body: JSON.stringify(scope)
    })
      .then(async (response) => {
        const body = await response.json().catch(() => ({}));
        if (!response.ok) {
          const detail = body.detail || body.message || ("HTTP " + response.status);
          throw new Error(detail);
        }
        return body.data || body;
      })
      .then((payload) => {
        if (sequence !== requestSequence) return;
        activePayload = payload;
        renderPayload(bundle, payload);
      })
      .catch((error) => {
        if (sequence !== requestSequence) return;
        renderError(error);
      });
  }

  function renderPayload(bundle, payload) {
    clearCharts();
    resultBody.innerHTML = "";
    resultSection.hidden = false;
    resultTitle.textContent = bundleText(bundle, "title");
    resultDescription.textContent = bundleText(bundle, "description");

    const quality = payload.data_quality || { status: "incomplete", notes: [] };
    const statusMap = {
      sufficient: ["sufficient", t("البيانات متاحة", "Data available")],
      limited: ["limited", t("البيانات محدودة", "Limited data")],
      incomplete: ["incomplete", t("البيانات غير مكتملة", "Incomplete data")]
    };
    const statusInfo = statusMap[quality.status] || statusMap.incomplete;
    setStatus(statusInfo[0], statusInfo[1]);

    const scope = payload.scope || {};
    const scopeParts = [scope.level_name_ar || scope.level || ""];
    if (scope.governorate) scopeParts.push(scope.governorate);
    if (scope.city) scopeParts.push(scope.city);
    if (scope.start_date && scope.end_date) scopeParts.push(scope.start_date + " → " + scope.end_date);
    resultBody.appendChild(createElement("div", {
      className: "ncfa-scope-summary",
      text: t("النطاق: ", "Scope: ") + scopeParts.filter(Boolean).join(" · ")
    }));

    const kpis = Array.isArray(payload.kpis) ? payload.kpis : [];
    if (kpis.length) {
      const grid = createElement("div", { className: "ncfa-kpi-grid" });
      kpis.forEach((kpi) => {
        const label = pickLocale(KPI_LABELS, kpi.code) || kpi.label_ar || kpi.code || "";
        const unit = (kpi.unit_ar ? (pickLocale(UNIT_LABELS, kpi.unit_ar) || kpi.unit_ar) : "");
        const value = String(kpi.value == null ? "—" : kpi.value) + (unit ? " " + unit : "");
        grid.appendChild(createElement("div", {
          className: "ncfa-kpi-card",
          children: [
            createElement("strong", { text: value }),
            createElement("span", { text: label })
          ]
        }));
      });
      resultBody.appendChild(grid);
    }

    renderCharts(payload.charts || []);
    renderTable(payload.table || []);

    resultBody.appendChild(createElement("div", {
      className: "ncfa-caveat",
      text: bundleText(bundle, "caveat")
    }));

    const notes = Array.isArray(quality.notes) ? quality.notes.filter(Boolean) : [];
    if (notes.length) {
      const box = createElement("div", { className: "ncfa-quality-notes" });
      box.appendChild(createElement("strong", { text: t("ملاحظات جودة البيانات", "Data-quality notes") }));
      const list = createElement("ul");
      notes.forEach((note) => list.appendChild(createElement("li", { text: note })));
      box.appendChild(list);
      resultBody.appendChild(box);
    }

    if (!kpis.length && !(payload.table || []).length) {
      resultBody.appendChild(createElement("div", {
        className: "ncfa-empty",
        text: t("لا توجد مؤشرات محسوبة ضمن النطاق المحدد.", "No indicators were calculated for the selected scope.")
      }));
    }

    exportButton.hidden = !kpis.length && !(payload.table || []).length;
    resultTitle.focus();
  }

  // Validated accessible categorical palette (CVD-safe), status ramp for
  // severity, and a single brand hue for ordinal (age-band) distributions.
  const VIZ_CATEGORICAL = ["#2a78d6", "#1baf7a", "#eda100", "#008300", "#4a3aa7", "#e34948", "#e87ba4", "#eb6834"];
  const VIZ_STATUS = { LOW: "#0ca30c", MEDIUM: "#fab219", HIGH: "#ec835a", CRITICAL: "#d03b3b" };
  const VIZ_BRAND = "#176b4d";
  const VIZ_GRID = "#e2e8f0";
  const VIZ_TICK = "#64748b";
  const VIZ_INK = "#0f172a";

  function chartColorsFor(chart) {
    const labels = (chart.series || []).map((s) => String(s.label));
    const severity = ["LOW", "MEDIUM", "HIGH", "CRITICAL"];
    if (labels.length && labels.every((l) => severity.includes(l))) {
      return labels.map((l) => VIZ_STATUS[l] || VIZ_CATEGORICAL[0]); // severity -> status ramp
    }
    if ((chart.title_ar || "").indexOf("العمري") !== -1) {
      return VIZ_BRAND; // ordinal age bands -> one hue
    }
    return labels.map((_, i) => VIZ_CATEGORICAL[i % VIZ_CATEGORICAL.length]);
  }

  function renderCharts(charts) {
    if (!Array.isArray(charts) || !charts.length || !window.Chart) return;
    const grid = createElement("div", { className: "ncfa-chart-grid" });
    const rtl = lang !== "en";
    charts.forEach((chart, index) => {
      const series = Array.isArray(chart.series) ? chart.series : [];
      if (!series.length) return;
      const card = createElement("div", { className: "ncfa-chart-card" });
      const title = pickLocale(CHART_TITLES, chart.title_ar) || chart.title_ar || t("الرسم البياني", "Chart");
      card.appendChild(createElement("h4", { text: title }));

      // A breakdown whose values are all suppressed (null) or zero must show an
      // honest empty state, never a blank axis frame that looks broken.
      const displayable = series.filter((s) => typeof s.value === "number" && s.value > 0);
      if (!displayable.length) {
        card.appendChild(createElement("p", {
          className: "ncfa-chart-empty",
          text: series.some((s) => s.suppressed)
            ? t("القيم ضمن هذه الفئة محجوبة لحماية الخصوصية.", "Values in this breakdown are suppressed to protect privacy.")
            : t("لا توجد بيانات كافية للعرض ضمن النطاق المحدد.", "Not enough data to display for the selected scope.")
        }));
        grid.appendChild(card);
        return;
      }

      const isPie = chart.type === "pie";
      const colors = chartColorsFor(chart);
      const wrap = createElement("div", { className: "ncfa-chart-canvas" });
      const canvas = createElement("canvas", { attrs: { id: "ncfa-chart-" + index, role: "img", "aria-label": title } });
      wrap.appendChild(canvas);
      card.appendChild(wrap);
      grid.appendChild(card);

      const instance = new window.Chart(canvas.getContext("2d"), {
        type: isPie ? "doughnut" : "bar",
        data: {
          labels: series.map((item) => localizeCategory(item.label)),
          datasets: [{
            label: title,
            data: series.map((item) => item.value),
            backgroundColor: colors,
            borderColor: isPie ? "#ffffff" : colors,
            borderWidth: isPie ? 2 : 0,
            borderRadius: isPie ? 0 : 5,
            borderSkipped: false,
            maxBarThickness: 34,
            hoverOffset: isPie ? 6 : 0
          }]
        },
        options: {
          indexAxis: isPie ? "x" : "y", // horizontal bars read long Arabic labels cleanly
          responsive: true,
          maintainAspectRatio: false,
          layout: { padding: 4 },
          cutout: isPie ? "58%" : undefined,
          plugins: {
            legend: {
              display: isPie,
              position: "bottom",
              rtl: rtl,
              labels: { color: VIZ_INK, usePointStyle: true, pointStyle: "circle", boxWidth: 8, padding: 14, font: { size: 12 } }
            },
            tooltip: { rtl: rtl, backgroundColor: "#0f172a", padding: 10, cornerRadius: 8, titleFont: { size: 12 }, bodyFont: { size: 13 } }
          },
          scales: isPie ? {} : {
            x: { beginAtZero: true, ticks: { precision: 0, color: VIZ_TICK, font: { size: 11 } }, grid: { color: VIZ_GRID, drawBorder: false } },
            y: { ticks: { color: VIZ_INK, font: { size: 12 } }, grid: { display: false, drawBorder: false } }
          }
        }
      });
      chartInstances.push(instance);
    });
    if (grid.childElementCount) resultBody.appendChild(grid);
  }

  function renderTable(rows) {
    if (!Array.isArray(rows) || !rows.length) return;
    const headers = [];
    rows.forEach((row) => Object.keys(row || {}).forEach((key) => {
      if (!headers.includes(key)) headers.push(key);
    }));
    const wrap = createElement("div", { className: "ncfa-table-wrap" });
    wrap.appendChild(createElement("h4", { text: t("جدول المؤشرات", "Indicator table") }));
    const table = createElement("table", { className: "ncfa-data-table" });
    const caption = createElement("caption", { text: resultTitle.textContent });
    table.appendChild(caption);
    const thead = createElement("thead");
    const headRow = createElement("tr");
    headers.forEach((header) => headRow.appendChild(createElement("th", { text: localizeHeader(header), attrs: { scope: "col" } })));
    thead.appendChild(headRow);
    table.appendChild(thead);
    const tbody = createElement("tbody");
    rows.forEach((row) => {
      const tr = createElement("tr");
      headers.forEach((header) => tr.appendChild(createElement("td", { text: row[header] == null ? "—" : localizeCategory(row[header]) })));
      tbody.appendChild(tr);
    });
    table.appendChild(tbody);
    wrap.appendChild(table);
    resultBody.appendChild(wrap);
  }

  function renderError(error) {
    clearCharts();
    resultSection.hidden = false;
    exportButton.hidden = true;
    setStatus("error", t("تعذر إنشاء التقرير", "Report failed"));
    resultBody.innerHTML = "";
    resultBody.appendChild(createElement("div", {
      className: "ncfa-error",
      text: t("تعذر احتساب التقرير. تحقق من البيانات أو أعد المحاولة. ", "The report could not be calculated. Check the data or try again. ") + (error && error.message ? error.message : "")
    }));
    resultTitle.focus();
  }

  function exportCsv() {
    if (!activeBundle || !activePayload) return;
    const scope = currentScope(activeBundle);
    exportButton.disabled = true;
    fetch("/api/admin/agency-reports/custom/export.csv", {
      method: "POST",
      credentials: "same-origin",
      headers: {
        "Content-Type": "application/json",
        "X-Requested-With": "XMLHttpRequest",
        "X-CSRF-Token": getCookie("kinjo_csrf_token")
      },
      body: JSON.stringify(scope)
    })
      .then((response) => {
        if (!response.ok) throw new Error("HTTP " + response.status);
        return response.blob();
      })
      .then((blob) => {
        const url = URL.createObjectURL(blob);
        const link = document.createElement("a");
        link.href = url;
        link.download = "ncfa_" + activeBundle.code + "_" + new Date().toISOString().slice(0, 10) + ".csv";
        document.body.appendChild(link);
        link.click();
        link.remove();
        URL.revokeObjectURL(url);
      })
      .catch((error) => renderError(error))
      .finally(() => { exportButton.disabled = false; });
  }

  governorateSelect.addEventListener("change", () => fillDistricts(governorateSelect.value));
  resetScopeButton.addEventListener("click", () => {
    periodSelect.value = "quarter";
    governorateSelect.value = "";
    resetDistricts(t("اختر المحافظة أولاً", "Select governorate first"));
  });
  exportButton.addEventListener("click", exportCsv);

  renderBundles();
  resetDistricts(t("اختر المحافظة أولاً", "Select governorate first"));
  loadDivisions();
}());
