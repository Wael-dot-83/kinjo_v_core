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
      caveatAr: "يعكس التقرير الأطفال المسجلين في كينجو ولا يمثل تعداداً سكانياً وطنياً.",
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
        const value = String(kpi.value == null ? "—" : kpi.value) + (kpi.unit_ar ? " " + kpi.unit_ar : "");
        grid.appendChild(createElement("div", {
          className: "ncfa-kpi-card",
          children: [
            createElement("strong", { text: value }),
            createElement("span", { text: kpi.label_ar || kpi.code || "" })
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

  function renderCharts(charts) {
    if (!Array.isArray(charts) || !charts.length || !window.Chart) return;
    const grid = createElement("div", { className: "ncfa-chart-grid" });
    charts.forEach((chart, index) => {
      const series = Array.isArray(chart.series) ? chart.series : [];
      if (!series.length) return;
      const card = createElement("div", { className: "ncfa-chart-card" });
      const title = chart.title_ar || t("الرسم البياني", "Chart");
      card.appendChild(createElement("h4", { text: title }));
      const canvas = createElement("canvas", {
        attrs: {
          id: "ncfa-chart-" + index,
          role: "img",
          "aria-label": title
        }
      });
      card.appendChild(canvas);
      grid.appendChild(card);
      const instance = new window.Chart(canvas.getContext("2d"), {
        type: chart.type === "pie" ? "pie" : "bar",
        data: {
          labels: series.map((item) => item.label),
          datasets: [{ label: title, data: series.map((item) => item.value) }]
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: { legend: { position: chart.type === "pie" ? "bottom" : "top" } },
          scales: chart.type === "pie" ? {} : { y: { beginAtZero: true } }
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
    headers.forEach((header) => headRow.appendChild(createElement("th", { text: header, attrs: { scope: "col" } })));
    thead.appendChild(headRow);
    table.appendChild(thead);
    const tbody = createElement("tbody");
    rows.forEach((row) => {
      const tr = createElement("tr");
      headers.forEach((header) => tr.appendChild(createElement("td", { text: row[header] == null ? "—" : row[header] })));
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
