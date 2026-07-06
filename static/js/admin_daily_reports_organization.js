(function () {
  const state = {
    allKindergartens: [],
    selectedResponse: null,
    governorateMap: new Map(),
  };

  const STATUS_ORDER = {
    received: 1,
    pending: 2,
    incomplete: 3,
    absent: 4,
    not_submitted: 5,
  };

  const STATUS_UI_CONFIG = {
    received: {
      labelAr: "تم استلامه من قبل الوالدين",
      labelEn: "Received by parents",
      icon: "bi bi-check-circle-fill",
      colorClass: "text-success",
      bgClass: "bg-success-subtle",
    },
    pending: {
      labelAr: "بانتظار مراجعة المدير",
      labelEn: "Pending manager review",
      icon: "bi bi-clock-fill",
      colorClass: "text-warning",
      bgClass: "bg-warning-subtle",
    },
    incomplete: {
      labelAr: "غير مكتمل",
      labelEn: "Incomplete",
      icon: "bi bi-exclamation-triangle-fill",
      colorClass: "text-info",
      bgClass: "bg-info-subtle",
    },
    absent: {
      labelAr: "غير مملوء - غياب الطفل",
      labelEn: "Not filled - child absent",
      icon: "bi bi-person-x-fill",
      colorClass: "text-danger",
      bgClass: "bg-danger-subtle",
    },
    not_submitted: {
      labelAr: "غير مملوء - لم يقدم المشرف/المعلم",
      labelEn: "Not filled - supervisor or teacher did not submit",
      icon: "bi bi-file-earmark-x-fill",
      colorClass: "text-secondary",
      bgClass: "bg-secondary-subtle",
    },
  };

  function isEnglishUi() {
    if (typeof t === "function") {
      return !t("ar", "en");
    }
    return String(document.documentElement.lang || "").toLowerCase() === "en";
  }

  function t(arText, enText) {
    if (typeof window.t === "function") {
      return window.t(arText, enText);
    }
    return isEnglishUi() ? enText : arText;
  }

  function uiLocale() {
    return isEnglishUi() ? "en-GB" : "ar-EG";
  }

  function formatNumber(value) {
    const numericValue = Number(value || 0);
    return numericValue.toLocaleString(uiLocale());
  }

  function localizeServerMessage(message) {
    const normalized = String(message || "").trim();
    if (!normalized) {
      return "";
    }
    if (normalized === "غير متاح") {
      return t("غير متاح", "Not available");
    }
    if (normalized === "لا توجد تقارير متاحة بناءً على الاختيارات") {
      return t(
        "لا توجد تقارير متاحة بناءً على الاختيارات",
        "No reports are available for the selected filters"
      );
    }
    if (normalized === "لا توجد تقارير يومية مقدمة لهذا اليوم") {
      return t(
        "لا توجد تقارير يومية مقدمة لهذا اليوم",
        "No daily reports were submitted for this date"
      );
    }
    return normalized;
  }

  function getStatusDisplay(status) {
    const cfg = STATUS_UI_CONFIG[status] || {
      labelAr: status || "غير معروف",
      labelEn: status || "Unknown",
      icon: "fas fa-question-circle",
      colorClass: "text-muted",
      bgClass: "bg-light",
    };
    return {
      ...cfg,
      label: t(cfg.labelAr, cfg.labelEn),
    };
  }


  async function apiGet(path, params = {}) {
    const search = new URLSearchParams();
    Object.entries(params).forEach(([key, value]) => {
      if (value === undefined || value === null || value === "") {
        return;
      }
      search.set(key, String(value));
    });

    const query = search.toString();
    const url = query ? `${path}?${query}` : path;

    const response = await fetch(url, {
      method: "GET",
      headers: {
        "Content-Type": "application/json",
      },
    });

    if (!response.ok) {
      const text = await response.text();
      throw new Error(
        localizeServerMessage(text) || t("تعذر تحميل البيانات", "Unable to load data")
      );
    }

    return response.json();
  }

  function toYmd(dateObj) {
    const year = dateObj.getFullYear();
    const month = String(dateObj.getMonth() + 1).padStart(2, "0");
    const day = String(dateObj.getDate()).padStart(2, "0");
    return `${year}-${month}-${day}`;
  }

  function formatDateLocalized(isoDate) {
    if (!isoDate) {
      return "";
    }
    const dateValue = new Date(`${isoDate}T00:00:00`);
    if (Number.isNaN(dateValue.getTime())) {
      return isoDate;
    }
    const locale = isEnglishUi() ? "en-GB" : "ar-EG-u-ca-gregory-nu-arab";
    return new Intl.DateTimeFormat(locale, {
      day: "numeric",
      month: "long",
      year: "numeric",
    }).format(dateValue);
  }

  function resolveKindergartenName(kg) {
    if (isEnglishUi()) {
      return (
        kg?.name_en || kg?.name_ar || kg?.name || t("حضانة غير محددة", "Unspecified kindergarten")
      );
    }
    return (
      kg?.name_ar || kg?.name_en || kg?.name || t("حضانة غير محددة", "Unspecified kindergarten")
    );
  }

  function resolveGovernorateLabel(rawGovernorate) {
    const value = String(rawGovernorate || "").trim();
    if (!value) {
      return t("غير محدد", "Unspecified");
    }
    if (!isEnglishUi()) {
      return value;
    }
    return state.governorateMap.get(value) || value;
  }

  function resolveChildName(row) {
    if (isEnglishUi()) {
      return row?.child_name_en || row?.child_name_ar || "";
    }
    return row?.child_name_ar || row?.child_name_en || "";
  }

  function resolveTeacherName(row) {
    if (isEnglishUi()) {
      return row?.filled_by_name_en || row?.filled_by_name_ar || "";
    }
    return row?.filled_by_name_ar || row?.filled_by_name_en || "";
  }

  function buildChildLabel(row) {
    const childName = resolveChildName(row) || t("غير متاح", "Unavailable");
    if (isEnglishUi()) {
      return `${childName} (<bdi>ID: ${row.child_id}</bdi>)`;
    }
    return row?.child_label_ar || `اسم الطفل: ${childName} (<bdi>المعرف: ${row.child_id}</bdi>)`;
  }

  function setLoading(isLoading) {
    const loadingBox = document.getElementById("dailyReportsLoading");
    if (!loadingBox) {
      return;
    }
    loadingBox.classList.toggle("d-none", !isLoading);
  }

  function setError(message) {
    const errorBox = document.getElementById("dailyReportsError");
    if (!errorBox) {
      return;
    }

    if (message) {
      errorBox.textContent = message;
      errorBox.classList.remove("d-none");
    } else {
      errorBox.textContent = "";
      errorBox.classList.add("d-none");
    }
  }

  function setEmptyMessage(message) {
    const emptyBox = document.getElementById("dailyReportsEmpty");
    if (!emptyBox) {
      return;
    }

    if (message) {
      const msg = localizeServerMessage(message) || message;
      emptyBox.innerHTML = `
        <div class="empty-state p-4 text-center border rounded-3 bg-light text-dark" role="status">
          <h3 class="h5 mb-2">${escapeHtml(msg)}</h3>
          <p class="text-muted mb-0 small">
            ${t("يرجى مراجعة المعلم أو التحقق من سجل الحضور لمعرفة حالة الحضور والتقارير.", "Please consult the teacher or check the attendance register to verify reporting and attendance status.")}
          </p>
        </div>
      `;
      emptyBox.classList.remove("d-none");
    } else {
      emptyBox.innerHTML = "";
      emptyBox.classList.add("d-none");
    }
  }

  function setMeta(response, shownCount) {
    const meta = document.getElementById("dailyReportsMeta");
    const selectedDateChip = document.getElementById("selectedDateChip");
    const selectedCountChip = document.getElementById("selectedCountChip");
    if (!meta || !selectedDateChip || !selectedCountChip) {
      return;
    }

    if (!response) {
      meta.classList.add("d-none");
      return;
    }

    const dateLabel = isEnglishUi()
      ? formatDateLocalized(response.date)
      : response.date_ar || formatDateLocalized(response.date);
    selectedDateChip.textContent = `${t("التاريخ", "Date")}: ${dateLabel}`;
    selectedCountChip.textContent = `${t("عدد الحضانات المعروضة", "Displayed kindergartens")}: ${formatNumber(shownCount)}`;
    meta.classList.remove("d-none");
  }

  function getSelectedKindergartenIds() {
    const container = document.getElementById("kindergartenCheckboxGroup");
    if (!container) {
      return [];
    }
    return Array.from(container.querySelectorAll(".kg-checkbox:checked"))
      .map((input) => Number(input.value))
      .filter((value) => Number.isInteger(value) && value > 0);
  }

  function renderGovernorates(governorates) {
    const governorateSelect = document.getElementById("governorateSelect");
    if (!governorateSelect) {
      return;
    }

    state.governorateMap = new Map();
    const options = [`<option value="">${t("اختر المحافظة", "Select governorate")}</option>`];

    governorates.forEach((item) => {
      const canonical = item.name_ar || item.name || item.name_en || "";
      if (!canonical) {
        return;
      }
      const labelEn = item.name_en || item.name || canonical;
      state.governorateMap.set(String(canonical), labelEn);
      const label = isEnglishUi() ? labelEn : item.name_ar || canonical;
      options.push(`<option value="${escapeHtml(canonical)}">${escapeHtml(label)}</option>`);
    });
    governorateSelect.innerHTML = options.join("");
  }

  function renderKindergartensByGovernorate(governorateValue) {
    const container = document.getElementById("kindergartenCheckboxGroup");
    if (!container) {
      return;
    }

    const items = state.allKindergartens.filter((kg) => {
      if (!governorateValue) {
        return true;
      }
      return String(kg.governorate || "") === String(governorateValue);
    });

    items.sort((a, b) =>
      String(resolveKindergartenName(a)).localeCompare(
        String(resolveKindergartenName(b)),
        uiLocale()
      )
    );

    const checkboxes = items.map((kg) => {
      const name = resolveKindergartenName(kg);
      const governorate = resolveGovernorateLabel(kg.governorate);
      return `
        <div class="form-check mb-1">
          <input class="form-check-input kg-checkbox" type="checkbox" value="${kg.id}" id="kg_chk_${kg.id}">
          <label class="form-check-label small" for="kg_chk_${kg.id}">
            ${escapeHtml(name)} - <span class="text-muted"><bdi>${escapeHtml(governorate)}</bdi></span>
          </label>
        </div>
      `;
    });
    container.innerHTML = checkboxes.join("");

    const allChecked = Boolean(document.getElementById("allKindergartens")?.checked);
    if (!allChecked && governorateValue) {
      container.querySelectorAll(".kg-checkbox").forEach((input) => {
        input.checked = true;
      });
    }

    // Bind checkbox change events
    container.querySelectorAll(".kg-checkbox").forEach((input) => {
      input.addEventListener("change", () => {
        if (state.selectedResponse) {
          renderGroups(state.selectedResponse);
        }
      });
    });

    toggleScopeControls();
  }

  function toggleScopeControls() {
    const allCheckbox = document.getElementById("allKindergartens");
    const governorateSelect = document.getElementById("governorateSelect");
    const container = document.getElementById("kindergartenCheckboxGroup");
    if (!allCheckbox || !governorateSelect || !container) {
      return;
    }

    const disabled = allCheckbox.checked;
    governorateSelect.disabled = disabled;
    container.querySelectorAll(".kg-checkbox").forEach((input) => {
      input.disabled = disabled;
    });
  }

  function buildQueryParams() {
    const dateInput = document.getElementById("dailyReportDate");
    const governorateSelect = document.getElementById("governorateSelect");
    const allCheckbox = document.getElementById("allKindergartens");

    const dateValue = dateInput?.value || toYmd(new Date());
    const allChecked = Boolean(allCheckbox?.checked);
    const governorateValue = governorateSelect?.value || "";
    const kindergartenIds = getSelectedKindergartenIds();

    const params = {
      date: dateValue,
      all_kindergartens: allChecked ? "true" : "false",
    };

    if (!allChecked && kindergartenIds.length > 0) {
      params.kindergarten_ids = kindergartenIds.join(",");
    } else if (!allChecked && governorateValue) {
      params.governorate_id = governorateValue;
    }

    return params;
  }

  function applyClientFilters(groups) {
    const statusFilter = document.getElementById("statusFilter")?.value || "";
    const childSearch = (document.getElementById("childSearch")?.value || "").trim().toLowerCase();
    const teacherSearch = (document.getElementById("teacherSearch")?.value || "")
      .trim()
      .toLowerCase();
    const sortField = document.getElementById("sortField")?.value || "child";
    const sortDir = document.getElementById("sortDir")?.value || "asc";

    return (groups || [])
      .map((kg) => {
        let rows = Array.isArray(kg.reports) ? [...kg.reports] : [];

        rows = rows.filter((row) => {
          if (statusFilter && row.status !== statusFilter) {
            return false;
          }

          if (childSearch && !String(resolveChildName(row)).toLowerCase().includes(childSearch)) {
            return false;
          }

          if (
            teacherSearch &&
            !String(resolveTeacherName(row)).toLowerCase().includes(teacherSearch)
          ) {
            return false;
          }

          return true;
        });

        rows.sort((a, b) => {
          let left = "";
          let right = "";

          if (sortField === "status") {
            left = STATUS_ORDER[a.status] || 99;
            right = STATUS_ORDER[b.status] || 99;
          } else if (sortField === "teacher") {
            left = String(resolveTeacherName(a));
            right = String(resolveTeacherName(b));
          } else {
            left = String(resolveChildName(a));
            right = String(resolveChildName(b));
          }

          if (left < right) {
            return sortDir === "asc" ? -1 : 1;
          }
          if (left > right) {
            return sortDir === "asc" ? 1 : -1;
          }
          return 0;
        });

        return { ...kg, reports: rows };
      })
      .filter((kg) => kg.has_reports || kg.reports.length > 0);
  }

  function statusSummaryHtml(statusCounts) {
    if (!statusCounts || typeof statusCounts !== "object") {
      return "";
    }
    return Object.keys(STATUS_UI_CONFIG)
      .map((key) => {
        const value = Number(statusCounts[key] || 0);
        const cfg = getStatusDisplay(key);
        return `
          <li class="summary-chip badge ${cfg.bgClass} text-dark p-2 border">
            <span class="fw-semibold">${escapeHtml(cfg.label)}:</span>
            <strong class="mx-1"><bdi>${formatNumber(value)}</bdi></strong>
          </li>
        `;
      })
      .join("");
  }

  function renderTableRows(rows) {
    if (!rows || rows.length === 0) {
      return `
        <tr>
          <td colspan="4" class="text-center text-muted py-4">${t("لا توجد نتائج مطابقة للفلاتر الحالية", "No matching rows for the current filters")}</td>
        </tr>
      `;
    }

    return rows
      .map((row) => {
        const cfg = getStatusDisplay(row.status);
        const teacherName = resolveTeacherName(row);
        const displayTeacher = teacherName ? escapeHtml(teacherName) : `<span aria-label="${t("غير متاح", "Unavailable")}">—</span>`;
        const displayNotes = row.notes ? escapeHtml(row.notes) : `<span aria-label="${t("لا توجد ملاحظات", "No notes")}">—</span>`;
        return `
        <tr>
          <td>
            <div class="fw-semibold">${escapeHtml(buildChildLabel(row))}</div>
          </td>
          <td>${displayTeacher}</td>
          <td>
            <span class="status-pill ${cfg.bgClass}">
              <i class="${cfg.icon} ${cfg.colorClass}"></i>
              ${escapeHtml(cfg.label)}
            </span>
          </td>
          <td>${displayNotes}</td>
        </tr>
      `;
      })
      .join("");
  }

  function renderGroups(response) {
    const container = document.getElementById("dailyReportsAccordion");
    if (!container) {
      return;
    }

    const groups = applyClientFilters(response.kindergartens || []);

    if (groups.length === 0) {
      container.innerHTML = "";
      if (response.is_future_date) {
        setEmptyMessage(t("غير متاح", "Not available"));
      } else {
        setEmptyMessage(
          localizeServerMessage(response.message) ||
            t(
              "لا توجد تقارير متاحة بناءً على الاختيارات",
              "No reports are available for the selected filters"
            )
        );
      }
      setMeta(response, 0);
      return;
    }

    setEmptyMessage("");
    setMeta(response, groups.length);

    container.innerHTML = groups
      .map((kg, index) => {
        const collapseId = `kgCollapse${kg.id}`;
        const headingId = `kgHeading${kg.id}`;
        const expanded = index === 0 ? "true" : "false";
        const showClass = index === 0 ? "show" : "";
        const noReportsNote =
          kg.has_reports === false
            ? `<div class="no-report-note">${escapeHtml(localizeServerMessage(kg.message) || t("لا توجد تقارير يومية مقدمة لهذا اليوم", "No daily reports were submitted for this date"))}</div>`
            : "";
        const managerName = isEnglishUi()
          ? kg.manager_name_en || kg.manager_name_ar || t("غير محدد", "Unspecified")
          : kg.manager_name_ar || kg.manager_name_en || t("غير محدد", "Unspecified");
        const reportDate = isEnglishUi()
          ? formatDateLocalized(kg.report_date)
          : kg.report_date_ar || formatDateLocalized(kg.report_date);

        return `
          <section class="accordion-item mb-3 border rounded-3 overflow-hidden" aria-labelledby="${headingId}">
            <h2 class="accordion-header" id="${headingId}">
              <button class="accordion-button ${index === 0 ? "" : "collapsed"}" type="button"
                data-bs-toggle="collapse" data-bs-target="#${collapseId}" aria-expanded="${expanded}" aria-controls="${collapseId}">
                <div class="w-100">
                  <div class="fw-bold">${escapeHtml(resolveKindergartenName(kg))}</div>
                  <div class="kg-meta mt-1">
                    ${t("المدير", "Manager")}: <bdi>${escapeHtml(managerName)}</bdi> |
                    ${t("التاريخ", "Date")}: <bdi>${escapeHtml(reportDate)}</bdi>
                  </div>
                </div>
              </button>
            </h2>
            <div id="${collapseId}" class="accordion-collapse collapse ${showClass}" aria-labelledby="${headingId}" data-bs-parent="#dailyReportsAccordion">
              <div class="accordion-body">
                <ul class="status-summary d-flex flex-wrap gap-2 mb-3 list-unstyled" aria-label="${t(`ملخص حالة التقارير في ${resolveKindergartenName(kg)}`, `Report status summary in ${resolveKindergartenName(kg)}`)}">
                  ${statusSummaryHtml(kg.status_counts)}
                </ul>
                ${noReportsNote}
                <div class="table-responsive">
                  <table class="table table-hover report-table align-middle">
                    <caption class="visually-hidden">${t(`جدول التقارير اليومية لـ ${resolveKindergartenName(kg)}`, `Daily reports table for ${resolveKindergartenName(kg)}`)}</caption>
                    <thead class="table-light">
                      <tr>
                        <th scope="col">${t("الطفل", "Child")}</th>
                        <th scope="col">${t("تمت التعبئة بواسطة", "Filled by")}</th>
                        <th scope="col">${t("الحالة", "Status")}</th>
                        <th scope="col">${t("ملاحظات", "Notes")}</th>
                      </tr>
                    </thead>
                    <tbody>
                      ${renderTableRows(kg.reports)}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          </section>
        `;
      })
      .join("");
  }

  async function loadInitialFilters() {
    const [governoratesResponse, kindergartensResponse] = await Promise.all([
      apiGet("/api/reference/governorates"),
      apiGet("/api/kindergartens", { limit: 500, include_inactive: true }),
    ]);

    const governorates = governoratesResponse?.governorates || [];
    const kindergartens = kindergartensResponse?.kindergartens || [];

    state.allKindergartens = kindergartens;
    renderGovernorates(governorates);
    renderKindergartensByGovernorate("");
  }

  async function fetchAndRenderReports() {
    setError("");
    setEmptyMessage("");
    setLoading(true);
    try {
      const params = buildQueryParams();
      const response = await apiGet("/api/daily-reports", params);
      state.selectedResponse = response;
      renderGroups(response);
    } catch (error) {
      console.error(error);
      setError(
         error?.message ||
          t("خطأ في التحميل. يرجى إعادة المحاولة.", "Loading failed. Please try again.")
      );
      document.getElementById("dailyReportsAccordion").innerHTML = "";
      setMeta(null, 0);
    } finally {
      setLoading(false);
    }
  }

  function attachEvents() {
    const filterForm = document.getElementById("dailyReportsFilterForm");
    filterForm?.addEventListener("submit", (e) => {
      e.preventDefault();
      fetchAndRenderReports();
    });

    const searchBtn = document.getElementById("searchDailyReportsBtn");
    const allCheckbox = document.getElementById("allKindergartens");
    const governorateSelect = document.getElementById("governorateSelect");
    const dateInput = document.getElementById("dailyReportDate");
    const statusFilter = document.getElementById("statusFilter");
    const childSearch = document.getElementById("childSearch");
    const teacherSearch = document.getElementById("teacherSearch");
    const sortField = document.getElementById("sortField");
    const sortDir = document.getElementById("sortDir");

    searchBtn?.addEventListener("click", (e) => {
      e.preventDefault();
      fetchAndRenderReports();
    });

    allCheckbox?.addEventListener("change", () => {
      toggleScopeControls();
      if (allCheckbox.checked && state.selectedResponse) {
        fetchAndRenderReports();
      }
    });

    governorateSelect?.addEventListener("change", () => {
      renderKindergartensByGovernorate(governorateSelect.value || "");
    });

    dateInput?.addEventListener("change", fetchAndRenderReports);

    [statusFilter, childSearch, teacherSearch, sortField, sortDir].forEach((control) => {
      control?.addEventListener("input", () => {
        if (state.selectedResponse) {
          renderGroups(state.selectedResponse);
        }
      });
    });
  }

  async function init() {
    const dateInput = document.getElementById("dailyReportDate");
    if (dateInput && !dateInput.value) {
      dateInput.value = toYmd(new Date());
    }

    toggleScopeControls();
    attachEvents();
    setLoading(true);
    try {
      await loadInitialFilters();
      await fetchAndRenderReports();
    } catch (error) {
      console.error(error);
      setLoading(false);
      setError(error?.message || t("تعذر تحميل بيانات الصفحة.", "Unable to load page data."));
    }
  }

  document.addEventListener("DOMContentLoaded", init);
})();
